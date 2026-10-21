"""API models for carparks and the information attached to them."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.db.records import CarparkInfo

BusynessLevel = Literal["LOW", "MODERATE", "HIGH"]


class Location(BaseModel):
    latitude: float
    longitude: float


class CarparkOut(BaseModel):
    carpark_id: str
    name: str
    address: Optional[str] = None
    location: Location
    carpark_type: Optional[str] = None
    parking_system: Optional[str] = None
    gantry_height_m: Optional[float] = None       # None = unknown
    night_parking: Optional[bool] = None
    free_parking: Optional[str] = None
    short_term_parking: Optional[str] = None
    has_ev_charging: Optional[bool] = None        # None = unknown

    @classmethod
    def from_info(cls, c: CarparkInfo) -> "CarparkOut":
        return cls(carpark_id=c.carpark_id, name=c.name, address=c.address,
                   location=Location(latitude=c.latitude, longitude=c.longitude),
                   carpark_type=c.carpark_type, parking_system=c.parking_system,
                   gantry_height_m=c.gantry_height_m, night_parking=c.night_parking,
                   free_parking=c.free_parking, short_term_parking=c.short_term_parking,
                   has_ev_charging=c.has_ev_charging)

    def fits_vehicle_height(self, height_m: Optional[float]) -> Optional[bool]:
        """FR4.4. None when either height is unknown."""
        if not height_m or self.gantry_height_m is None:
            return None
        return height_m <= self.gantry_height_m


class Availability(BaseModel):
    """Current availability (class diagram: Availability)."""
    available_lots: int
    total_lots: Optional[int] = None             # None = source gives no total (never 0)
    occupancy_pct: Optional[int] = None
    last_updated: datetime
    is_stale: bool                               # older than 15 min -> "may be outdated" (FR6.3)


class ExpectedBusyness(BaseModel):
    """Expected availability at arrival, from history. Shown with the label "Expected" (FR5.3)."""
    occupancy_pct: int
    level: BusynessLevel
    sample_count: int


class EVCharging(BaseModel):
    supported: Optional[bool] = None             # None = unknown
    available_chargers: Optional[int] = None     # None = Unavailable
