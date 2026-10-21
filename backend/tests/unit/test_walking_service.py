from app.exceptions import RouteNotFoundError
from app.schemas.carpark import Location
from app.schemas.search import WalkingRoute
from app.services.walking_service import WalkingService

DEST = Location(latitude=1.3483, longitude=103.6831)


class FakeOneMap:
    def __init__(self):
        self.calls = 0

    def walking_route(self, start, end):
        self.calls += 1
        if start.latitude > 1.40:
            raise RouteNotFoundError("nope")
        return WalkingRoute(distance_m=500, duration_s=420)


def test_routes_fetched_and_cached():
    om = FakeOneMap()
    svc = WalkingService(om)
    carparks = {"A": Location(latitude=1.35, longitude=103.68)}
    assert svc.get_routes(DEST, carparks)["A"].distance_m == 500
    svc.get_routes(DEST, carparks)
    assert om.calls == 1   # second search served from cache


def test_failed_route_is_none_and_not_cached():
    om = FakeOneMap()
    svc = WalkingService(om)
    carparks = {"BAD": Location(latitude=1.45, longitude=103.68), "OK": Location(latitude=1.35, longitude=103.68)}
    result = svc.get_routes(DEST, carparks)
    assert result["BAD"] is None and result["OK"] is not None
    svc.get_routes(DEST, carparks)
    assert om.calls == 3   # OK cached; BAD retried
