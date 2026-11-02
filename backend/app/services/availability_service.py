"""AvailabilityService «control»: current availability from the latest stored reading (UC-04).

Reads the database (refreshed every 10 min by HistoricalAvailabilityCollector) instead of
calling data.gov.sg on every search: faster, no rate limits, already split by lot type.
"""
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.db.records import AvailabilityReading
from app.repositories.carpark_repository import LotTypeLike
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository
from app.schemas.carpark import Availability
from app.utils.timeutil import now_sg

STALE_AFTER = timedelta(minutes=15)   # FR6.3 / NFR-P2: older data is flagged "may be outdated"


def to_availability(r: AvailabilityReading, now: datetime) -> Availability:
    occ = None
    if r.total_lots:
        occ = round(100 * (r.total_lots - min(r.available_lots, r.total_lots)) / r.total_lots)
    return Availability(available_lots=r.available_lots, total_lots=r.total_lots, occupancy_pct=occ,
                        last_updated=r.observed_at, is_stale=now - r.observed_at > STALE_AFTER)


class AvailabilityService:
    def __init__(self, repo: HistoricalAvailabilityRepository):
        self._repo = repo

    def get_current_availability_many(self, carpark_ids: Iterable[str], lot_type: LotTypeLike,
                                      now: Optional[datetime] = None) -> dict[str, Availability]:
        """One query for all candidates. Missing carpark -> no data (UC-04 AF1: Unknown)."""
        now = now or now_sg()
        return {cid: to_availability(r, now)
                for cid, r in self._repo.get_latest_availability(carpark_ids, lot_type).items()}

    def get_current_availability(self, carpark_id: str, lot_type: LotTypeLike) -> Optional[Availability]:
        return self.get_current_availability_many([carpark_id], lot_type).get(carpark_id)
