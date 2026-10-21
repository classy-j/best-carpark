"""OneMapAdapter: realizes MapService (geocoding + walking routes) using OneMap.

Endpoint paths / field names follow OneMap's public docs
(https://www.onemap.gov.sg/apidocs/). Routing needs a token; tokens last ~3 days.
"""
import time
from typing import Optional

from app.clients.base import BaseApiClient
from app.exceptions import AddressNotFoundError, ApiClientError, RouteNotFoundError
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch, WalkingRoute


class OneMapAdapter(BaseApiClient):
    def __init__(self, base_url: str, email: str = "", password: str = "", token: str = "", **kwargs):
        """Give email + password (token renewed automatically), or a ready-made token."""
        super().__init__(base_url, **kwargs)
        self._email, self._password = email, password
        self._token: Optional[str] = token or None
        self._token_expiry: float = 0.0 if not token else float("inf")

    # ---- auth ----
    def _auth_header(self) -> dict:
        if not self._token or time.time() > self._token_expiry - 300:
            data = self._request("POST", "/api/auth/post/getToken",
                                 json={"email": self._email, "password": self._password})
            try:
                self._token = data["access_token"]
                self._token_expiry = float(data["expiry_timestamp"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ApiClientError(f"Unexpected OneMap token response: {data!r}") from exc
        return {"Authorization": self._token}

    # ---- geocoding ----
    def search_locations(self, query: str, limit: int = 5) -> list[PlaceMatch]:
        data = self._request("GET", "/api/common/elastic/search", params={
            "searchVal": query, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        matches, seen = [], set()
        for r in data.get("results") or []:
            try:
                loc = Location(latitude=float(r["LATITUDE"]), longitude=float(r["LONGITUDE"]))
            except (KeyError, TypeError, ValueError):
                continue
            name = (r.get("SEARCHVAL") or r.get("ADDRESS") or query).strip()
            key = (round(loc.latitude, 4), round(loc.longitude, 4))
            if key in seen:
                continue
            seen.add(key)
            matches.append(PlaceMatch(name=name, address=r.get("ADDRESS"), location=loc))
            if len(matches) == limit:
                break
        return matches

    def geocode(self, query: str) -> Location:
        matches = self.search_locations(query, limit=1)
        if not matches:
            raise AddressNotFoundError(f"No OneMap result for {query!r}")
        return matches[0].location

    # ---- walking route ----
    def walking_route(self, start: Location, end: Location) -> WalkingRoute:
        data = self._request("GET", "/api/public/routingsvc/route", headers=self._auth_header(), params={
            "start": f"{start.latitude},{start.longitude}",
            "end": f"{end.latitude},{end.longitude}",
            "routeType": "walk"})
        summary = data.get("route_summary")
        if not summary:
            raise RouteNotFoundError(f"No walking route {start} -> {end}")
        return WalkingRoute(distance_m=round(summary["total_distance"]), duration_s=round(summary["total_time"]))
