"""EV charging: LTA batch parsing and 75 m matching (no network)."""
from datetime import timedelta

import httpx
import pytest

from app.clients.lta_datamall import EVStation, LtaDataMallAdapter, normalise_station
from app.exceptions import ApiClientError
from app.schemas.carpark import CarparkOut
from app.services.ev_charging_service import EVChargingService
from tests.helpers import MONDAY_1PM, make_info

ACB = (1.301063, 103.854118)                     # Albert Centre
NEAR = (1.301300, 103.854300)                    # ~33 m away
FAR = (1.302000, 103.854118)                     # ~104 m away


def loc(lat, lng, statuses=("Available", "Occupied"), plug="Type 2"):
    return {"latitude": lat, "longtitude": lng, "chargingPoints": [
        {"status": "", "plugTypes": [{"plugType": plug, "evIds": [{"status": s} for s in statuses]}]}]}


class FakeSource:
    def __init__(self, stations=None, error=None):
        self.stations, self.error, self.calls = stations or [], error, 0

    def fetch_charging_points(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.stations


def out(lat, lng, has_ev=None):
    return CarparkOut.from_info(make_info("HDB:X", lat, lng, has_ev_charging=has_ev))


def test_normalise_counts_points_and_free():
    s = normalise_station(loc(*NEAR))
    assert (s.total_points, s.available_points, s.plug_types) == (2, 1, ("Type 2",))


def test_normalise_never_invents_a_charger_and_keeps_unknown_status():
    assert normalise_station({"latitude": 1.3, "longitude": 103.8}) is None
    s = normalise_station({"latitude": 1.3, "longitude": 103.8, "NoOfChargingPoints": 4})
    assert (s.total_points, s.available_points) == (4, None)          # count known, status not


def test_adapter_downloads_batch_file():
    def handler(req: httpx.Request):
        if req.url.path.endswith("/EVCBatch"):
            assert req.headers["AccountKey"] == "KEY"
            return httpx.Response(200, json={"value": [{"Link": "https://files.test/ev.json"}]})
        return httpx.Response(200, json={"evLocationsData": [loc(*NEAR), {"bad": 1}]})
    client = httpx.Client(base_url="https://lta.test", transport=httpx.MockTransport(handler))
    stations = LtaDataMallAdapter("https://lta.test", "KEY", http_client=client).fetch_charging_points()
    assert len(stations) == 1 and stations[0].total_points == 2


def test_adapter_without_key_raises_instead_of_returning_nothing():
    with pytest.raises(ApiClientError):
        LtaDataMallAdapter("https://lta.test", "").fetch_charging_points()


def test_match_within_75m_only():
    svc = EVChargingService(FakeSource([EVStation(*NEAR, 2, 1), EVStation(*FAR, 3, 3)]))
    assert svc.refresh()
    info = svc.get_charging_info(out(*ACB), now=None)
    assert info.supported is True and info.available_chargers == 1       # FAR station not counted
    assert svc.get_charging_info(out(1.35, 103.70)).supported is False
    flags = svc.match_flags([make_info("HDB:ACB", *ACB), make_info("HDB:Z", 1.35, 103.70)])
    assert flags == {"HDB:ACB": True, "HDB:Z": False}


def test_not_loaded_uses_stored_flag_and_writes_nothing():
    svc = EVChargingService(FakeSource(error=ApiClientError("down")))
    assert not svc.refresh()
    assert svc.get_charging_info(out(*ACB, has_ev=True)).supported is True
    assert svc.match_flags([make_info("HDB:ACB", *ACB)]) == {}           # never "False" on failure


def test_failed_refresh_keeps_previous_data():
    src = FakeSource([EVStation(*NEAR, 2, 1)])
    svc = EVChargingService(src)
    svc.refresh()
    src.error = ApiClientError("down")
    assert not svc.refresh()
    assert svc.get_charging_info(out(*ACB)).supported is True


def test_old_feed_hides_live_counts():
    svc = EVChargingService(FakeSource([EVStation(*NEAR, 2, 1)]))
    svc.refresh()
    later = svc._snapshot[1] + timedelta(hours=2)
    info = svc.get_charging_info(out(*ACB), now=later)
    assert info.supported is True and info.available_chargers is None
