from datetime import datetime, timedelta

from collector import backfill as bf
from collector.load_carparks import load
from db import repository as repo
from db.models import LotType
from db.records import SGT
from test_hdb_collector import INFO_RECORDS


def fake_api(calls, drift=timedelta(0)):
    """Mimics the API: answers time t with the snapshot taken just before t."""
    def fetch(at):
        calls.append(at)
        snap = at - timedelta(seconds=23) + drift
        upd = (snap - timedelta(seconds=13)).strftime("%Y-%m-%dT%H:%M:%S")
        return {"items": [{"timestamp": snap.isoformat(), "carpark_data": [
            {"carpark_number": "ACB", "update_datetime": upd,
             "carpark_info": [{"total_lots": "100", "lot_type": "C", "lots_available": str(at.hour)}]},
            {"carpark_number": "ACM", "update_datetime": upd,
             "carpark_info": [{"total_lots": "50", "lot_type": "C", "lots_available": "5"}]},
        ]}]}
    return fetch


def test_target_times_aligned():
    now = datetime(2026, 10, 18, 6, 7, 41, tzinfo=SGT)
    times = bf.target_times(days=1, step_min=15, now=now)
    assert times[0] == datetime(2026, 10, 17, 6, 0, tzinfo=SGT)
    assert times[-1] == datetime(2026, 10, 18, 6, 0, tzinfo=SGT)
    assert len(times) == 97 and times == sorted(times)


def test_backfill_stores_history_and_resumes(monkeypatch):
    load(INFO_RECORDS)
    monkeypatch.setattr(bf, "MIN_ROWS_FOR_COVERED_SLOT", 2)   # our fake snapshot has 2 carparks
    times = bf.target_times(days=2, step_min=60)
    calls = []
    stats = bf.backfill(times, 60, delay_s=0, fetch=fake_api(calls), sleep=lambda s: None)
    assert stats["fetched"] == len(times) and stats["failed"] == 0
    assert stats["rows"] == 2 * len(times)

    # busyness lookup sees the backfilled data (same weekday 1 week later)
    at = times[5] + timedelta(days=7)
    records = repo.get_historical_records("HDB:ACB", LotType.CAR, at)
    assert records and records[0].available_lots == times[5].hour

    calls.clear()
    again = bf.backfill(times, 60, delay_s=0, fetch=fake_api(calls), sleep=lambda s: None)
    assert calls == [] and again["skipped"] == len(times)          # resume: nothing re-fetched


def test_backfill_rejects_wrong_snapshot_and_keeps_going():
    load(INFO_RECORDS)
    times = bf.target_times(days=0, step_min=15, now=datetime(2026, 10, 1, 12, 0, tzinfo=SGT))
    stats = bf.backfill(times, 15, delay_s=0, fetch=fake_api([], drift=timedelta(days=3)),
                        sleep=lambda s: None)
    assert stats == {"fetched": 0, "skipped": 0, "failed": 1, "rows": 0}


def test_midnight_is_requested_one_minute_later():
    load(INFO_RECORDS)
    calls = []
    midnight = datetime(2026, 10, 18, 0, 0, tzinfo=SGT)
    bf.backfill([midnight], 15, delay_s=0, fetch=fake_api(calls), sleep=lambda s: None)
    assert calls == [midnight + timedelta(minutes=1)]


def test_backfill_does_not_overwrite_newer_latest():
    load(INFO_RECORDS)
    now = datetime.now(SGT)
    repo.record_availability([repo.AvailabilityReading("HDB:ACB", LotType.CAR, 77, 100, now, now)])
    bf.backfill(bf.target_times(days=1, step_min=120), 120, delay_s=0, fetch=fake_api([]),
                sleep=lambda s: None)
    assert repo.get_latest_availability(["HDB:ACB"], LotType.CAR)["HDB:ACB"].available_lots == 77
