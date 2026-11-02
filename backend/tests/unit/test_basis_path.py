"""Lab 4 §3.2.2: basis path (white-box) tests for two methods with complex logic.

Method 1: app/services/fee_calculator.py  _segment_charge(rule, minutes)
  Predicates: P1 mode == FREE, P2 mode == PER_ENTRY, P3a first_interval_min,
              P3b first_rate_sgd is not None, P4 per_minute
  Cyclomatic complexity V(G) = 5 predicates + 1 = 6 -> 6 independent paths (SC-1..SC-6).

Method 2: app/services/search_service.py  SearchService.resolve_destination(request)
  Predicates: Q1 destination_location given, Q2 no matches, Q3 exactly one match,
              Q4 an exact (case-insensitive) name match exists
  V(G) = 4 + 1 = 5 -> 5 independent paths (RD-1..RD-5).
  (The list comprehension that builds `exact` is treated as one statement node; both of its
  outcomes, empty and non-empty, are exercised by RD-4 and RD-5.)
"""
from datetime import time
from decimal import Decimal

import pytest

from app.db.models import ChargeMode, DayType, LotType
from app.db.records import RateRuleInfo
from app.exceptions import AddressNotFoundError, MultipleDestinationsError
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch
from app.services.fee_calculator import _segment_charge
from app.services.search_service import SearchService
from tests.helpers import make_request


def rule(mode=ChargeMode.PER_INTERVAL, rate="0.60", interval=30, per_minute=False,
         first_interval=None, first_rate=None):
    return RateRuleInfo(rule_id=1, rate_scheme_id=1, lot_type=LotType.CAR, day_type=DayType.ALL,
                        start_time=time(7), end_time=time(22, 30), charge_mode=mode, rate_sgd=Decimal(rate),
                        interval_min=interval, per_minute=per_minute, first_interval_min=first_interval,
                        first_rate_sgd=None if first_rate is None else Decimal(first_rate),
                        cap_sgd=None, cap_scope=None, grace_min=None, priority=0)


# id, path (predicate outcomes), rule, minutes, expected
SEGMENT_PATHS = [
    ("SC-1", "P1=T", rule(mode=ChargeMode.FREE, rate="0", interval=None), 120, "0"),
    ("SC-2", "P1=F P2=T", rule(mode=ChargeMode.PER_ENTRY, rate="0.65", interval=None), 120, "0.65"),
    ("SC-3", "P1=F P2=F P3a=F P4=F", rule(), 40, "1.20"),
    ("SC-4", "P1=F P2=F P3a=T P3b=F P4=F", rule(first_interval=60), 40, "1.20"),
    ("SC-5", "P1=F P2=F P3a=T P3b=T P4=F", rule(first_interval=60, first_rate="2.00"), 90, "2.60"),
    ("SC-6", "P1=F P2=F P3a=F P4=T", rule(per_minute=True), 45, "0.90"),
]


@pytest.mark.parametrize("case_id,path,r,minutes,expected", SEGMENT_PATHS, ids=[c[0] for c in SEGMENT_PATHS])
def test_segment_charge_paths(case_id, path, r, minutes, expected):
    assert _segment_charge(r, minutes) == Decimal(expected)


class CountingMap:
    def __init__(self, matches):
        self.matches, self.calls = matches, 0

    def search_locations(self, query, limit=5):
        self.calls += 1
        return self.matches


NORTH = PlaceMatch(name="NTU NORTH SPINE", location=Location(latitude=1.347, longitude=103.680))
SOUTH = PlaceMatch(name="NTU SOUTH SPINE", location=Location(latitude=1.342, longitude=103.682))
PICKED = {"latitude": 1.3010, "longitude": 103.8541}


def resolve(matches, **request_kw):
    m = CountingMap(matches)
    svc = SearchService(m, None, None, None, None, None, None, None)
    return svc.resolve_destination(make_request(**request_kw)), m.calls


def test_RD1_location_already_picked_skips_onemap():          # Q1=T
    loc, calls = resolve([NORTH, SOUTH], destination_address="NTU", destination_location=PICKED)
    assert (loc.latitude, loc.longitude, calls) == (1.3010, 103.8541, 0)


def test_RD2_no_match_raises_invalid_destination():            # Q1=F Q2=T
    with pytest.raises(AddressNotFoundError):
        resolve([], destination_address="zzzz")


def test_RD3_single_match_used():                              # Q1=F Q2=F Q3=T
    loc, calls = resolve([SOUTH], destination_address="NTU")
    assert (loc.latitude, calls) == (1.342, 1)


def test_RD4_several_matches_exact_name_wins():                # Q1=F Q2=F Q3=F Q4=T
    loc, _ = resolve([NORTH, SOUTH], destination_address="ntu south spine")
    assert loc.latitude == 1.342


def test_RD5_several_matches_no_exact_asks_driver():           # Q1=F Q2=F Q3=F Q4=F
    with pytest.raises(MultipleDestinationsError) as e:
        resolve([NORTH, SOUTH], destination_address="NTU")
    assert [m.name for m in e.value.matches] == ["NTU NORTH SPINE", "NTU SOUTH SPINE"]
