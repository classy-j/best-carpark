from decimal import Decimal

from app.schemas.carpark import Availability, CarparkOut, EVCharging, ExpectedBusyness
from app.schemas.search import SearchPreference, SearchResult
from app.services.ranking_engine import RankingEngine
from tests.helpers import MONDAY_1PM, make_info


def result(cid, fee, walk, **kw):
    return SearchResult(carpark=CarparkOut.from_info(make_info(cid)), walking_time_min=walk,
                        estimated_fee_sgd=None if fee is None else Decimal(fee), **kw)


def ranked(results, priorities):
    out = RankingEngine().rank_carparks(results, SearchPreference(priority_ranking=priorities))
    return [r.carpark.carpark_id for r in out.sorted_with_tie_break()]


def test_first_priority_dominates():
    rs = lambda: [result("A", "1.00", 10), result("B", "3.00", 2)]
    assert ranked(rs(), ["PRICE", "WALKING_TIME"]) == ["A", "B"]
    assert ranked(rs(), ["WALKING_TIME", "PRICE"]) == ["B", "A"]


def test_unknown_fee_is_skipped_not_treated_as_free_and_ties_use_walking_time():
    # A: price 1, walk 0 -> 0.625;  C: no price, walk 0.625 -> 0.625;  tie -> shorter walk first
    rs = [result("A", "1.00", 10), result("B", "3.00", 2), result("C", None, 5)]
    assert ranked(rs, ["PRICE", "WALKING_TIME"]) == ["C", "A", "B"]
    assert [r.rank for r in sorted(rs, key=lambda r: r.rank)] == [1, 2, 3]


def test_expected_busyness_preferred_over_current_availability():
    now = MONDAY_1PM
    busy_now = Availability(available_lots=5, total_lots=100, occupancy_pct=95, last_updated=now, is_stale=False)
    rs = [result("A", "1", 5, availability=busy_now,
                 expected_busyness=ExpectedBusyness(occupancy_pct=20, level="LOW", sample_count=8)),
          result("B", "1", 5, availability=Availability(available_lots=50, total_lots=100, occupancy_pct=50,
                                                        last_updated=now, is_stale=False))]
    assert ranked(rs, ["AVAILABILITY"]) == ["A", "B"]


def test_ev_factor():
    rs = [result("A", "1", 5, ev_charging=EVCharging(supported=False)),
          result("B", "1", 5, ev_charging=EVCharging(supported=True))]
    assert ranked(rs, ["EV_CHARGING", "PRICE"]) == ["B", "A"]
