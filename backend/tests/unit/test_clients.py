"""Adapter tests using httpx.MockTransport (no network)."""
import httpx
import pytest

from app.clients.lta_datamall import LtaDataMallAdapter
from app.clients.onemap import OneMapAdapter
from app.exceptions import AddressNotFoundError, ApiClientError
from app.schemas.carpark import Location


def mock_client(handler, base="https://example.test"):
    return httpx.Client(base_url=base, transport=httpx.MockTransport(handler))


def test_onemap_walking_route_uses_token_and_parses_summary():
    seen = {}

    def handler(req: httpx.Request):
        if req.url.path.endswith("getToken"):
            return httpx.Response(200, json={"access_token": "T", "expiry_timestamp": "9999999999"})
        seen["auth"], seen["q"] = req.headers.get("authorization"), dict(req.url.params)
        return httpx.Response(200, json={"route_summary": {"total_time": 421, "total_distance": 512.7}})

    c = OneMapAdapter("https://x", "e", "p", http_client=mock_client(handler))
    route = c.walking_route(Location(latitude=1.3, longitude=103.7), Location(latitude=1.31, longitude=103.71))
    assert (route.distance_m, route.duration_s) == (513, 421)
    assert seen["auth"] == "T" and seen["q"]["routeType"] == "walk"


def test_onemap_static_token():
    def handler(req):
        assert not req.url.path.endswith("getToken")
        return httpx.Response(200, json={"route_summary": {"total_time": 60, "total_distance": 80}})
    c = OneMapAdapter("https://x", token="STATIC", http_client=mock_client(handler))
    assert c.walking_route(Location(latitude=1.3, longitude=103.7), Location(latitude=1.3, longitude=103.7)).duration_s == 60


def test_onemap_search_and_geocode():
    def handler(req):
        if req.url.params["searchVal"] != "NTU":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"results": [
            {"SEARCHVAL": "NTU NORTH SPINE", "ADDRESS": "50 NANYANG AVE", "LATITUDE": "1.3483", "LONGITUDE": "103.6831"},
            {"SEARCHVAL": "NTU NORTH SPINE DUP", "LATITUDE": "1.34831", "LONGITUDE": "103.68311"},   # same place
            {"SEARCHVAL": "NTU SOUTH SPINE", "LATITUDE": "1.3425", "LONGITUDE": "103.6820"}]})

    c = OneMapAdapter("https://x", "e", "p", http_client=mock_client(handler))
    assert [m.name for m in c.search_locations("NTU")] == ["NTU NORTH SPINE", "NTU SOUTH SPINE"]
    assert c.geocode("NTU").latitude == pytest.approx(1.3483)
    with pytest.raises(AddressNotFoundError):
        c.geocode("zzzz")


def test_http_errors_become_api_client_error():
    c = OneMapAdapter("https://x", "e", "p", http_client=mock_client(lambda r: httpx.Response(500)))
    with pytest.raises(ApiClientError):
        c.geocode("NTU")


def test_lta_pagination():
    pages = {0: [{"CarParkID": str(i), "LotType": "C", "AvailableLots": i} for i in range(500)],
             500: [{"CarParkID": "ACB", "LotType": "C", "AvailableLots": 7}]}
    handler = lambda req: httpx.Response(200, json={"value": pages[int(req.url.params["$skip"])]})
    rows = LtaDataMallAdapter("https://x", "KEY", http_client=mock_client(handler)).fetch_availability()
    assert len(rows) == 501 and rows[-1]["carpark_id"] == "ACB"
