"""URA carparks from the URA Data Service: carpark list + rates, and live available lots.

    https://eservice.ura.gov.sg/maps/api/   (Car Park List and Rates, Car Park Available Lots)

Auth: an AccessKey (emailed after registering) is exchanged for a token that is valid for
the day; every call sends both headers. fetch_* functions do HTTP; parse_* functions are
pure (tested with sample JSON), like hdb_data.py.

One URA carpark (ppCode) has one row per vehicle category and time window in
Car_Park_Details, e.g. Car 07:00-17:00 and Car 17:00-07:00, each with weekday / Saturday /
Sunday-PH rates. Coordinates are SVY21, like HDB.

TODO(A, once the AccessKey arrives): check the parsers against a real response. Formats
assumed from URA's docs and public samples: rates like "$0.60", minutes like "30 mins",
times like "07.00 AM", coordinates "x,y", lot types C / M / H, parkingSystem B / C.
"""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from app.db.models import DayType, LotType
from app.db.records import SGT, AvailabilityReading, CarparkInfo
from app.exceptions import ApiClientError

log = logging.getLogger(__name__)

TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
INVOKE_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
DETAILS = "Car_Park_Details"
AVAILABILITY = "Car_Park_Availability"

VEH_CATS = {"CAR": LotType.CAR, "MOTORCYCLE": LotType.MOTORCYCLE, "HEAVY VEHICLE": LotType.HEAVY_VEHICLE}
LOT_CODES = {"C": LotType.CAR, "M": LotType.MOTORCYCLE, "Y": LotType.MOTORCYCLE, "H": LotType.HEAVY_VEHICLE}
SYSTEMS = {"B": "ELECTRONIC", "C": "COUPON"}
DAY_FIELDS = ((DayType.WEEKDAY, "weekdayRate", "weekdayMin"),
              (DayType.SATURDAY, "satdayRate", "satdayMin"),
              (DayType.SUNDAY_PH, "sunPHRate", "sunPHMin"))

# Singapore's extent, to sanity-check converted coordinates
_LAT, _LNG = (1.15, 1.48), (103.59, 104.10)


def carpark_id(pp_code: str) -> str:
    return f"URA:{pp_code}"


# ---------------------------------------------------------------- HTTP

class UraClient:
    def __init__(self, access_key: str, http_client: Optional[httpx.Client] = None, timeout: float = 30.0):
        self._key = access_key
        # URA's gateway answers non-browser User-Agents (e.g. python-httpx) with an HTML challenge page,
        # so identify as a browser.
        self._http = http_client or httpx.Client(timeout=timeout, transport=httpx.HTTPTransport(retries=2),
                                                 headers={"User-Agent": "Mozilla/5.0"})
        self._token: Optional[str] = None
        self._token_day: Optional[date] = None

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _get(self, url: str, headers: dict, params: Optional[dict] = None) -> dict:
        try:
            r = self._http.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ApiClientError(f"URA {url} failed: {e}") from e
        if not isinstance(data, dict) or str(data.get("Status", "")).lower() != "success":
            raise ApiClientError(f"URA {url} returned {str(data)[:200]}")
        return data

    def token(self, force: bool = False) -> str:
        """The day's token (URA issues one per day)."""
        today = datetime.now(SGT).date()
        if force or not self._token or self._token_day != today:
            if not self._key:
                raise ApiClientError("URA_API_KEY is not set")
            token = self._get(TOKEN_URL, {"AccessKey": self._key}).get("Result")
            if not token:
                raise ApiClientError("URA token response had no token")
            self._token, self._token_day = token, today
        return self._token

    def _invoke(self, service: str) -> list[dict]:
        for attempt in (0, 1):                  # retry once with a fresh token
            try:
                headers = {"AccessKey": self._key, "Token": self.token(force=attempt == 1)}
                result = self._get(INVOKE_URL, headers, {"service": service}).get("Result")
                return result if isinstance(result, list) else []
            except ApiClientError:
                if attempt == 1:
                    raise
        return []

    def fetch_details(self) -> list[dict]:
        return self._invoke(DETAILS)

    def fetch_availability(self) -> list[dict]:
        return self._invoke(AVAILABILITY)


# ---------------------------------------------------------------- parsing (pure)

def parse_money(v) -> Optional[Decimal]:
    """'$0.60' -> Decimal('0.60'). None if missing or not a price."""
    m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
    if not m:
        return None
    try:
        return Decimal(m.group())
    except InvalidOperation:
        return None


def parse_minutes(v) -> Optional[int]:
    """'30 mins' -> 30. None if missing / zero."""
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m and int(m.group()) > 0 else None


def parse_time(v) -> Optional[time]:
    """'07.00 AM' / '7:00 PM' / '12.00 AM' -> time. None if unparseable."""
    m = re.match(r"\s*(\d{1,2})[.:](\d{2})\s*([AP]M)\s*$", str(v or "").upper())
    if not m:
        return None
    h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= h <= 12 and 0 <= mi < 60):
        return None
    return time(h % 12 + (12 if ampm == "PM" else 0), mi)


def parse_location(row: dict) -> Optional[tuple[float, float]]:
    """First usable geometry's SVY21 'x,y' (easting, northing) -> (lat, lng).

    The order can't be auto-detected: Singapore's easting and northing ranges overlap, so a
    swapped pair still lands inside Singapore. Check one known carpark on a map once the
    AccessKey arrives. Points outside Singapore are rejected."""
    from app.utils.svy21 import svy21_to_wgs84

    for g in row.get("geometries") or []:
        parts = str((g or {}).get("coordinates", "")).split(",")
        try:
            x, y = float(parts[0]), float(parts[1])
        except (IndexError, ValueError):
            continue
        lat, lng = svy21_to_wgs84(x, y)
        if _LAT[0] <= lat <= _LAT[1] and _LNG[0] <= lng <= _LNG[1]:
            return round(lat, 6), round(lng, 6)
    return None


@dataclass(frozen=True)
class UraRate:
    """One rate window for one carpark, vehicle category and day type."""
    lot_type: LotType
    day_type: DayType
    start: time
    end: time
    rate: Decimal              # per interval; 0 = free in this window
    interval_min: int


def parse_details(rows: list[dict]) -> tuple[list[tuple[CarparkInfo, str]], dict[str, list[UraRate]],
                                             dict[tuple[str, LotType], int]]:
    """Car_Park_Details rows -> (carparks, rates by ppCode, capacity by (ppCode, lot type))."""
    by_code: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        code = str(r.get("ppCode") or "").strip()
        if code:
            by_code[code].append(r)

    carparks, rates, capacity = [], {}, {}
    for code, group in by_code.items():
        loc = next((p for p in map(parse_location, group) if p), None)
        if loc is None:
            log.warning("URA %s: no usable coordinates; skipped", code)
            continue
        name = next((str(r.get("ppName")).strip() for r in group if r.get("ppName")), code)
        system = next((SYSTEMS.get(str(r.get("parkingSystem", "")).strip().upper()) for r in group), None)
        carparks.append((CarparkInfo(
            carpark_id=carpark_id(code), name=name, address=name, latitude=loc[0], longitude=loc[1],
            carpark_type=None, parking_system=system, operator="URA", gantry_height_m=None,
            free_parking=None, night_parking=None, has_ev_charging=None, rate_scheme_id=None,
            short_term_parking=None), code))

        out, seen = [], set()
        for r in group:
            lot = VEH_CATS.get(str(r.get("vehCat", "")).strip().upper())
            start, end = parse_time(r.get("startTime")), parse_time(r.get("endTime"))
            if lot is None or start is None or end is None:
                continue
            cap = r.get("parkCapacity")
            if isinstance(cap, (int, float)) or str(cap or "").strip().isdigit():
                capacity[(code, lot)] = max(capacity.get((code, lot), 0), int(cap))
            for day_type, rate_f, min_f in DAY_FIELDS:
                rate, minutes = parse_money(r.get(rate_f)), parse_minutes(r.get(min_f))
                if rate is None or (rate > 0 and minutes is None):
                    continue                     # no parking / unparseable for this day
                key = (lot, day_type, start, end)
                if key not in seen:
                    seen.add(key)
                    out.append(UraRate(lot, day_type, start, end, rate, minutes or 30))
        rates[code] = out
    return carparks, rates, capacity


def parse_availability(rows: list[dict], known_ids: dict[str, str],
                       capacity: dict[tuple[str, LotType], int],
                       collected_at: Optional[datetime] = None) -> tuple[list[AvailabilityReading], set[str]]:
    """Car_Park_Availability rows -> readings for carparks we know.

    URA gives no per-carpark update time, so observed_at = collected_at: "may be outdated"
    then only catches a stopped collector. total_lots comes from parkCapacity (Details)."""
    collected_at = collected_at or datetime.now(SGT)
    readings, unknown, seen = [], set(), set()
    for r in rows:
        code = str(r.get("carparkNo") or "").strip()
        cid = known_ids.get(code)
        if cid is None:
            if code:
                unknown.add(code)
            continue
        lot = LOT_CODES.get(str(r.get("lotType", "")).strip().upper())
        try:
            available = int(r.get("lotsAvailable"))
        except (TypeError, ValueError):
            continue
        if lot is None or (cid, lot) in seen:
            continue
        seen.add((cid, lot))
        total = capacity.get((code, lot))
        readings.append(AvailabilityReading(
            carpark_id=cid, lot_type=lot, available_lots=max(available, 0),
            total_lots=total if total and total > 0 else None,
            observed_at=collected_at, collected_at=collected_at))
    return readings, unknown
