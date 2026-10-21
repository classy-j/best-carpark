"""BusynessEstimator «control»: expected availability at the arrival time (UC-05, FR5.2).

Average occupancy of past readings on the same weekday and 15-minute slot (last 8 weeks).
Not a prediction model: a typical value, labelled "Expected" in the UI (FR5.3, NFR-U2).
"""
from datetime import datetime
from typing import Optional, Sequence

from app.db.records import HistoricalAvailability
from app.repositories.carpark_repository import LotTypeLike
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository
from app.schemas.carpark import ExpectedBusyness

MIN_SAMPLES = 3          # fewer usable records -> Unavailable (UC-05 EX1)
HIGH_ABOVE = 90          # occupancy %: >90 HIGH, >70 MODERATE, else LOW
MODERATE_ABOVE = 70


class BusynessEstimator:
    def __init__(self, repo: HistoricalAvailabilityRepository):
        self._repo = repo

    @staticmethod
    def estimate_busyness(records: Sequence[HistoricalAvailability],
                          arrival: datetime) -> Optional[ExpectedBusyness]:
        usable = [r for r in records if r.total_lots and r.total_lots > 0]
        if len(usable) < MIN_SAMPLES:
            return None
        # occupancy per record, so a change in total lots over time doesn't skew the average
        occ = [100 * (r.total_lots - min(r.available_lots, r.total_lots)) / r.total_lots for r in usable]
        pct = round(sum(occ) / len(occ))
        level = "HIGH" if pct > HIGH_ABOVE else "MODERATE" if pct > MODERATE_ABOVE else "LOW"
        return ExpectedBusyness(occupancy_pct=pct, level=level, sample_count=len(usable))

    def get_expected_busyness(self, carpark_id: str, lot_type: LotTypeLike,
                              arrival: datetime) -> Optional[ExpectedBusyness]:
        return self.estimate_busyness(self._repo.get_historical_records(carpark_id, lot_type, arrival), arrival)
