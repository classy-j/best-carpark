"""Person A's interfaces from docs/BACKEND_INTERFACES.md.

    from db.repositories import CarparkRepository, HistoricalAvailabilityRepository

Method names follow Python style (snake_case) for the camelCase names in the doc:
    CarparkRepository.getNearbyCarparks                -> get_nearby_carparks
    CarparkRepository.getCarparkById                   -> get_carpark_by_id
    HistoricalAvailabilityRepository.saveAvailabilityRecord -> save_availability_record
    HistoricalAvailabilityRepository.getHistoricalRecords   -> get_historical_records

Extras not in the doc (needed by other modules):
    CarparkRepository.get_rate_rules                      -> FeeCalculator (B)
    HistoricalAvailabilityRepository.get_latest_availability -> AvailabilityService (D)
"""
from datetime import datetime
from typing import Iterable, Optional, Sequence, Union

from . import repository as _r
from .models import LotType
from .records import (
    SGT, AvailabilityReading, CarparkInfo, HistoricalAvailability, RateRuleInfo,
)

LotTypeLike = Union[LotType, str]          # LotType.CAR or "CAR"


def _lot(lot_type: LotTypeLike) -> LotType:
    return lot_type if isinstance(lot_type, LotType) else LotType(lot_type)


def _lat_lng(location) -> tuple[float, float]:
    """Accepts any object with .latitude/.longitude, a dict with those keys, or a (lat, lng) tuple."""
    if isinstance(location, (tuple, list)):
        return float(location[0]), float(location[1])
    if isinstance(location, dict):
        return float(location["latitude"]), float(location["longitude"])
    return float(location.latitude), float(location.longitude)


class CarparkRepository:

    def get_nearby_carparks(
        self,
        destination_location,
        radius_m: float = 1000,
        *,
        carpark_types: Optional[Sequence[str]] = None,
        ev_required: bool = False,
        include_season_only: bool = False,
    ) -> list[CarparkInfo]:
        """Carparks within radius_m (straight line) of the destination, nearest first.
        Season-parking-only carparks are excluded unless include_season_only=True."""
        lat, lng = _lat_lng(destination_location)
        return [n.carpark for n in _r.find_carparks_near(
            lat, lng, radius_m, carpark_types=carpark_types, ev_required=ev_required,
            include_season_only=include_season_only)]

    def get_carpark_by_id(self, carpark_id: str) -> Optional[CarparkInfo]:
        return _r.get_carpark(carpark_id)

    def get_rate_rules(self, carpark_id: str, lot_type: LotTypeLike) -> list[RateRuleInfo]:
        """Rate rules for FeeCalculator. Empty list -> fee is null."""
        return _r.get_rate_rules(carpark_id, _lot(lot_type))


class HistoricalAvailabilityRepository:

    def save_availability_record(
        self,
        carpark_id: str,
        lot_type: LotTypeLike,
        available_lots: int,
        total_lots: Optional[int],
        timestamp: datetime,
    ) -> None:
        """Store one observation (duplicates of an existing observation are ignored)."""
        _r.record_availability([AvailabilityReading(
            carpark_id, _lot(lot_type), available_lots, total_lots, timestamp, datetime.now(SGT))])

    def save_availability_records(self, readings: Sequence[AvailabilityReading]) -> int:
        """Batch version used by the collector. Returns the number of new records."""
        return _r.record_availability(readings)

    def get_historical_records(
        self,
        carpark_id: str,
        lot_type: LotTypeLike,
        arrival_time: datetime,
        *,
        window_minutes: int = 15,
        lookback_days: int = 56,
    ) -> list[HistoricalAvailability]:
        """Past observations on the same weekday within +/- window_minutes of the
        arrival time of day, from the last lookback_days days. Oldest first."""
        return _r.get_historical_records(carpark_id, _lot(lot_type), arrival_time,
                                         window_slots=max(window_minutes // 15, 0),
                                         lookback_days=lookback_days)

    def get_latest_availability(
        self, carpark_ids: Iterable[str], lot_type: LotTypeLike
    ) -> dict[str, AvailabilityReading]:
        """Most recent stored observation per carpark (missing key = no data)."""
        return _r.get_latest_availability(carpark_ids, _lot(lot_type))
