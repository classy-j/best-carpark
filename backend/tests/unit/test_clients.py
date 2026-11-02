"""Adapter tests using httpx.MockTransport (no network)."""
import httpx
import pytest

from app.clients.lta_datamall import LtaDataMallAdapter
from app.clients.onemap import OneMapAdapter
from app.exceptions import AddressNotFoundError, ApiClientError
from app.schemas.carpark import Location


def mock_client(handler, base="https://example.test"):
    return httpx.Client(
        base_url=base,
        transport=httpx.MockTransport(handler),
    )


def test_onemap_walking_route_uses_token_and_parses_summary():
    seen = {}

    def handler(req: httpx.Request):
        if req.url.path.endswith("getToken"):
            return httpx.Response(
                200,
                json={
                    "access_token": "T",
                    "expiry_timestamp": "9999999999",
                },
            )

        seen["auth"] = req.headers.get("authorization")
        seen["q"] = dict(req.url.params)

        return httpx.Response(
            200,
            json={
                "route_summary": {
                    "total_time": 421,
                    "total_distance": 512.7,
                }
            },
        )

    client = OneMapAdapter(
        "https://x",
        "e",
        "p",
        http_client=mock_client(handler),
    )

    route = client.walking_route(
        Location(latitude=1.3, longitude=103.7),
        Location(latitude=1.31, longitude=103.71),
    )

    assert (route.distance_m, route.duration_s) == (513, 421)
    assert seen["auth"] == "T"
    assert seen["q"]["routeType"] == "walk"


def test_onemap_static_token():
    def handler(req: httpx.Request):
        assert not req.url.path.endswith("getToken")
        assert req.headers.get("authorization") == "STATIC"

        return httpx.Response(
            200,
            json={
                "route_summary": {
                    "total_time": 60,
                    "total_distance": 80,
                }
            },
        )

    client = OneMapAdapter(
        "https://x",
        token="STATIC",
        http_client=mock_client(handler),
    )

    route = client.walking_route(
        Location(latitude=1.3, longitude=103.7),
        Location(latitude=1.3, longitude=103.7),
    )

    assert route.duration_s == 60


def test_onemap_search_uses_token_and_geocodes():
    seen_auth = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("getToken"):
            return httpx.Response(
                200,
                json={
                    "access_token": "SEARCH_TOKEN",
                    "expiry_timestamp": "9999999999",
                },
            )

        seen_auth.append(
            req.headers.get("authorization")
        )

        if req.url.params["searchVal"] != "NTU":
            return httpx.Response(
                200,
                json={"results": []},
            )

        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "SEARCHVAL": "NTU NORTH SPINE",
                        "ADDRESS": "50 NANYANG AVE",
                        "LATITUDE": "1.3483",
                        "LONGITUDE": "103.6831",
                    },
                    {
                        "SEARCHVAL": "NTU NORTH SPINE DUP",
                        "LATITUDE": "1.34831",
                        "LONGITUDE": "103.68311",
                    },
                    {
                        "SEARCHVAL": "NTU SOUTH SPINE",
                        "LATITUDE": "1.3425",
                        "LONGITUDE": "103.6820",
                    },
                ]
            },
        )

    client = OneMapAdapter(
        "https://x",
        "e",
        "p",
        http_client=mock_client(handler),
    )

    assert [
        match.name
        for match in client.search_locations("NTU")
    ] == [
        "NTU NORTH SPINE",
        "NTU SOUTH SPINE",
    ]

    assert (
        client.geocode("NTU").latitude
        == pytest.approx(1.3483)
    )

    assert seen_auth

    assert all(
        value == "SEARCH_TOKEN"
        for value in seen_auth
    )

    with pytest.raises(AddressNotFoundError):
        client.geocode("zzzz")


def test_onemap_search_error_inside_http_200_becomes_api_client_error():
    def handler(req: httpx.Request):
        if req.url.path.endswith("getToken"):
            return httpx.Response(
                200,
                json={
                    "access_token": "T",
                    "expiry_timestamp": "9999999999",
                },
            )

        return httpx.Response(
            200,
            json={
                "error": "Authentication token expired.",
                "found": 0,
                "results": [],
            },
        )

    client = OneMapAdapter(
        "https://x",
        "e",
        "p",
        http_client=mock_client(handler),
    )

    with pytest.raises(
        ApiClientError,
        match="Authentication token expired",
    ):
        client.search_locations("NTU")


def test_onemap_missing_credentials_gives_clear_error():
    client = OneMapAdapter(
        "https://x",
        http_client=mock_client(
            lambda _: httpx.Response(500)
        ),
    )

    with pytest.raises(
        ApiClientError,
        match="OneMap credentials are missing",
    ):
        client.search_locations("NTU")


def test_http_errors_become_api_client_error():
    def handler(req: httpx.Request):
        if req.url.path.endswith("getToken"):
            return httpx.Response(
                200,
                json={
                    "access_token": "T",
                    "expiry_timestamp": "9999999999",
                },
            )

        return httpx.Response(500)

    client = OneMapAdapter(
        "https://x",
        "e",
        "p",
        http_client=mock_client(handler),
    )

    with pytest.raises(ApiClientError):
        client.geocode("NTU")


def test_lta_pagination():
    pages = {
        0: [
            {
                "CarParkID": str(i),
                "LotType": "C",
                "AvailableLots": i,
            }
            for i in range(500)
        ],
        500: [
            {
                "CarParkID": "ACB",
                "LotType": "C",
                "AvailableLots": 7,
            }
        ],
    }

    def handler(req: httpx.Request):
        return httpx.Response(
            200,
            json={
                "value": pages[
                    int(req.url.params["$skip"])
                ]
            },
        )

    rows = LtaDataMallAdapter(
        "https://x",
        "KEY",
        http_client=mock_client(handler),
    ).fetch_availability()

    assert len(rows) == 501
    assert rows[-1]["carpark_id"] == "ACB"