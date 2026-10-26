"""LtaDataMallAdapter: realizes EVChargingSource (LTA DataMall).

TODO(EV owner): implement fetch_charging_points() against LTA DataMall's EV charging
dataset and match points to carparks (FR2.8/FR2.9). Until then EVChargingService uses
the carparks.has_ev_charging flag, and charger counts are shown as Unavailable.

fetch_availability() is kept from the earlier prototype (CarParkAvailabilityv2). It is
not used: availability comes from data.gov.sg, which also gives total lots and history.
"""
import requests
from typing import List, Dict, Any

class LTAClient:
    """Client for interacting with the external LTA DataMall API."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://datamall2.mytransport.sg/ltaodataservice"
        self.headers = {"AccountKey": self.api_key, "accept": "application/json"}

    def get_all_ev_chargers(self) -> List[Dict[str, Any]]:
        """Fetches and normalizes the complete islandwide EV charging dataset."""
        if not self.api_key:
            print("[LTAClient] Warning: No API key provided.")
            return []

        try:
            response = requests.get(f"{self.base_url}/EVCBatch", headers=self.headers, timeout=10)
            response.raise_for_status()
            
            val = response.json().get("value", [])
            if not val or "Link" not in val[0]:
                return []

            batch_res = requests.get(val[0]["Link"], timeout=25)
            batch_res.raise_for_status()
            batch_data = batch_res.json()

            raw_locations = batch_data.get("evLocationsData", []) if isinstance(batch_data, dict) else batch_data
            return self._normalize_ev_data(raw_locations)

        except requests.exceptions.RequestException as e:
            print(f"[LTAClient] Network Error: {e}")
            return []

    def _normalize_ev_data(self, raw_locations: List[Dict]) -> List[Dict[str, Any]]:
        """Normalizes LTA's nested schema into a flat list of dictionaries."""
        normalized = []
        for loc in raw_locations:
            lat = loc.get("latitude") or loc.get("Latitude")
            lon = loc.get("longtitude") or loc.get("longitude") or loc.get("Longitude")
            
            if lat is None or lon is None:
                continue

            total_points, available_points = 0, 0
            plug_types = set()

            for cp in loc.get("chargingPoints", []):
                cp_status = str(cp.get("status", "")).lower()
                for pt in cp.get("plugTypes", []):
                    p_type = pt.get("plugType") or pt.get("connectorType")
                    if p_type: plug_types.add(p_type)

                    ev_ids = pt.get("evIds", [])
                    if ev_ids:
                        for ev in ev_ids:
                            total_points += 1
                            if str(ev.get("status", cp_status)).lower() in ("available", "free", "1"):
                                available_points += 1
                    else:
                        total_points += 1
                        if cp_status in ("available", "free", "1"):
                            available_points += 1

            if total_points == 0:
                total_points = int(loc.get("NoOfChargingPoints", 1))

            normalized.append({
                "latitude": float(lat),
                "longitude": float(lon),
                "total_points": total_points,
                "available_points": available_points,
                "plug_types": sorted(plug_types) if plug_types else ["Standard"]
            })
            
        return normalized
