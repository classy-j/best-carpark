from datetime import datetime, time
from decimal import Decimal

from app.db.models import CapScope, ChargeMode, DayType, LotType
from app.db.records import SGT, CarparkInfo, RateRuleInfo
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch, SearchRequest, WalkingRoute

MONDAY_1PM = datetime(2026, 10, 19, 13, 0, tzinfo=SGT)


def make_info(cid="HDB:A", lat=1.3010, lng=103.8541, **kw) -> CarparkInfo:
    d = dict(carpark_id=cid, name=f"Carpark {cid}", address=None, latitude=lat, longitude=lng,
             carpark_type="MULTI-STOREY", parking_system="ELECTRONIC", operator="HDB",
             gantry_height_m=2.1, free_parking="NO", night_parking=True, has_ev_charging=None,
             rate_scheme_id=1, short_term_parking="WHOLE DAY")
    d.update(kw)
    return CarparkInfo(**d)


def rule(rule_id=1, day=DayType.ALL, start=time(7), end=time(22, 30), mode=ChargeMode.PER_INTERVAL,
         rate="0.60", interval=30, per_minute=False, cap=None, cap_scope=None, grace=None,
         priority=0, lot=LotType.CAR) -> RateRuleInfo:
    return RateRuleInfo(rule_id=rule_id, rate_scheme_id=1, lot_type=lot, day_type=day, start_time=start,
                        end_time=end, charge_mode=mode, rate_sgd=Decimal(rate), interval_min=interval,
                        per_minute=per_minute, first_interval_min=None, first_rate_sgd=None,
                        cap_sgd=None if cap is None else Decimal(cap), cap_scope=cap_scope,
                        grace_min=grace, priority=priority)


def make_request(**kw) -> SearchRequest:
    d = dict(destination_address="Albert Centre", arrival_time="2026-10-19T13:00:00",
             departure_time="2026-10-19T15:00:00")
    d.update(kw)
    return SearchRequest(**d)


class FakeMap:
    """MapService stand-in: one or more geocoding matches, fixed walking routes."""
    def __init__(self, matches=None, minutes=None):
        self.matches = matches if matches is not None else [
            PlaceMatch(name="ALBERT CENTRE", location=Location(latitude=1.3010, longitude=103.8541))]
        self.minutes = minutes or {}

    def search_locations(self, query, limit=5):
        return self.matches

    def walking_route(self, start, end):
        for (lat, lng), m in self.minutes.items():
            if round(start.latitude, 4) == lat and round(start.longitude, 4) == lng:
                return WalkingRoute(distance_m=int(m * 80), duration_s=int(m * 60))
        return WalkingRoute(distance_m=400, duration_s=300)
