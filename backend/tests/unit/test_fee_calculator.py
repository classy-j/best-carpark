"""FeeCalculator against HDB's published charges (see app/collectors/seed_rates.py)."""
from datetime import datetime, time
from decimal import Decimal

from app.db.models import CapScope, ChargeMode, DayType, LotType
from app.db.records import SGT
from app.services.fee_calculator import compute_fee
from tests.helpers import rule


def t(day, hh, mm=0):              # 19 Oct 2026 is a Monday, 25 Oct a Sunday
    return datetime(2026, 10, day, hh, mm, tzinfo=SGT)


EPS = dict(per_minute=True, grace=15)
DAY_CAP = dict(cap="12.00", cap_scope=CapScope.DAY)
NIGHT = rule(2, start=time(22, 30), end=time(7), cap="5.00", cap_scope=CapScope.WINDOW, **EPS)
STANDARD = [rule(1, **EPS, **DAY_CAP), NIGHT]


def test_standard_per_minute():
    assert compute_fee(STANDARD, t(19, 13), t(19, 15)) == Decimal("2.40")        # 120 min x $0.02
    assert compute_fee(STANDARD, t(19, 13), t(19, 13, 16)) == Decimal("0.32")


def test_grace_period_is_free():
    assert compute_fee(STANDARD, t(19, 13), t(19, 13, 10)) == Decimal("0.00")


def test_day_cap():
    assert compute_fee(STANDARD, t(19, 8), t(19, 22)) == Decimal("12.00")        # 16.80 capped


def test_overnight_uses_night_cap_and_next_day():
    # 20:00-22:30 = 3.00, night 22:30-07:00 = 10.20 -> capped 5.00, 07:00-09:00 = 2.40
    assert compute_fee(STANDARD, t(19, 20), t(20, 9)) == Decimal("10.40")


def test_coupon_charges_per_started_half_hour():
    assert compute_fee([rule(1)], t(19, 13), t(19, 13, 40)) == Decimal("1.20")


def test_central_area_peak_rate_and_sunday():
    rules = [rule(1, DayType.WEEKDAY, time(7), time(17), rate="1.20", cap="20.00", cap_scope=CapScope.DAY, **EPS),
             rule(2, DayType.WEEKDAY, time(17), time(22, 30), cap="20.00", cap_scope=CapScope.DAY, **EPS),
             rule(3, DayType.SUNDAY_PH, time(7), time(22, 30), cap="20.00", cap_scope=CapScope.DAY, **EPS)]
    assert compute_fee(rules, t(19, 16), t(19, 18)) == Decimal("3.60")            # 2.40 + 1.20
    assert compute_fee(rules, t(25, 16), t(25, 18)) == Decimal("2.40")


def test_free_parking_on_sunday_and_holidays():
    rules = STANDARD + [rule(9, DayType.SUNDAY_PH, mode=ChargeMode.FREE, rate="0", interval=None, priority=10)]
    assert compute_fee(rules, t(25, 10), t(25, 12)) == Decimal("0.00")
    assert compute_fee(rules, t(19, 10), t(19, 12)) == Decimal("2.40")
    holiday = datetime(2026, 10, 19).date()
    assert compute_fee(rules, t(19, 10), t(19, 12), holidays={holiday}) == Decimal("0.00")


def test_no_short_term_parking_at_that_time_is_unavailable():
    assert compute_fee([rule(1, **EPS)], t(19, 22), t(19, 23)) is None             # no night parking


def test_no_rules_is_unavailable_not_zero():
    assert compute_fee([], t(19, 13), t(19, 15)) is None


def test_motorcycle_per_entry_each_window():
    rules = [rule(1, mode=ChargeMode.PER_ENTRY, rate="0.65", interval=None, lot=LotType.MOTORCYCLE),
             rule(2, start=time(22, 30), end=time(7), mode=ChargeMode.PER_ENTRY, rate="0.65",
                  interval=None, lot=LotType.MOTORCYCLE)]
    assert compute_fee(rules, t(19, 13), t(19, 15)) == Decimal("0.65")
    assert compute_fee(rules, t(19, 20), t(20, 8)) == Decimal("1.95")
