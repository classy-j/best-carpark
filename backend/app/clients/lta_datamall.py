"""LtaDataMallAdapter: realizes EVChargingSource (LTA DataMall).

fetch_charging_points() downloads LTA's EV charging batch file (EVCBatch: the API answers
with a link to a JSON file of every charging location in Singapore) and normalises each
location into an EVStation. Matching stations to carparks is EVChargingService's job.
Ported from feature/evinfo EVcharging.py (LTAClient), on httpx like the other adapters.

fetch_availability() is kept from the earlier prototype (CarParkAvailabilityv2). It is
not used: availability comes from data.gov.sg, which also gives total lots and history.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.clients.base import BaseApiClient
from app.exceptions import ApiClientError
from app.utils.timeutil import now_sg

# Status values counted as "free". TODO(EV owner): confirm against a real EVCBatch file;
# if LTA uses other values, every charger will show as occupied.
FREE_STATUSES = {"available", "free", "1"}


@dataclass(frozen=True)
class EVStation:
    latitude: float
    longitude: float
    total_points: int
    available_points: Optional[int]      # None = feed gave no status for this location
    plug_types: tuple[str, ...] = ()


def _float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalise_station(loc: dict) -> Optional[EVStation]:
    """One location from the batch file -> EVStation. None if unusable."""
    lat = _float(loc.get("latitude") or loc.get("Latitude"))
    lng = _float(loc.get("longtitude") or loc.get("longitude") or loc.get("Longitude"))  # LTA spells it "longtitude"
    if lat is None or lng is None:
        return None

    total, free, status_seen, plugs = 0, 0, False, set()
    for cp in loc.get("chargingPoints") or []:
        cp_status = str(cp.get("status", "")).strip().lower()
        for pt in cp.get("plugTypes") or []:
            plug = pt.get("plugType") or pt.get("connectorType")
            if plug:
                plugs.add(str(plug))
            for status in ([str(ev.get("status", cp_status)).strip().lower() for ev in pt.get("evIds") or []]
                           or [cp_status]):
                total += 1
                if status:
                    status_seen = True
                    free += status in FREE_STATUSES

    if total == 0:                              # no point details: fall back to the stated count
        try:
            total = int(loc.get("NoOfChargingPoints") or 0)
        except (TypeError, ValueError):
            total = 0
    if total <= 0:
        return None                             # never invent a charger
    return EVStation(lat, lng, total, free if status_seen else None, tuple(sorted(plugs)))


class LtaDataMallAdapter(BaseApiClient):
    PAGE_SIZE = 500

    def __init__(self, base_url: str, account_key: str, **kwargs):
        super().__init__(base_url, **kwargs)
        self._has_key = bool(account_key)
        self._headers = {"AccountKey": account_key, "accept": "application/json"}

    def fetch_charging_points(self) -> list[EVStation]:
        """All EV charging locations. Raises ApiClientError on any failure, so a download
        problem is never mistaken for "no chargers anywhere"."""
        if not self._has_key:
            raise ApiClientError("LTA_API_KEY is not set")
        meta = self._request("GET", "/EVCBatch", headers=self._headers)
        value = (meta or {}).get("value") or []
        link = value[0].get("Link") if value and isinstance(value[0], dict) else None
        if not link:
            raise ApiClientError(f"EVCBatch returned no download link: {meta!r:.200}")
        data = self._request("GET", link, timeout=60)     # absolute URL (file host), large file
        raw = data.get("evLocationsData", []) if isinstance(data, dict) else data
        stations = [s for s in map(normalise_station, raw or []) if s is not None]
        if not stations:
            raise ApiClientError("EV batch file contained no usable stations")
        return stations

    def fetch_availability(self, recorded_at: datetime | None = None) -> list[dict]:
        recorded_at = recorded_at or now_sg()
        rows_out, skip = [], 0
        while True:
            data = self._request("GET", "/CarParkAvailabilityv2", headers=self._headers, params={"$skip": skip})
            rows = data.get("value", [])
            rows_out.extend({"carpark_id": str(r["CarParkID"]), "lot_type": r["LotType"],
                             "available_lots": int(r["AvailableLots"]), "recorded_at": recorded_at} for r in rows)
            if len(rows) < self.PAGE_SIZE:
                return rows_out
            skip += self.PAGE_SIZE
