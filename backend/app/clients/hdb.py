"""HdbAdapter: realizes CarparkDataSource using data.gov.sg (HDB carpark info + live
and historical availability). HTTP and parsing live in hdb_data.py."""
from datetime import datetime
from typing import Callable, Iterable, Optional

from app.clients import hdb_data
from app.db.records import AvailabilityReading, CarparkInfo


class HdbAdapter:
    def fetch_carparks(self) -> list[tuple[CarparkInfo, str]]:
        """(carpark, HDB car_park_no) for every usable row of the HDB Carpark Information dataset."""
        records = hdb_data.fetch_carpark_info_records()
        return [p for p in (hdb_data.parse_carpark_info(r) for r in records) if p is not None]

    def fetch_availability(
        self, resolve_ids: Callable[[Iterable[str]], dict[str, str]], at: Optional[datetime] = None
    ) -> list[AvailabilityReading]:
        """Live availability, or the snapshot at time `at` (data.gov.sg keeps history).
        resolve_ids maps HDB car_park_no -> our carpark_id; unknown carparks are skipped."""
        payload = hdb_data.fetch_availability(at)
        readings, _unknown = hdb_data.parse_availability(payload, resolve_ids(hdb_data.availability_refs(payload)))
        return readings
