"""RankingEngine «control» and RankedResultList «container» (UC-07, FR4.1/FR4.2).

Composite score = weighted average of the factor scores (each 0..1, higher is better).
The Driver's 1st priority has weight 1, the 2nd 0.6, the 3rd 0.36, ... (WEIGHT_DECAY).
A factor that is unavailable for a carpark is left out of that carpark's average (UC-07 AF1),
so missing data neither helps nor hurts. Ties are broken by walking time (UC-07 AF2).
"""
from typing import Optional, Sequence

from app.schemas.search import SearchPreference, SearchResult

WEIGHT_DECAY = 0.6
DEFAULT_PRIORITIES = ["PRICE", "WALKING_TIME", "AVAILABILITY"]
WALK_M_PER_MIN = 80          # only used when OneMap had no route: straight line -> rough minutes
DETOUR = 1.3
LOTS_FOR_FULL_SCORE = 50     # availability score when the total is unknown


def walking_minutes(r: SearchResult) -> Optional[float]:
    if r.walking_time_min is not None:
        return r.walking_time_min
    if r.straight_line_m is not None:
        return r.straight_line_m * DETOUR / WALK_M_PER_MIN
    return None


def _relative_lower_is_better(values: dict[int, Optional[float]]) -> dict[int, Optional[float]]:
    known = [v for v in values.values() if v is not None]
    if not known:
        return {i: None for i in values}
    lo, hi = min(known), max(known)
    return {i: None if v is None else (1.0 if hi == lo else (hi - v) / (hi - lo)) for i, v in values.items()}


def _availability_score(r: SearchResult) -> Optional[float]:
    if r.expected_busyness is not None:                     # arrival-time estimate first
        return 1 - r.expected_busyness.occupancy_pct / 100
    a = r.availability
    if a is None:
        return None
    if a.occupancy_pct is not None:
        return 1 - a.occupancy_pct / 100
    return min(1.0, a.available_lots / LOTS_FOR_FULL_SCORE)


class RankedResultList:
    def __init__(self, results: Sequence[SearchResult]):
        self._results = list(results)

    def sorted_with_tie_break(self) -> list[SearchResult]:
        def key(r: SearchResult):
            w = walking_minutes(r)
            return (-r.composite_score, w if w is not None else float("inf"),
                    r.estimated_fee_sgd if r.estimated_fee_sgd is not None else float("inf"))
        ordered = sorted(self._results, key=key)
        for i, r in enumerate(ordered, start=1):
            r.rank = i
        return ordered


class RankingEngine:
    def rank_carparks(self, results: Sequence[SearchResult], preference: SearchPreference) -> RankedResultList:
        priorities = preference.priority_ranking or DEFAULT_PRIORITIES
        weights = {p: WEIGHT_DECAY ** i for i, p in enumerate(priorities)}
        idx = range(len(results))
        factor = {
            "PRICE": _relative_lower_is_better(
                {i: None if results[i].estimated_fee_sgd is None else float(results[i].estimated_fee_sgd) for i in idx}),
            "WALKING_TIME": _relative_lower_is_better({i: walking_minutes(results[i]) for i in idx}),
            "AVAILABILITY": {i: _availability_score(results[i]) for i in idx},
            "EV_CHARGING": {i: None if results[i].ev_charging.supported is None
                            else float(results[i].ev_charging.supported) for i in idx},
        }
        for i in idx:
            total = weight = 0.0
            for p, w in weights.items():
                s = factor[p][i]
                if s is not None:
                    total += w * s
                    weight += w
            results[i].composite_score = round(total / weight, 4) if weight else 0.0
        return RankedResultList(results)
