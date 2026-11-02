"""Plain data objects returned by db/repository.py.

These are what other modules (B, C, D) work with. They are frozen dataclasses,
not ORM objects, so they are safe to pass around after the DB session closes.

Times: every datetime returned here is timezone-aware in Singapore time (+08:00).
Money: Decimal (avoid float rounding in fee calculation).
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Optional

from .models import CapScope, ChargeMode, DayType, LotType, RunStatus, Source

SGT = timezone(timedelta(hours=8), "SGT")


def to_db_time(dt: datetime) -> datetime:
    """Aware datetime -> naive SGT for storage. Naive input is assumed to be SGT."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(SGT)
    return dt.replace(tzinfo=None)


def from_db_time(dt: Optional[datetime]) -> Optional[datetime]:
    """Naive SGT from MySQL -> aware SGT."""
    return None if dt is None else dt.replace(tzinfo=SGT)


@dataclass(frozen=True)
class CarparkInfo:
    carpark_id: str
    name: str
    address: Optional[str]
    latitude: float
    longitude: float
    carpark_type: Optional[str]
    parking_system: Optional[str]
    operator: Optional[str]
    gantry_height_m: Optional[float]
    free_parking: Optional[str]
    night_parking: Optional[bool]
    has_ev_charging: Optional[bool]
    rate_scheme_id: Optional[int]
    short_term_parking: Optional[str] = None   # 'WHOLE_DAY', 'NO' (no short-term parking), hours like '7AM_10_30PM'; None = unknown


@dataclass(frozen=True)
class NearbyCarpark:
    carpark: CarparkInfo
    straight_line_m: float          # haversine distance, NOT walking distance (C gets that from OneMap)


@dataclass(frozen=True)
class RateRuleInfo:
    rule_id: int
    rate_scheme_id: int
    lot_type: LotType
    day_type: DayType
    start_time: time
    end_time: time                  # end_time <= start_time means the window crosses midnight
    charge_mode: ChargeMode
    rate_sgd: Decimal
    interval_min: Optional[int]
    per_minute: bool
    first_interval_min: Optional[int]
    first_rate_sgd: Optional[Decimal]
    cap_sgd: Optional[Decimal]
    cap_scope: Optional[CapScope]
    grace_min: Optional[int]
    priority: int


@dataclass(frozen=True)
class AvailabilityReading:
    """One live reading. Used both as poller input and as read output."""
    carpark_id: str
    lot_type: LotType
    available_lots: int
    total_lots: Optional[int]
    observed_at: datetime           # source's own update time
    collected_at: datetime          # when we fetched it


@dataclass(frozen=True)
class HistoricalAvailability:
    """One stored observation (BACKEND_INTERFACES: HistoricalAvailability)."""
    carpark_id: str
    lot_type: LotType
    available_lots: int
    total_lots: Optional[int]       # None when the source gives no total
    timestamp: datetime             # when the source observed it (+08:00)


@dataclass(frozen=True)
class OccupancyStats:
    mean_occupancy_pct: float       # 0-100
    sample_count: int               # number of readings used; D decides the minimum for a reliable estimate


@dataclass(frozen=True)
class CollectionRunInfo:
    run_id: int
    source: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: RunStatus
    rows_inserted: int
    error_message: Optional[str]


__all__ = [
    "SGT", "to_db_time", "from_db_time", "CarparkInfo", "NearbyCarpark",
    "RateRuleInfo", "AvailabilityReading", "HistoricalAvailability", "OccupancyStats", "CollectionRunInfo",
    "LotType", "Source", "DayType", "ChargeMode", "CapScope", "RunStatus",
]
