"""LtaDataMallAdapter: realizes EVChargingSource (LTA DataMall).

TODO(EV owner): implement fetch_charging_points() against LTA DataMall's EV charging
dataset and match points to carparks (FR2.8/FR2.9). Until then EVChargingService uses
the carparks.has_ev_charging flag, and charger counts are shown as Unavailable.

fetch_availability() is kept from the earlier prototype (CarParkAvailabilityv2). It is
not used: availability comes from data.gov.sg, which also gives total lots and history.
"""
from datetime import datetime

from app.clients.base import BaseApiClient
from app.utils.timeutil import now_sg


class LtaDataMallAdapter(BaseApiClient):
    PAGE_SIZE = 500

    def __init__(self, base_url: str, account_key: str, **kwargs):
        super().__init__(base_url, **kwargs)
        self._headers = {"AccountKey": account_key, "accept": "application/json"}

    def fetch_charging_points(self) -> list[dict]:
        raise NotImplementedError("LTA EV charging points not wired up yet (see module docstring)")

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
