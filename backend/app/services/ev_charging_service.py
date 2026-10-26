import math
from typing import List, Dict, Any
from app.clients.lta_datamall import LTAClient

def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates distance in meters between two WGS84 coordinates."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

class EVChargingService:
    """Service layer for matching EV charging locations to carparks."""
    
    def __init__(self, lta_client: LTAClient):
        self.client = lta_client
        self._ev_cache: List[Dict[str, Any]] = []

    def refresh_ev_data(self) -> None:
        """Pulls fresh data from LTA and stores it in memory."""
        fetched_data = self.client.get_all_ev_chargers()
        if fetched_data:
            self._ev_cache = fetched_data

    def get_charging_info(self, carpark: Any, max_distance_m: int = 75) -> Dict[str, Any]:
        """
        BACKEND_INTERFACES: get_charging_info(carpark: CarparkOut)
        Extracts coordinates from the carpark object and cross-references them.
        """
        if not self._ev_cache:
            return {
                "has_ev": None,
                "total_chargers": 0,
                "available_chargers": 0,
                "plug_types": []
            }

        # Extract coordinates directly from Person C's CarparkOut object
        carpark_lat = carpark.latitude
        carpark_lon = carpark.longitude

        total_chargers, available_chargers = 0, 0
        connector_types = set()

        for station in self._ev_cache:
            dist = haversine_distance_m(carpark_lat, carpark_lon, station["latitude"], station["longitude"])
            if dist <= max_distance_m:
                total_chargers += station["total_points"]
                available_chargers += station["available_points"]
                connector_types.update(station["plug_types"])

        if total_chargers > 0:
            return {
                "has_ev": True,
                "total_chargers": total_chargers,
                "available_chargers": available_chargers,
                "plug_types": sorted(connector_types)
            }

        return {
            "has_ev": False,
            "total_chargers": 0,
            "available_chargers": 0,
            "plug_types": []
        }
