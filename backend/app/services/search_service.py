"""SearchService «control, coordinator»: runs one search (UC-01). Facade over the
evaluation steps; the REST layer (api/) only translates HTTP to and from this class.

    1. destination: OneMap geocoding (UC-02), or the location the Driver picked
    2. candidates within 1 km (FR1.4), minus season-only carparks; carpark type / EV filters
    3. lot type (FR4.3) and vehicle height (FR4.4) filters
    4. fee, current availability, expected busyness, EV info, walking route per carpark
    5. rank (RankingEngine) and return
"""
from datetime import datetime
from typing import Optional

from app.db.records import CarparkInfo
from app.exceptions import AddressNotFoundError, MultipleDestinationsError
from app.repositories.carpark_repository import CarparkRepository
from app.schemas.carpark import CarparkOut, Location
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services.availability_service import AvailabilityService
from app.services.busyness_estimator import BusynessEstimator
from app.services.ev_charging_service import EVChargingService
from app.services.fee_calculator import FeeCalculator
from app.services.ranking_engine import RankingEngine
from app.services.walking_service import WalkingService
from app.utils.geo import haversine_m
from app.utils.timeutil import now_sg

NO_CARPARKS = "No carparks found within {km:g} km of the destination."
NONE_MATCH = "No carparks within {km:g} km satisfy the selected requirements."
URA_PREFIX = "URA:"   # URA carparks: kerbside and surface lots, listed per vehicle category, no gantry


class SearchService:
    def __init__(self, map_service, carpark_repo: CarparkRepository, fee_calculator: FeeCalculator,
                 availability_service: AvailabilityService, busyness_estimator: BusynessEstimator,
                 ev_charging_service: EVChargingService, ranking_engine: RankingEngine,
                 walking_service: WalkingService, search_radius_m: float = 1000, max_walking_routes: int = 20):
        self._map = map_service
        self._carparks = carpark_repo
        self._fees = fee_calculator
        self._availability = availability_service
        self._busyness = busyness_estimator
        self._ev = ev_charging_service
        self._ranking = ranking_engine
        self._walking = walking_service
        self._radius_m = search_radius_m
        self._max_routes = max_walking_routes

    # ---- step 1 ----
    def resolve_destination(self, request: SearchRequest) -> Location:
        if request.destination_location is not None:
            return request.destination_location
        matches = self._map.search_locations(request.destination_address)
        if not matches:
            raise AddressNotFoundError(f"Destination {request.destination_address!r} could not be found.")
        exact = [m for m in matches if m.name.casefold() == request.destination_address.casefold()]
        if len(matches) == 1 or exact:
            return (exact or matches)[0].location
        raise MultipleDestinationsError(matches)

    # ---- steps 2-3 ----
    def _eligible(self, request: SearchRequest, destination: Location) -> tuple[list[CarparkInfo], Optional[str]]:
        pref = request.preference
        km = self._radius_m / 1000
        if not self._carparks.get_nearby_carparks(destination, self._radius_m):
            return [], NO_CARPARKS.format(km=km)                                   # UC-10
        candidates = self._carparks.get_nearby_carparks(
            destination, self._radius_m, carpark_types=pref.carpark_types or None, ev_required=pref.ev_required)
        known_lots = self._carparks.get_lot_types([c.carpark_id for c in candidates])
        eligible = [c for c in candidates
                    if c.carpark_id not in known_lots or pref.lot_type in {l.value for l in known_lots[c.carpark_id]}]
        # URA lists rates per vehicle category, so a URA carpark with no rate rules for the
        # Driver's lot type does not offer that lot type (e.g. backlanes without car lots): FR4.3.
        eligible = [c for c in eligible
                    if not c.carpark_id.startswith(URA_PREFIX) or self._carparks.get_rate_rules(c.carpark_id, pref.lot_type)]
        if pref.vehicle_height_m:
            eligible = [c for c in eligible if c.gantry_height_m is None or pref.vehicle_height_m <= c.gantry_height_m]
        return eligible, (None if eligible else NONE_MATCH.format(km=km))           # UC-07 EX1

    # ---- the whole search ----
    def search_carparks(self, request: SearchRequest, now: Optional[datetime] = None) -> SearchResponse:
        now = now or now_sg()
        pref = request.preference
        destination = self.resolve_destination(request)
        eligible, message = self._eligible(request, destination)
        if not eligible:
            return SearchResponse(destination_address=request.destination_address,
                                  destination=destination, results=[], message=message)

        ids = [c.carpark_id for c in eligible]
        current = self._availability.get_current_availability_many(ids, pref.lot_type, now)
        nearest = sorted(eligible, key=lambda c: haversine_m(destination.latitude, destination.longitude,
                                                             c.latitude, c.longitude))
        routes = self._walking.get_routes(destination, {c.carpark_id: Location(latitude=c.latitude, longitude=c.longitude)
                                                         for c in nearest[: self._max_routes]})
        results = []
        for c in eligible:
            out = CarparkOut.from_info(c)
            route = routes.get(c.carpark_id)
            results.append(SearchResult(
                carpark=out,
                straight_line_m=round(haversine_m(destination.latitude, destination.longitude, c.latitude, c.longitude)),
                walking_distance_m=route.distance_m if route else None,
                walking_time_min=round(route.duration_s / 60, 1) if route else None,
                walking_time_estimated=False,  # absent route is NOT a walking-time estimate
                estimated_fee_sgd=self._fees.calculate_fee(c.carpark_id, request),
                availability=current.get(c.carpark_id),
                expected_busyness=self._busyness.get_expected_busyness(c.carpark_id, pref.lot_type, request.arrival_time),
                ev_charging=self._ev.get_charging_info(out),
                height_unknown=(bool(pref.vehicle_height_m) and c.gantry_height_m is None
                                and not c.carpark_id.startswith(URA_PREFIX)),   # URA lots have no gantry
            ))
        ranked = self._ranking.rank_carparks(results, pref).sorted_with_tie_break()
        return SearchResponse(destination_address=request.destination_address,
                              destination=destination, results=ranked)
