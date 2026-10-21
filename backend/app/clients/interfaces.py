"""Interfaces to the external actors (class diagram: «interface» MapService,
CarparkDataSource, EVChargingSource). Adapters in this package realize them, so
services depend on these interfaces, never on a specific API's JSON format."""
from datetime import datetime
from typing import Callable, Iterable, Optional, Protocol

from app.db.records import AvailabilityReading, CarparkInfo
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch, WalkingRoute


class MapService(Protocol):                      # realized by OneMapAdapter
    def geocode(self, query: str) -> Location: ...
    def search_locations(self, query: str, limit: int = 5) -> list["PlaceMatch"]: ...
    def walking_route(self, start: Location, end: Location) -> WalkingRoute: ...


class CarparkDataSource(Protocol):               # realized by HdbAdapter
    def fetch_carparks(self) -> list[tuple[CarparkInfo, str]]: ...
    def fetch_availability(
        self, resolve_ids: Callable[[Iterable[str]], dict[str, str]], at: Optional[datetime] = None
    ) -> list[AvailabilityReading]: ...


class EVChargingSource(Protocol):                # realized by LtaDataMallAdapter
    def fetch_charging_points(self) -> list[dict]: ...
