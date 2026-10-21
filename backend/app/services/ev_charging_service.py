"""EVChargingService «control»: EV charging information per carpark (UC-06, FR6.4).

For now this uses the carparks.has_ev_charging flag (None = unknown). When
LtaDataMallAdapter.fetch_charging_points() is implemented, match points to carparks here
(FR2.9: shared id or proximity) and fill available_chargers.
"""
from typing import Optional

from app.clients.interfaces import EVChargingSource
from app.schemas.carpark import CarparkOut, EVCharging


class EVChargingService:
    def __init__(self, source: Optional[EVChargingSource] = None):
        self._source = source

    def get_charging_info(self, carpark: CarparkOut) -> EVCharging:
        return EVCharging(supported=carpark.has_ev_charging, available_chargers=None)
