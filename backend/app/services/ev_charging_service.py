"""EVChargingService «control»: EV charging information per carpark (UC-06, FR2.9, FR6.4).

refresh() downloads LTA's charging locations (in the background, never inside a search:
the file is large) and keeps the last good copy if a download fails (UC-06 EX1).
Matching is by proximity (FR2.9): stations within MATCH_RADIUS_M of the carpark.
Stations are bucketed into ~111 m grid cells, so a lookup checks a few cells only.

Two outputs:
  match_flags(carparks)  {carpark_id: True/False} for the collector to store in
                         carparks.has_ev_charging (used by the "EV required" filter and ranking)
  get_charging_info(c)   per search result; live charger counts when this process has
                         loaded the feed, otherwise the stored flag with counts Unavailable
"""
import logging
import math
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.clients.interfaces import EVChargingSource
from app.schemas.carpark import CarparkOut, EVCharging
from app.utils.geo import haversine_m
from app.utils.timeutil import now_sg

log = logging.getLogger(__name__)

MATCH_RADIUS_M = 75
CELL_DEG = 0.001                       # ~111 m
LIVE_MAX_AGE = timedelta(minutes=60)   # older feed -> charger counts shown as Unavailable


def _cell(lat: float, lng: float) -> tuple[int, int]:
    return math.floor(lat / CELL_DEG), math.floor(lng / CELL_DEG)


class EVChargingService:
    def __init__(self, source: Optional[EVChargingSource] = None, match_radius_m: float = MATCH_RADIUS_M):
        self._source = source
        self._radius_m = match_radius_m
        self._span = max(1, math.ceil(match_radius_m / 111_000 / CELL_DEG))
        self._snapshot = None          # (grid, loaded_at); replaced in one assignment (thread-safe read)

    # ---- data refresh (background) ----
    def refresh(self) -> bool:
        """Download the feed. Returns False (and keeps the previous copy) on failure."""
        if self._source is None:
            return False
        try:
            stations = self._source.fetch_charging_points()
        except Exception as e:
            log.error("EV refresh failed; keeping previous EV data: %s", e)
            return False
        if not stations:
            log.warning("EV feed returned no stations; keeping previous EV data")
            return False
        grid: dict[tuple[int, int], list] = {}
        for s in stations:
            grid.setdefault(_cell(s.latitude, s.longitude), []).append(s)
        self._snapshot = (grid, now_sg())
        log.info("EV data refreshed: %d locations", len(stations))
        return True

    @property
    def loaded(self) -> bool:
        return self._snapshot is not None

    def _nearby(self, lat: float, lng: float) -> list:
        grid, _ = self._snapshot
        ci, cj = _cell(lat, lng)
        return [s for di in range(-self._span, self._span + 1) for dj in range(-self._span, self._span + 1)
                for s in grid.get((ci + di, cj + dj), ())
                if haversine_m(lat, lng, s.latitude, s.longitude) <= self._radius_m]

    # ---- for the collector ----
    def match_flags(self, carparks: Iterable) -> dict[str, bool]:
        """{carpark_id: has EV charging} for objects with carpark_id / latitude / longitude.
        Empty when no feed is loaded, so a failed download never writes False."""
        if not self.loaded:
            return {}
        return {c.carpark_id: bool(self._nearby(c.latitude, c.longitude)) for c in carparks}

    # ---- for search ----
    def get_charging_info(self, carpark: CarparkOut, now: Optional[datetime] = None) -> EVCharging:
        if not self.loaded:                         # this process has no feed: use the stored flag
            return EVCharging(supported=carpark.has_ev_charging, available_chargers=None)
        near = self._nearby(carpark.location.latitude, carpark.location.longitude)
        if not near:
            return EVCharging(supported=False, available_chargers=None)
        fresh = (now or now_sg()) - self._snapshot[1] <= LIVE_MAX_AGE
        counts = [s.available_points for s in near if s.available_points is not None]
        return EVCharging(supported=True, available_chargers=sum(counts) if (counts and fresh) else None)
