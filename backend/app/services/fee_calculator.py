"""FeeCalculator «control»: estimated parking fee from the stored rate rules (UC-03, FR3.1-FR3.3).

The rules come from rate_schemes / rate_rules (seeded by collectors/seed_rates.py from HDB's
published charges). A stay is walked minute by minute; consecutive minutes under the same
rule window form a segment, which is charged by that rule. Caps:
  WINDOW - per occurrence of the rule's window (e.g. night cap $5, 22:30-07:00)
  DAY    - per calendar day, summed over all DAY-capped segments that day (e.g. $12 / $20)
  ENTRY  - once per stay
Central Area (FR3.1) is part of the scheme: those carparks are linked to the Central Area rates.

Returns None ("Unavailable") when the carpark has no rules for the lot type, or when part of
the stay falls in a time with no short-term parking at that carpark.
"""
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Iterable, Optional

from app.db.models import CapScope, ChargeMode, DayType
from app.db.records import RateRuleInfo
from app.repositories.carpark_repository import CarparkRepository, LotTypeLike
from app.utils.timeutil import to_sg

if TYPE_CHECKING:
    from app.schemas.search import SearchRequest

CENT = Decimal("0.01")


def day_type_of(d: date, holidays: Iterable[date] = ()) -> DayType:
    if d.weekday() == 6 or d in holidays:
        return DayType.SUNDAY_PH
    return DayType.SATURDAY if d.weekday() == 5 else DayType.WEEKDAY


def _in_window(r: RateRuleInfo, t: time) -> bool:
    if r.start_time < r.end_time:
        return r.start_time <= t < r.end_time
    return t >= r.start_time or t < r.end_time       # window crosses midnight


def _window_start(r: RateRuleInfo, t: datetime) -> datetime:
    """Start of the occurrence of r's window that contains t."""
    start = t.replace(hour=r.start_time.hour, minute=r.start_time.minute, second=0, microsecond=0)
    return start - timedelta(days=1) if start > t else start


def _rule_at(rules: list[RateRuleInfo], t: datetime, holidays) -> Optional[RateRuleInfo]:
    dt = day_type_of(t.date(), holidays)
    matching = [r for r in rules if r.day_type in (dt, DayType.ALL) and _in_window(r, t.time())]
    if not matching:
        return None
    # highest priority first; a rule for the specific day type beats an ALL rule
    return max(matching, key=lambda r: (r.priority, r.day_type != DayType.ALL))


def _segment_charge(r: RateRuleInfo, minutes: int) -> Decimal:
    if r.charge_mode == ChargeMode.FREE:
        return Decimal(0)
    if r.charge_mode == ChargeMode.PER_ENTRY:
        return r.rate_sgd
    charge = Decimal(0)
    if r.first_interval_min and r.first_rate_sgd is not None:
        charge += r.first_rate_sgd
        minutes = max(0, minutes - r.first_interval_min)
    if r.per_minute:
        charge += r.rate_sgd * minutes / r.interval_min
    else:
        charge += r.rate_sgd * math.ceil(minutes / r.interval_min)
    return charge


def compute_fee(rules: list[RateRuleInfo], arrival: datetime, departure: datetime,
                holidays: Iterable[date] = ()) -> Optional[Decimal]:
    if not rules:
        return None
    arrival, departure = to_sg(arrival).replace(second=0, microsecond=0), to_sg(departure)
    total = math.ceil((departure - arrival).total_seconds() / 60)
    if total <= 0:
        return Decimal("0.00")
    grace = max((r.grace_min or 0) for r in rules)
    if total <= grace:
        return Decimal("0.00")

    # 1. split the stay into segments: (rule, window occurrence) -> minutes
    segments: dict[tuple[int, datetime], list] = {}
    order = []
    for i in range(total):
        t = arrival + timedelta(minutes=i)
        r = _rule_at(rules, t, holidays)
        if r is None:
            return None                                  # no short-term parking at this time
        key = (r.rule_id, _window_start(r, t))
        if key not in segments:
            segments[key] = [r, 0]
            order.append(key)
        segments[key][1] += 1

    # 2. charge each segment, applying WINDOW caps; collect DAY / ENTRY capped amounts
    fee = Decimal(0)
    by_day: dict[date, list] = defaultdict(lambda: [Decimal(0), Decimal(0)])  # day -> [sum, cap]
    entry = [Decimal(0), Decimal(0)]
    for key in order:
        r, minutes = segments[key]
        charge = _segment_charge(r, minutes)
        if r.cap_sgd is None:
            fee += charge
        elif r.cap_scope == CapScope.WINDOW:
            fee += min(charge, r.cap_sgd)
        elif r.cap_scope == CapScope.DAY:
            acc = by_day[key[1].date()]
            acc[0] += charge
            acc[1] = max(acc[1], r.cap_sgd)
        else:                                            # ENTRY
            entry[0] += charge
            entry[1] = max(entry[1], r.cap_sgd)
    fee += sum((min(s, cap) for s, cap in by_day.values()), Decimal(0))
    fee += min(entry[0], entry[1]) if entry[1] else entry[0]
    return fee.quantize(CENT, rounding=ROUND_HALF_UP)


class FeeCalculator:
    def __init__(self, carpark_repo: CarparkRepository, holidays: Iterable[date] = ()):
        self._repo = carpark_repo
        self._holidays = frozenset(holidays)     # public holidays are charged as Sundays

    def calculate_fee(self, carpark_id: str, request: "SearchRequest") -> Optional[Decimal]:
        """Fee for the request's lot type and parking period. None = Unavailable."""
        return self.calculate_fee_for(carpark_id, request.preference.lot_type,
                                      request.arrival_time, request.departure_time)

    def calculate_fee_for(self, carpark_id: str, lot_type: LotTypeLike,
                          arrival: datetime, departure: datetime) -> Optional[Decimal]:
        return compute_fee(self._repo.get_rate_rules(carpark_id, lot_type), arrival, departure, self._holidays)
