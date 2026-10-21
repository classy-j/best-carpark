"""CarparkRepository «persistent store»: the only class that reads carparks and rates.

Returns plain dataclasses (app.db.records), never ORM rows.
"""
from typing import Iterable, Optional, Sequence, Union

from app.db import repository as _r
from app.db.models import LotType
from app.db.records import CarparkInfo, RateRuleInfo

LotTypeLike = Union[LotType, str]          # LotType.CAR or "CAR"


def as_lot_type(lot_type: LotTypeLike) -> LotType:
    return lot_type if isinstance(lot_type, LotType) else LotType(lot_type)


def _lat_lng(location) -> tuple[float, float]:
    """Accepts an object with .latitude/.longitude, a dict with those keys, or a (lat, lng) tuple."""
    if isinstance(location, (tuple, list)):
        return float(location[0]), float(location[1])
    if isinstance(location, dict):
        return float(location["latitude"]), float(location["longitude"])
    return float(location.latitude), float(location.longitude)


class CarparkRepository:

    def get_nearby_carparks(
        self,
        location,
        radius_m: float = 1000,
        *,
        carpark_types: Optional[Sequence[str]] = None,
        ev_required: bool = False,
        include_season_only: bool = False,
    ) -> list[CarparkInfo]:
        """Carparks within radius_m (real straight-line distance, not a box) of the location,
        nearest first. Season-parking-only carparks are excluded unless include_season_only."""
        lat, lng = _lat_lng(location)
        return [n.carpark for n in _r.find_carparks_near(
            lat, lng, radius_m, carpark_types=carpark_types, ev_required=ev_required,
            include_season_only=include_season_only)]

    def get_carpark_by_id(self, carpark_id: str) -> Optional[CarparkInfo]:
        return _r.get_carpark(carpark_id)

    def get_rate_rules(self, carpark_id: str, lot_type: LotTypeLike) -> list[RateRuleInfo]:
        """Rate rules for FeeCalculator. Empty list -> fee unavailable."""
        return _r.get_rate_rules(carpark_id, as_lot_type(lot_type))

    def get_lot_types(self, carpark_ids: Iterable[str]) -> dict[str, set[LotType]]:
        """Lot types known per carpark (absent = unknown). Used for the lot-type filter (FR4.3)."""
        return _r.get_lot_types(carpark_ids)
