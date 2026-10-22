"""OneMapAdapter: realizes MapService (geocoding + walking routes) using OneMap.

Both Search and Routing require a OneMap access token. The adapter can either:
1. generate/renew a token from email + password, or
2. use a ready-made token supplied through configuration.
"""
import time
from typing import Optional

from app.clients.base import BaseApiClient
from app.exceptions import AddressNotFoundError, ApiClientError, RouteNotFoundError
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch, WalkingRoute


class OneMapAdapter(BaseApiClient):
    def __init__(
        self,
        base_url: str,
        email: str = "",
        password: str = "",
        token: str = "",
        **kwargs,
    ):
        super().__init__(base_url, **kwargs)
        self._email = email
        self._password = password
        self._token: Optional[str] = token or None

        # If a ready-made token is supplied, its expiry time is unknown.
        # If email/password are used instead, expiry is obtained from OneMap.
        self._token_expiry: float = 0.0 if not token else float("inf")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def _auth_header(self) -> dict[str, str]:
        if not self._token or time.time() > self._token_expiry - 300:
            if not self._email or not self._password:
                raise ApiClientError(
                    "OneMap credentials are missing. Set ONEMAP_EMAIL and "
                    "ONEMAP_PASSWORD, or set ONEMAP_API_TOKEN in backend/.env."
                )

            data = self._request(
                "POST",
                "/api/auth/post/getToken",
                json={
                    "email": self._email,
                    "password": self._password,
                },
            )

            try:
                self._token = data["access_token"]
                self._token_expiry = float(data["expiry_timestamp"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ApiClientError(
                    f"Unexpected OneMap token response: {data!r}"
                ) from exc

        return {"Authorization": self._token}

    @staticmethod
    def _raise_on_api_error(data: object, operation: str) -> None:
        """Catch OneMap errors that may be returned inside HTTP 200 responses."""
        if isinstance(data, dict) and data.get("error"):
            raise ApiClientError(
                f"OneMap {operation} failed: {data['error']}"
            )

    # ------------------------------------------------------------------
    # Geocoding / destination search
    # ------------------------------------------------------------------

    def search_locations(
        self,
        query: str,
        limit: int = 5,
    ) -> list[PlaceMatch]:

        query = query.strip()

        if not query:
            return []

        data = self._request(
            "GET",
            "/api/common/elastic/search",
            headers=self._auth_header(),
            params={
                "searchVal": query,
                "returnGeom": "Y",
                "getAddrDetails": "Y",
                "pageNum": 1,
            },
        )

        self._raise_on_api_error(data, "search")

        matches: list[PlaceMatch] = []
        seen: set[tuple[float, float]] = set()

        for result in data.get("results") or []:
            try:
                location = Location(
                    latitude=float(result["LATITUDE"]),
                    longitude=float(result["LONGITUDE"]),
                )
            except (KeyError, TypeError, ValueError):
                continue

            name = (
                result.get("SEARCHVAL")
                or result.get("ADDRESS")
                or query
            ).strip()

            key = (
                round(location.latitude, 4),
                round(location.longitude, 4),
            )

            if key in seen:
                continue

            seen.add(key)

            matches.append(
                PlaceMatch(
                    name=name,
                    address=result.get("ADDRESS"),
                    location=location,
                )
            )

            if len(matches) >= limit:
                break

        return matches

    def geocode(self, query: str) -> Location:
        matches = self.search_locations(query, limit=1)

        if not matches:
            raise AddressNotFoundError(
                f"No OneMap result for {query!r}"
            )

        return matches[0].location

    # ------------------------------------------------------------------
    # Walking route
    # ------------------------------------------------------------------

    def walking_route(
        self,
        start: Location,
        end: Location,
    ) -> WalkingRoute:

        data = self._request(
            "GET",
            "/api/public/routingsvc/route",
            headers=self._auth_header(),
            params={
                "start": f"{start.latitude},{start.longitude}",
                "end": f"{end.latitude},{end.longitude}",
                "routeType": "walk",
            },
        )

        self._raise_on_api_error(data, "routing")

        summary = data.get("route_summary")

        if not summary:
            raise RouteNotFoundError(
                f"No walking route {start} -> {end}"
            )

        try:
            return WalkingRoute(
                distance_m=round(
                    float(summary["total_distance"])
                ),
                duration_s=round(
                    float(summary["total_time"])
                ),
            )

        except (KeyError, TypeError, ValueError) as exc:
            raise ApiClientError(
                f"Unexpected OneMap routing response: {data!r}"
            ) from exc