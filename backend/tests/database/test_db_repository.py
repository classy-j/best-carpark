from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.db import repository as repo
from app.db.models import ChargeMode, CapScope, DayType, LotType, RateRule, RateScheme, RunStatus, Source
from app.db.session import session_scope
from app.db.records import SGT, AvailabilityReading, CarparkInfo

DEST = (1.3000, 103.8500)


def cp(cid, lat, lng, **kw):
    base = dict(carpark_id=cid, name=cid, address=None, latitude=lat, longitude=lng,
                carpark_type="MULTI_STOREY", parking_system="ELECTRONIC", operator="HDB",
                gantry_height_m=2.1, free_parking="NO", night_parking=True,
                has_ev_charging=None, rate_scheme_id=None)
    base.update(kw)
    return CarparkInfo(**base)


def load_sample_carparks():
    lat, lng = DEST
    repo.upsert_carparks(Source.HDB, [
        (cp("HDB:NEAR", lat + 0.0027, lng, has_ev_charging=True), "NEAR"),             # ~300 m
        (cp("HDB:MID", lat + 0.0080, lng, carpark_type="SURFACE"), "MID"),             # ~890 m
        (cp("HDB:FAR", lat + 0.0110, lng), "FAR"),                                     # ~1225 m
        (cp("HDB:CORNER", lat + 0.0080, lng + 0.0080), "CORNER"),                      # in box, ~1260 m
    ])


def recent(weekday_iso: int, hh: int, mm: int, weeks_ago: int) -> datetime:
    """A past datetime on the given ISO weekday (Mon=1..Sun=7), weeks_ago weeks back."""
    now = datetime.now(SGT)
    days_back = (now.isoweekday() - weekday_iso) % 7 + 7 * weeks_ago
    d = (now - timedelta(days=days_back)).date()
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=SGT)


# ---------------------------------------------------------------- carparks

def test_upsert_get_and_source_mapping():
    load_sample_carparks()
    c = repo.get_carpark("HDB:NEAR")
    assert c is not None and c.has_ev_charging is True and c.latitude == 1.3027
    assert repo.get_carpark("NOPE") is None
    assert repo.resolve_carpark_ids(Source.HDB, ["NEAR", "MID", "UNKNOWN"]) == {
        "NEAR": "HDB:NEAR", "MID": "HDB:MID"}


def test_reload_updates_fields_but_keeps_ev_flag():
    load_sample_carparks()
    # A later HDB reload doesn't know EV status (None) and renames the carpark
    repo.upsert_carparks(Source.HDB, [(cp("HDB:NEAR", 1.3027, 103.85, name="RENAMED"), "NEAR")])
    c = repo.get_carpark("HDB:NEAR")
    assert c.name == "RENAMED"
    assert c.has_ev_charging is True  # not wiped by the NULL


def test_find_near_radius_order_and_filters():
    load_sample_carparks()
    near = repo.find_carparks_near(*DEST)
    assert [n.carpark.carpark_id for n in near] == ["HDB:NEAR", "HDB:MID"]  # FAR and CORNER excluded
    assert 280 < near[0].straight_line_m < 320
    assert [n.carpark.carpark_id for n in repo.find_carparks_near(*DEST, carpark_types=["SURFACE"])] == ["HDB:MID"]
    assert [n.carpark.carpark_id for n in repo.find_carparks_near(*DEST, ev_required=True)] == ["HDB:NEAR"]
    assert len(repo.find_carparks_near(*DEST, radius_m=2000)) == 4


# ---------------------------------------------------------------- rates

def test_rate_rules():
    with session_scope() as s:
        scheme = RateScheme(name="HDB_NONCENTRAL_EPS", source="MANUAL")
        s.add(scheme)
        s.flush()
        s.add_all([
            RateRule(rate_scheme_id=scheme.rate_scheme_id, lot_type=LotType.CAR, day_type=DayType.ALL,
                     start_time=time(7), end_time=time(22, 30), charge_mode=ChargeMode.PER_INTERVAL,
                     rate_sgd=Decimal("0.60"), interval_min=30, per_minute=True,
                     cap_sgd=Decimal("12.00"), cap_scope=CapScope.WINDOW, grace_min=15),
            RateRule(rate_scheme_id=scheme.rate_scheme_id, lot_type=LotType.CAR, day_type=DayType.ALL,
                     start_time=time(22, 30), end_time=time(7), charge_mode=ChargeMode.PER_INTERVAL,
                     rate_sgd=Decimal("0.60"), interval_min=30, per_minute=True,
                     cap_sgd=Decimal("5.00"), cap_scope=CapScope.WINDOW, grace_min=15, priority=1),
        ])
        scheme_id = scheme.rate_scheme_id
    repo.upsert_carparks(Source.HDB, [(cp("HDB:X", 1.3, 103.85, rate_scheme_id=scheme_id), "X"),
                                      (cp("HDB:NOPRICE", 1.3, 103.85), "NOPRICE")])
    rules = repo.get_rate_rules("HDB:X", LotType.CAR)
    assert len(rules) == 2
    assert rules[0].cap_sgd == Decimal("5.00")          # priority 1 first
    assert rules[0].end_time < rules[0].start_time      # crosses midnight
    assert repo.get_rate_rules("HDB:X", LotType.MOTORCYCLE) == []
    assert repo.get_rate_rules("HDB:NOPRICE", LotType.CAR) == []


# ---------------------------------------------------------------- availability

def reading(cid, avail, total, observed, collected=None):
    return AvailabilityReading(cid, LotType.CAR, avail, total, observed, collected or observed)


def test_record_availability_dedupes_and_keeps_newest_latest():
    load_sample_carparks()
    t1 = datetime(2026, 10, 9, 13, 58, tzinfo=SGT)
    t2 = t1 + timedelta(minutes=10)
    assert repo.record_availability([reading("HDB:NEAR", 47, 100, t1)]) == 1
    assert repo.record_availability([reading("HDB:NEAR", 47, 100, t1)]) == 0   # same reading again
    assert repo.record_availability([reading("HDB:NEAR", 40, 100, t2)]) == 1
    assert repo.record_availability([reading("HDB:NEAR", 99, 100, t1 - timedelta(hours=1))]) == 1  # late, older
    latest = repo.get_latest_availability(["HDB:NEAR", "HDB:MID"], LotType.CAR)
    assert set(latest) == {"HDB:NEAR"}                  # MID has no data -> absent
    assert latest["HDB:NEAR"].available_lots == 40      # older reading did not overwrite
    assert latest["HDB:NEAR"].observed_at == t2
    assert latest["HDB:NEAR"].observed_at.utcoffset() == timedelta(hours=8)


def test_utc_input_stored_as_singapore_time():
    load_sample_carparks()
    utc = datetime(2026, 10, 9, 6, 0, tzinfo=timezone.utc)   # = 14:00 SGT
    repo.record_availability([reading("HDB:NEAR", 10, 100, utc)])
    got = repo.get_latest_availability(["HDB:NEAR"], LotType.CAR)["HDB:NEAR"].observed_at
    assert (got.hour, got.utcoffset()) == (14, timedelta(hours=8))


def test_historical_occupancy():
    load_sample_carparks()
    FRI = 5
    repo.record_availability([
        reading("HDB:NEAR", 30, 100, recent(FRI, 14, 0, 1)),    # 70 %
        reading("HDB:NEAR", 50, 100, recent(FRI, 14, 10, 2)),   # 50 %
        reading("HDB:NEAR", 0, 100, recent(FRI, 18, 0, 1)),     # other time -> ignored
        reading("HDB:NEAR", 0, None, recent(FRI, 14, 5, 3)),    # no total -> ignored
        reading("HDB:NEAR", 0, 100, recent(FRI, 14, 0, 20)),    # older than 8 weeks -> ignored
        reading("HDB:NEAR", 0, 100, recent(4, 14, 0, 1)),       # Thursday -> ignored
    ])
    future_friday = recent(FRI, 14, 5, 0) + timedelta(days=7)
    stats = repo.get_historical_occupancy("HDB:NEAR", LotType.CAR, future_friday)
    assert stats is not None
    assert stats.sample_count == 2
    assert stats.mean_occupancy_pct == 60.0
    assert repo.get_historical_occupancy("HDB:MID", LotType.CAR, future_friday) is None


def test_collection_runs():
    run = repo.start_collection_run("HDB")
    assert repo.get_last_successful_run("HDB") is None
    repo.finish_collection_run(run, RunStatus.OK, rows_inserted=2000)
    last = repo.get_last_successful_run("HDB")
    assert last.run_id == run and last.rows_inserted == 2000 and last.finished_at is not None
    failed = repo.start_collection_run("HDB")
    repo.finish_collection_run(failed, RunStatus.FAILED, 0, "timeout")
    assert repo.get_last_successful_run("HDB").run_id == run
