"""HistoricalAvailabilityRepository «persistent store»: availability history + latest readings."""
from datetime import datetime
from typing import Iterable, Sequence

from app.db import repository as _r
from app.db.records import AvailabilityReading, HistoricalAvailability
from app.repositories.carpark_repository import LotTypeLike, as_lot_type


class HistoricalAvailabilityRepository:

    def save_availability_records(self, readings: Sequence[AvailabilityReading]) -> int:
        """Append to history (duplicates skipped) and refresh the latest reading when newer.
        Returns the number of NEW history rows."""
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
        """Past observations on the same weekday within +/- window_minutes of the arrival
        time of day, from the last lookback_days days. Oldest first."""
        return _r.get_historical_records(carpark_id, as_lot_type(lot_type), arrival_time,
                                         window_slots=max(window_minutes // 15, 0),
                                         lookback_days=lookback_days)

    def get_latest_availability(
        self, carpark_ids: Iterable[str], lot_type: LotTypeLike
    ) -> dict[str, AvailabilityReading]:
        """Most recent stored reading per carpark (missing key = no data)."""
        return _r.get_latest_availability(carpark_ids, as_lot_type(lot_type))
