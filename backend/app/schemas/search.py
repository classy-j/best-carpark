"""Request/response models for the search endpoint (class diagram: SearchRequest,
SearchPreference, SearchResult)."""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.carpark import Availability, CarparkOut, EVCharging, ExpectedBusyness, Location
from app.utils.timeutil import to_sg

Priority = Literal["PRICE", "WALKING_TIME", "AVAILABILITY", "EV_CHARGING"]
LotTypeName = Literal["CAR", "MOTORCYCLE", "HEAVY_VEHICLE"]
_ALIASES = {"COST": "PRICE", "DISTANCE": "WALKING_TIME", "WALKING": "WALKING_TIME", "EV": "EV_CHARGING"}


class SearchPreference(BaseModel):
    """What the Driver configured (UC-08). Kept in the browser; sent with every search."""
    priority_ranking: list[Priority] = Field(
        default_factory=lambda: ["PRICE", "WALKING_TIME", "AVAILABILITY"])
    lot_type: LotTypeName = "CAR"
    vehicle_height_m: Optional[float] = Field(default=None, gt=0, le=6)
    carpark_types: list[str] = Field(default_factory=list)   # empty = any type
    ev_required: bool = False

    @field_validator("priority_ranking", mode="before")
    @classmethod
    def _normalise(cls, v):
        out = []
        for p in v or []:
            p = _ALIASES.get(str(p).upper(), str(p).upper())
            if p not in out:
                out.append(p)
        return out

    @field_validator("lot_type", mode="before")
    @classmethod
    def _upper(cls, v):
        return str(v).upper()


class SearchRequest(BaseModel):
    destination_address: str = Field(min_length=1)
    destination_location: Optional[Location] = None   # set after the Driver picks one of several matches
    arrival_time: datetime
    departure_time: Optional[datetime] = None
    parking_duration_minutes: Optional[int] = Field(default=None, gt=0, le=7 * 24 * 60)
    preference: SearchPreference = Field(default_factory=SearchPreference)

    @field_validator("destination_address")
    @classmethod
    def _address_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Destination address is required.")
        return v.strip()

    @field_validator("arrival_time", "departure_time")
    @classmethod
    def _to_sgt(cls, v):
        return None if v is None else to_sg(v)

    @model_validator(mode="after")
    def _parking_period(self):
        if self.departure_time is None:
            if self.parking_duration_minutes is None:
                raise ValueError("Enter a departure time or a parking duration.")
            # UC-01 AF2: duration given instead of a departure time
            self.departure_time = self.arrival_time + timedelta(minutes=self.parking_duration_minutes)
        if self.departure_time <= self.arrival_time:
            raise ValueError("Departure must be after arrival.")
        return self

    def get_parking_duration(self) -> timedelta:
        return self.departure_time - self.arrival_time


class WalkingRoute(BaseModel):
    distance_m: int
    duration_s: int


class PlaceMatch(BaseModel):
    name: str
    address: Optional[str] = None
    location: Location


class SearchResult(BaseModel):
    rank: int = 0
    carpark: CarparkOut
    straight_line_m: Optional[float] = None
    walking_distance_m: Optional[int] = None       # None = OneMap could not route
    walking_time_min: Optional[float] = None
    estimated_fee_sgd: Optional[Decimal] = None    # None = Unavailable (never 0 for "unknown")
    availability: Optional[Availability] = None
    expected_busyness: Optional[ExpectedBusyness] = None
    ev_charging: EVCharging = Field(default_factory=EVCharging)
    height_unknown: bool = False                   # vehicle height given but gantry height unknown
    composite_score: float = 0.0


class SearchResponse(BaseModel):
    destination_address: str
    destination: Location
    results: list[SearchResult]
    message: Optional[str] = None                  # e.g. "No carparks found within 1 km" (UC-10)
