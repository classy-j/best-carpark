"""The classes named in docs/BACKEND_INTERFACES.md."""
from datetime import datetime, timedelta

from collector.load_carparks import load
from db.models import LotType
from db.records import SGT
from db.repositories import CarparkRepository, HistoricalAvailabilityRepository
from test_hdb_collector import INFO_RECORDS


class Location:
    def __init__(self, latitude, longitude):
        self.latitude, self.longitude = latitude, longitude


def test_carpark_repository():
    load(INFO_RECORDS)
    repo = CarparkRepository()
    for loc in (Location(1.3010, 103.8541), (1.3010, 103.8541), {"latitude": 1.3010, "longitude": 103.8541}):
        assert [c.carpark_id for c in repo.get_nearby_carparks(loc, 500)] == ["HDB:ACB"]
    assert repo.get_carpark_by_id("HDB:ACB").name.startswith("BLK 270/271")
    assert repo.get_carpark_by_id("NOPE") is None
    assert repo.get_rate_rules("HDB:ACB", "CAR") == []          # not seeded in this test


def test_historical_availability_repository():
    load(INFO_RECORDS)
    repo = HistoricalAvailabilityRepository()
    last_week = datetime.now(SGT).replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=7)
    repo.save_availability_record("HDB:ACB", "CAR", 30, 100, last_week)
    repo.save_availability_record("HDB:ACB", LotType.CAR, 50, 100, last_week - timedelta(days=7, minutes=-10))
    repo.save_availability_record("HDB:ACB", "CAR", 30, 100, last_week)                # duplicate: ignored
    repo.save_availability_record("HDB:ACB", "CAR", 0, 100, last_week + timedelta(hours=4))  # other time

    arrival = last_week + timedelta(days=7, minutes=5)
    records = repo.get_historical_records("HDB:ACB", "CAR", arrival)
    assert [r.available_lots for r in records] == [50, 30]                            # oldest first
    assert all(r.timestamp.utcoffset() == timedelta(hours=8) for r in records)
    assert repo.get_historical_records("HDB:ACB", "CAR", arrival + timedelta(days=1)) == []
    assert repo.get_latest_availability(["HDB:ACB"], "CAR")["HDB:ACB"].available_lots == 0
