"""SearchService with in-memory fakes for the repositories and OneMap."""
from datetime import timedelta

import pytest

from app.db.models import LotType
from app.db.records import AvailabilityReading, HistoricalAvailability
from app.exceptions import AddressNotFoundError, MultipleDestinationsError
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch
from app.services.availability_service import AvailabilityService
from app.services.busyness_estimator import BusynessEstimator
from app.services.ev_charging_service import EVChargingService
from app.services.fee_calculator import FeeCalculator
from app.services.ranking_engine import RankingEngine
from app.services.search_service import NO_CARPARKS, NONE_MATCH, SearchService
from app.services.walking_service import WalkingService
from app.utils.geo import haversine_m
from tests.helpers import MONDAY_1PM, FakeMap, make_info, make_request, rule

DEST = (1.3010, 103.8541)


class FakeCarparks:
    def __init__(self, carparks, lot_types=None, rules=None):
        self.carparks, self.lot_types, self.rules = carparks, lot_types or {}, rules or {}

    def get_nearby_carparks(self, loc, radius_m=1000, *, carpark_types=None, ev_required=False):
        out = [c for c in self.carparks
               if haversine_m(loc.latitude, loc.longitude, c.latitude, c.longitude) <= radius_m]
        if carpark_types:
            out = [c for c in out if c.carpark_type in carpark_types]
        if ev_required:
            out = [c for c in out if c.has_ev_charging]
        return out

    def get_lot_types(self, ids):
        return {i: self.lot_types[i] for i in ids if i in self.lot_types}

    def get_rate_rules(self, cid, lot_type):
        return self.rules.get(cid, [])


class FakeAvailability:
    def __init__(self, latest=None, history=None):
        self.latest, self.history = latest or {}, history or {}

    def get_latest_availability(self, ids, lot_type):
        return {i: self.latest[i] for i in ids if i in self.latest}

    def get_historical_records(self, cid, lot_type, arrival):
        return self.history.get(cid, [])


def service(carparks, avail=None, map_=None, **kw):
    avail = avail or FakeAvailability()
    m = map_ or FakeMap()
    return SearchService(m, carparks, FeeCalculator(carparks), AvailabilityService(avail),
                         BusynessEstimator(avail), EVChargingService(), RankingEngine(), WalkingService(m), **kw)


A = make_info("HDB:A", 1.3015, 103.8545)                      # ~70 m away
B = make_info("HDB:B", 1.3050, 103.8541, gantry_height_m=1.8)  # ~450 m, low gantry
M = make_info("HDB:M", 1.3020, 103.8530)                      # motorcycle lots only
FAR = make_info("HDB:FAR", 1.3200, 103.8541)                  # ~2 km away


def test_filters_lot_type_height_and_radius_and_keeps_unknown_fee_unavailable():
    repo = FakeCarparks([A, B, M, FAR], lot_types={"HDB:M": {LotType.MOTORCYCLE}, "HDB:A": {LotType.CAR}},
                        rules={"HDB:B": [rule(per_minute=True)]})
    walk = FakeMap(minutes={(1.3015, 103.8545): 3, (1.305, 103.8541): 6})
    res = service(repo, map_=walk).search_carparks(make_request(), now=MONDAY_1PM)
    assert [r.carpark.carpark_id for r in res.results] == ["HDB:A", "HDB:B"]
    a, b = res.results
    assert a.estimated_fee_sgd is None and a.walking_time_min == 3.0 and a.rank == 1   # Unavailable, not $0
    assert str(b.estimated_fee_sgd) == "2.40"

    tall = make_request(preference={"vehicle_height_m": 2.0})
    assert [r.carpark.carpark_id for r in service(repo).search_carparks(tall).results] == ["HDB:A"]


def test_availability_staleness_and_expected_busyness():
    old = MONDAY_1PM - timedelta(minutes=20)
    latest = {"HDB:A": AvailabilityReading("HDB:A", LotType.CAR, 10, 100, old, old)}
    history = {"HDB:A": [HistoricalAvailability("HDB:A", LotType.CAR, 40, 100, old - timedelta(days=7 * k))
                         for k in range(1, 4)]}
    res = service(FakeCarparks([A]), FakeAvailability(latest, history)).search_carparks(make_request(), now=MONDAY_1PM)
    r = res.results[0]
    assert r.availability.is_stale and r.availability.occupancy_pct == 90
    assert (r.expected_busyness.occupancy_pct, r.expected_busyness.level) == (60, "LOW")


def test_no_carparks_within_1km_message():
    res = service(FakeCarparks([FAR])).search_carparks(make_request())
    assert res.results == [] and res.message == NO_CARPARKS.format(km=1)


def test_all_excluded_by_requirements_message():
    res = service(FakeCarparks([A])).search_carparks(make_request(preference={"ev_required": True}))
    assert res.results == [] and res.message == NONE_MATCH.format(km=1)


def test_destination_resolution():
    two = [PlaceMatch(name="NTU NORTH SPINE", location=Location(latitude=1.347, longitude=103.680)),
           PlaceMatch(name="NTU SOUTH SPINE", location=Location(latitude=1.342, longitude=103.682))]
    with pytest.raises(MultipleDestinationsError) as e:
        service(FakeCarparks([]), map_=FakeMap(matches=two)).search_carparks(make_request(destination_address="NTU"))
    assert len(e.value.matches) == 2
    picked = make_request(destination_address="NTU", destination_location={"latitude": DEST[0], "longitude": DEST[1]})
    assert service(FakeCarparks([A]), map_=FakeMap(matches=two)).search_carparks(picked).results
    exact = make_request(destination_address="ntu north spine")
    assert service(FakeCarparks([]), map_=FakeMap(matches=two)).search_carparks(exact).destination.latitude == 1.347
    with pytest.raises(AddressNotFoundError):
        service(FakeCarparks([]), map_=FakeMap(matches=[])).search_carparks(make_request())
