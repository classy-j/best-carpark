from datetime import time
from decimal import Decimal

from sqlalchemy import func, select

from app.collectors.load_carparks import load
from app.collectors.seed_rates import parse_window, seed, spec_for
from app.db import repository as repo
from app.db.models import CapScope, ChargeMode, DayType, LotType, RateRule, RateScheme
from app.db.session import session_scope
from tests.database.test_hdb_collector import INFO_RECORDS

ACB, ACM, AH1 = INFO_RECORDS          # ACB = Central Area; ACM, AH1 = free on Sun/PH


def row(**kw):
    return {**ACM, **kw}


def car_rules(spec, day_type=None):
    return [r for r in spec.rules if r.lot_type == LotType.CAR and (day_type is None or r.day_type == day_type)]


def test_parse_window():
    assert parse_window("7AM-10.30PM") == (time(7), time(22, 30))
    assert parse_window("SUN & PH FR 1PM-10.30PM") == (time(13), time(22, 30))
    assert parse_window("WHOLE DAY") is None


def test_central_area_scheme():
    spec = spec_for(ACB)
    assert spec.central and spec.electronic and spec.night and spec.free is None
    weekday = sorted(car_rules(spec, DayType.WEEKDAY), key=lambda r: r.start)
    assert [(r.start, r.end, r.rate) for r in weekday] == [
        (time(7), time(17), Decimal("1.20")), (time(17), time(22, 30), Decimal("0.60"))]
    assert all(r.cap == Decimal("20.00") and r.cap_scope == CapScope.DAY for r in weekday)
    assert car_rules(spec, DayType.SUNDAY_PH)[0].rate == Decimal("0.60")
    night = [r for r in car_rules(spec, DayType.ALL) if r.start == time(22, 30)][0]
    assert night.end == time(7) and night.cap == Decimal("5.00") and night.cap_scope == CapScope.WINDOW
    assert all(r.per_minute and r.grace == 15 for r in car_rules(spec))


def test_non_central_with_free_parking():
    spec = spec_for(ACM)
    assert not spec.central
    day = [r for r in car_rules(spec, DayType.ALL) if r.start == time(7)][0]
    assert (day.rate, day.cap) == (Decimal("0.60"), Decimal("12.00"))
    free = car_rules(spec, DayType.SUNDAY_PH)
    assert len(free) == 1 and free[0].mode == ChargeMode.FREE and free[0].priority == 10
    moto = [r for r in spec.rules if r.lot_type == LotType.MOTORCYCLE]
    assert {(r.start, r.end) for r in moto} == {(time(7), time(22, 30)), (time(22, 30), time(7))}
    assert all(r.mode == ChargeMode.PER_ENTRY and r.rate == Decimal("0.65") for r in moto)
    heavy = [r for r in spec.rules if r.lot_type == LotType.HEAVY_VEHICLE]
    assert all(r.rate == Decimal("1.20") for r in heavy) and len(heavy) == 2


def test_limited_hours_coupon_and_no_short_term():
    spec = spec_for(row(short_term_parking="7AM-7PM", type_of_parking_system="COUPON PARKING",
                        free_parking="SUN & PH FR 1PM-10.30PM"))
    assert not spec.night                                       # no parking at night
    day = car_rules(spec, DayType.ALL)
    assert [(r.start, r.end) for r in day] == [(time(7), time(19))]
    assert not day[0].per_minute and day[0].grace is None       # coupon
    assert [(r.start, r.end) for r in car_rules(spec, DayType.SUNDAY_PH)] == [(time(13), time(19))]
    assert all(r.end != time(7) for r in spec.rules)            # no overnight rules at all
    assert spec_for(row(short_term_parking="NO")) is None
    no_night = spec_for(row(night_parking="NO"))
    assert not no_night.night and all(r.start != time(22, 30) for r in no_night.rules)


def test_seed_into_db_is_idempotent_and_survives_reload():
    records = INFO_RECORDS + [row(car_park_no="NOST", short_term_parking="NO")]
    load(records)
    first = seed(records)
    assert first["carparks_linked"] == 3 and first["carparks_without_rates"] == 1
    assert first["schemes"] == 2                                # ACM and AH1 share one scheme

    def rule_count():
        with session_scope() as s:
            return s.scalar(select(func.count()).select_from(RateRule))
    n = rule_count()
    assert seed(records) == first and rule_count() == n         # re-run: no duplicates

    acb = repo.get_rate_rules("HDB:ACB", LotType.CAR)
    assert any(r.rate_sgd == Decimal("1.20") for r in acb)
    assert repo.get_rate_rules("HDB:NOST", LotType.CAR) == []
    assert repo.get_carpark("HDB:ACM").rate_scheme_id == repo.get_carpark("HDB:AH1").rate_scheme_id

    load(records)                                               # daily carpark refresh
    assert repo.get_carpark("HDB:ACB").rate_scheme_id is not None
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(RateScheme)) == 2
