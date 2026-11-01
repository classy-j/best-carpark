"""Regression tests: no synthetic walking duration enters verified rankings."""
from decimal import Decimal
from app.schemas.carpark import CarparkOut
from app.schemas.search import SearchPreference, SearchResult
from app.services.ranking_engine import RankingEngine, walking_minutes
from tests.helpers import make_info


def item(cid, fee, minutes=None, straight=100):
    return SearchResult(carpark=CarparkOut.from_info(make_info(cid)),
        straight_line_m=straight, walking_time_min=minutes,
        walking_distance_m=500 if minutes is not None else None,
        estimated_fee_sgd=Decimal(fee))


def test_no_straight_line_derived_walking_minutes():
    assert walking_minutes(item("A", "1", straight=50)) is None
    assert walking_minutes(item("B", "1", minutes=5)) == 5


def test_missing_routes_remain_after_verified_even_when_cheaper():
    a=item("A", "10", minutes=8)
    b=item("B", "1", straight=20)
    c=item("C", "5", minutes=4)
    results=RankingEngine().rank_carparks([a,b,c], SearchPreference()).sorted_with_tie_break()
    assert [r.carpark.carpark_id for r in results][-1] == "B"
    assert len(results)==3
    assert b.walking_time_min is None


def test_all_unrouted_still_present():
    rows=[item("A", "4"), item("B", "2")]
    got=RankingEngine().rank_carparks(rows, SearchPreference()).sorted_with_tie_break()
    assert len(got)==2 and all(r.walking_time_min is None for r in got)
