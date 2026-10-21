"""Walking routes from carparks to the destination via MapService (OneMap), fetched
concurrently and cached for an hour. No straight-line fallback here: a failed route is
None (shown as "walking route unavailable"; RankingEngine estimates from distance)."""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.exceptions import ApiClientError
from app.schemas.carpark import Location
from app.schemas.search import WalkingRoute

log = logging.getLogger(__name__)


class WalkingService:
    def __init__(self, map_service, max_workers: int = 8, cache_ttl_seconds: int = 3600):
        self._map = map_service
        self._max_workers = max_workers
        self._ttl = cache_ttl_seconds
        self._cache: dict[tuple, tuple[float, Optional[WalkingRoute]]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(a: Location, b: Location) -> tuple:
        return (round(a.latitude, 5), round(a.longitude, 5), round(b.latitude, 5), round(b.longitude, 5))

    def get_route(self, from_loc: Location, to_loc: Location) -> Optional[WalkingRoute]:
        key = self._key(from_loc, to_loc)
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < self._ttl:
                return hit[1]
        try:
            route = self._map.walking_route(from_loc, to_loc)
        except ApiClientError as exc:
            log.warning("Walking route failed for %s -> %s: %s", from_loc, to_loc, exc)
            return None  # failures are not cached, so the next search retries
        with self._lock:
            self._cache[key] = (time.monotonic(), route)
        return route

    def get_routes(self, destination: Location, carparks: dict[str, Location]) -> dict[str, Optional[WalkingRoute]]:
        """Walking route from each carpark (id -> location) to the destination."""
        if not carparks:
            return {}
        ids = list(carparks)
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            routes = list(pool.map(lambda cid: self.get_route(carparks[cid], destination), ids))
        return dict(zip(ids, routes))
