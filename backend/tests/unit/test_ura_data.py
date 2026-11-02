"""URA Data Service: parsing and token handling (no network)."""
from datetime import time
from decimal import Decimal

import httpx
import pytest

from app.clients import ura_data as ura
from app.db.models import DayType, LotType
from app.exceptions import ApiClientError

# A URA carpark ~45 m from Albert Centre (HDB:ACB is at SVY21 30314.79, 31490.49)
NEAR_XY = "30350.0,31520.0"


def row(code="A0004", veh="Car", start="07.00 AM", end="05.00 PM", wk="$0.60", wkmin="30 mins",
        sat="$0.60", satmin="30 mins", sun="$0.00", sunmin="0 mins", xy=NEAR_XY, cap=40, system="B"):
    return {"ppCode": code, "ppName": "WATERLOO STREET", "vehCat": veh, "startTime": start, "endTime": end,
            "weekdayRate": wk, "weekdayMin": wkmin, "satdayRate": sat, "satdayMin": satmin,
            "sunPHRate": sun, "sunPHMin": sunmin, "parkingSystem": system, "parkCapacity": cap,
            "geometries": [{"coordinates": xy}]}


SAMPLE = [row(), row(start="05.00 PM", end="07.00 AM", wk="$0.60", sat="$0.60", sun="$0.60", sunmin="30 mins"),
          row(veh="Motorcycle", start="12.00 AM", end="12.00 AM", wk="$0.65", wkmin="510 mins",
              sat="$0.65", satmin="510 mins", sun="$0.65", sunmin="510 mins", cap=10),
          row(code="BAD", xy="")]


def test_small_parsers():
    assert ura.parse_money("$1.20") == Decimal("1.20") and ura.parse_money("-") is None
    assert ura.parse_minutes("30 mins") == 30 and ura.parse_minutes("0 mins") is None
    assert ura.parse_time("07.00 AM") == time(7) and ura.parse_time("12.00 AM") == time(0)
    assert ura.parse_time("12.30 PM") == time(12, 30) and ura.parse_time("5:00 PM") == time(17)
    assert ura.parse_time("25.00 PM") is None and ura.parse_time("") is None


def test_location_svy21():
    lat, lng = ura.parse_location(row())
    assert 1.300 < lat < 1.303 and 103.853 < lng < 103.856          # next to Albert Centre
    assert ura.parse_location(row(xy="garbage")) is None
    assert ura.parse_location(row(xy="900000,900000")) is None       # outside Singapore


def test_details_carparks_rates_capacity():
    carparks, rates, capacity = ura.parse_details(SAMPLE)
    assert [ref for _, ref in carparks] == ["A0004"]                 # BAD has no coordinates
    info = carparks[0][0]
    assert (info.carpark_id, info.operator, info.parking_system) == ("URA:A0004", "URA", "ELECTRONIC")
    r = rates["A0004"]
    car_wk = [x for x in r if x.lot_type == LotType.CAR and x.day_type == DayType.WEEKDAY]
    assert {(x.start, x.end, x.rate, x.interval_min) for x in car_wk} == {
        (time(7), time(17), Decimal("0.60"), 30), (time(17), time(7), Decimal("0.60"), 30)}
    sun_day = [x for x in r if x.day_type == DayType.SUNDAY_PH and x.start == time(7)]
    assert sun_day[0].rate == 0                                      # free on Sunday daytime
    assert capacity == {("A0004", LotType.CAR): 40, ("A0004", LotType.MOTORCYCLE): 10}


def test_availability_uses_capacity_and_skips_unknown():
    _, _, capacity = ura.parse_details(SAMPLE)
    rows = [{"carparkNo": "A0004", "lotType": "C", "lotsAvailable": "10"},
            {"carparkNo": "A0004", "lotType": "M", "lotsAvailable": "3"},
            {"carparkNo": "ZZZ", "lotType": "C", "lotsAvailable": "5"}]
    readings, unknown = ura.parse_availability(rows, {"A0004": "URA:A0004"}, capacity)
    assert {(r.lot_type, r.available_lots, r.total_lots) for r in readings} == {
        (LotType.CAR, 10, 40), (LotType.MOTORCYCLE, 3, 10)}
    assert unknown == {"ZZZ"}


def mock(handler):
    return ura.UraClient("KEY", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_client_gets_daily_token_and_sends_headers():
    seen = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("insertNewToken/v1"):
            assert req.headers["AccessKey"] == "KEY"
            return httpx.Response(200, json={"Status": "Success", "Result": "TOK"})
        seen.append((req.url.params["service"], req.headers["Token"]))
        return httpx.Response(200, json={"Status": "Success", "Result": SAMPLE})

    c = mock(handler)
    assert c.fetch_details() == SAMPLE and c.fetch_availability() == SAMPLE
    assert seen == [("Car_Park_Details", "TOK"), ("Car_Park_Availability", "TOK")]


def test_client_retries_with_new_token_then_raises():
    calls = {"token": 0}

    def handler(req):
        if req.url.path.endswith("insertNewToken/v1"):
            calls["token"] += 1
            return httpx.Response(200, json={"Status": "Success", "Result": f"T{calls['token']}"})
        return httpx.Response(200, json={"Status": "Error", "Message": "Invalid token"})

    with pytest.raises(ApiClientError):
        mock(handler).fetch_details()
    assert calls["token"] == 2


def test_no_key_raises():
    with pytest.raises(ApiClientError):
        ura.UraClient("").fetch_details()
