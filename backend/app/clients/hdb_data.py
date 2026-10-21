"""HDB data from data.gov.sg: static carpark info + live availability.

fetch_* functions do HTTP; parse_* functions are pure (tested with sample JSON),
so the parsing logic can be tested without network access.
"""
import csv
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import httpx

from app.db.models import LotType
from app.db.records import SGT, AvailabilityReading, CarparkInfo

INFO_RESOURCE_ID = "d_23f946fa557947f93a8043bbef41dd09"
INFO_URL = "https://data.gov.sg/api/action/datastore_search"
AVAILABILITY_URL = "https://api.data.gov.sg/v1/transport/carpark-availability"

# HDB lot type codes. Others (e.g. S = motorcycle with sidecar) are not supported by the app.
LOT_TYPES = {"C": LotType.CAR, "Y": LotType.MOTORCYCLE, "H": LotType.HEAVY_VEHICLE}

TIMEOUT = httpx.Timeout(30.0)
MAX_RETRIES = 4


def carpark_id(car_park_no: str) -> str:
    return f"HDB:{car_park_no}"


# ---------------------------------------------------------------- HTTP

def _headers() -> dict:
    # Optional: data.gov.sg API key raises rate limits. Set DATA_GOV_SG_API_KEY if you have one.
    key = os.environ.get("DATA_GOV_SG_API_KEY")
    return {"x-api-key": key} if key else {}


def _get_json(client: httpx.Client, url: str, params: Optional[dict] = None) -> dict:
    """GET with retry on rate limit (429) and server errors (5xx)."""
    for attempt in range(MAX_RETRIES):
        try:
            r = client.get(url, params=params, headers=_headers())
            if r.status_code == 429 or r.status_code >= 500:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status < 500 and status != 429:
                raise  # 4xx other than 429: retrying won't help
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt * 5)  # 5, 10, 20 s
    raise RuntimeError("unreachable")


def fetch_carpark_info_records(page_size: int = 500) -> list[dict]:
    """All rows of the 'HDB Carpark Information' dataset (~2,300 carparks)."""
    records: list[dict] = []
    offset = 0
    with httpx.Client(timeout=TIMEOUT) as client:
        while True:
            data = _get_json(client, INFO_URL, {
                "resource_id": INFO_RESOURCE_ID, "limit": page_size, "offset": offset})
            result = data["result"]
            page = result["records"]
            records.extend(page)
            offset += len(page)
            if not page or offset >= int(result.get("total", 0)):
                return records


def fetch_availability(at: Optional[datetime] = None) -> dict:
    """Raw response of the carpark availability API: live, or the snapshot
    at (or just before) `at` if given (the API keeps history)."""
    params = None
    if at is not None:
        at_sgt = at.astimezone(SGT) if at.tzinfo else at
        params = {"date_time": at_sgt.strftime("%Y-%m-%dT%H:%M:%S")}
    with httpx.Client(timeout=TIMEOUT) as client:
        return _get_json(client, AVAILABILITY_URL, params)


# ---------------------------------------------------------------- CSV snapshot (fallback for demo day)

INFO_COLUMNS = ["car_park_no", "address", "x_coord", "y_coord", "car_park_type",
                "type_of_parking_system", "short_term_parking", "free_parking",
                "night_parking", "car_park_decks", "gantry_height", "car_park_basement"]


def save_records_csv(records: Iterable[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INFO_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def read_records_csv(path: Path) -> list[dict]:
    """Works with our own snapshot and with the CSV downloaded from data.gov.sg."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- parsing (pure)

def _code(text: Optional[str], drop_suffix: str = "") -> Optional[str]:
    """'MULTI-STOREY CAR PARK' -> 'MULTI_STOREY'; 'SUN & PH FR 7AM-10.30PM' -> 'SUN_PH_FR_7AM_10_30PM'."""
    if text is None or not text.strip():
        return None
    t = text.strip().upper()
    if drop_suffix and t.endswith(drop_suffix):
        t = t[: -len(drop_suffix)]
    return re.sub(r"[^A-Z0-9]+", "_", t).strip("_")[:32] or None


def _float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_carpark_info(record: dict) -> Optional[tuple[CarparkInfo, str]]:
    """One dataset row -> (CarparkInfo, source_ref). None if the row is unusable."""
    from app.utils.svy21 import svy21_to_wgs84

    ref = (record.get("car_park_no") or "").strip()
    x, y = _float(record.get("x_coord")), _float(record.get("y_coord"))
    if not ref or x is None or y is None or x == 0 or y == 0:
        return None
    lat, lng = svy21_to_wgs84(x, y)
    address = (record.get("address") or "").strip() or None
    gantry = _float(record.get("gantry_height"))
    night = (record.get("night_parking") or "").strip().upper()

    info = CarparkInfo(
        carpark_id=carpark_id(ref),
        name=address or ref,                       # dataset has no separate name
        address=address,
        latitude=round(lat, 6),
        longitude=round(lng, 6),
        carpark_type=_code(record.get("car_park_type"), " CAR PARK"),
        parking_system=_code(record.get("type_of_parking_system"), " PARKING"),
        operator="HDB",
        gantry_height_m=gantry if gantry else None,  # 0 = no gantry / unknown
        free_parking=_code(record.get("free_parking")),
        night_parking=True if night == "YES" else False if night == "NO" else None,
        short_term_parking=_code(record.get("short_term_parking")),
        has_ev_charging=None,                      # filled by Person D's EV matching
        rate_scheme_id=None,                       # filled by the rates seed
    )
    return info, ref


def parse_availability(payload: dict, known_ids: dict[str, str]) -> tuple[list[AvailabilityReading], set[str]]:
    """Raw availability JSON -> readings for carparks we know.

    known_ids: {car_park_no: internal carpark_id} from resolve_carpark_ids.
    Returns (readings, unknown car_park_no values).
    """
    items = payload.get("items") or []
    if not items:
        return [], set()
    item = items[0]
    collected = _parse_time(item.get("timestamp")) or datetime.now(SGT)

    readings: list[AvailabilityReading] = []
    unknown: set[str] = set()
    seen: set[tuple[str, LotType]] = set()
    for cp in item.get("carpark_data") or []:
        ref = (cp.get("carpark_number") or "").strip()
        cid = known_ids.get(ref)
        if cid is None:
            if ref:
                unknown.add(ref)
            continue
        observed = _parse_time(cp.get("update_datetime"))
        if observed is None:
            continue
        for info in cp.get("carpark_info") or []:
            lot_type = LOT_TYPES.get((info.get("lot_type") or "").strip().upper())
            available = _int(info.get("lots_available"))
            total = _int(info.get("total_lots"))
            if lot_type is None or available is None or (cid, lot_type) in seen:
                continue
            seen.add((cid, lot_type))
            readings.append(AvailabilityReading(
                carpark_id=cid, lot_type=lot_type, available_lots=max(available, 0),
                total_lots=total if total and total > 0 else None,
                observed_at=observed, collected_at=collected,
            ))
    return readings, unknown


def availability_refs(payload: dict) -> list[str]:
    items = payload.get("items") or []
    if not items:
        return []
    return [cp.get("carpark_number", "").strip() for cp in items[0].get("carpark_data") or []]


def _int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_time(s: Optional[str]) -> Optional[datetime]:
    """ISO time from the API. update_datetime has no offset -> it is Singapore time."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=SGT)
