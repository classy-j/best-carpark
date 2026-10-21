"""Collector tests. No network: the data.gov.sg calls are replaced with sample data
copied from the real API responses."""
from datetime import timedelta


from app.clients import hdb_data as hdb
from app.collectors.load_carparks import load
from app.utils.svy21 import svy21_to_wgs84
from app.db import repository as repo
from app.db.models import LotType, Source
from app.clients.hdb import HdbAdapter
from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository


def _collector():
    return HistoricalAvailabilityCollector(HdbAdapter(), HistoricalAvailabilityRepository())

# First 3 rows of the real 'HDB Carpark Information' dataset
INFO_RECORDS = [
    {"_id": 1, "car_park_no": "ACB", "address": "BLK 270/271 ALBERT CENTRE BASEMENT CAR PARK",
     "x_coord": "30314.7936", "y_coord": "31490.4942", "car_park_type": "BASEMENT CAR PARK",
     "type_of_parking_system": "ELECTRONIC PARKING", "short_term_parking": "WHOLE DAY",
     "free_parking": "NO", "night_parking": "YES", "car_park_decks": "1",
     "gantry_height": "1.8", "car_park_basement": "Y"},
    {"_id": 2, "car_park_no": "ACM", "address": "BLK 98A ALJUNIED CRESCENT",
     "x_coord": "33758.4143", "y_coord": "33695.5198", "car_park_type": "MULTI-STOREY CAR PARK",
     "type_of_parking_system": "ELECTRONIC PARKING", "short_term_parking": "WHOLE DAY",
     "free_parking": "SUN & PH FR 7AM-10.30PM", "night_parking": "YES", "car_park_decks": "5",
     "gantry_height": "2.1", "car_park_basement": "N"},
    {"_id": 3, "car_park_no": "AH1", "address": "BLK 101 JALAN DUSUN",
     "x_coord": "29257.7203", "y_coord": "34500.3599", "car_park_type": "SURFACE CAR PARK",
     "type_of_parking_system": "ELECTRONIC PARKING", "short_term_parking": "WHOLE DAY",
     "free_parking": "SUN & PH FR 7AM-10.30PM", "night_parking": "YES", "car_park_decks": "0",
     "gantry_height": "0", "car_park_basement": "N"},
]


def availability_payload(ts="2026-10-18T00:54:36+08:00", acb_available="102", acb_time="2026-10-18T00:53:32"):
    return {"items": [{"timestamp": ts, "carpark_data": [
        {"carpark_number": "ACB", "update_datetime": acb_time, "carpark_info": [
            {"total_lots": "105", "lot_type": "C", "lots_available": acb_available},
            {"total_lots": "20", "lot_type": "Y", "lots_available": "5"},
            {"total_lots": "4", "lot_type": "S", "lots_available": "1"},          # unsupported type
            {"total_lots": "105", "lot_type": "C", "lots_available": "1"},        # duplicate -> ignored
        ]},
        {"carpark_number": "ACM", "update_datetime": "2026-10-18T00:53:53", "carpark_info": [
            {"total_lots": "0", "lot_type": "H", "lots_available": "3"},          # total 0 -> None
        ]},
        {"carpark_number": "ZZZ9", "update_datetime": "2026-10-18T00:53:00", "carpark_info": [
            {"total_lots": "50", "lot_type": "C", "lots_available": "10"},        # not in our DB
        ]},
    ]}]}


# ---------------------------------------------------------------- parsing

def test_svy21_known_point():
    lat, lng = svy21_to_wgs84(30314.7936, 31490.4942)   # Albert Centre
    assert abs(lat - 1.301063) < 1e-5 and abs(lng - 103.854118) < 1e-5


def test_parse_carpark_info():
    info, ref = hdb.parse_carpark_info(INFO_RECORDS[0])
    assert ref == "ACB" and info.carpark_id == "HDB:ACB"
    assert info.carpark_type == "BASEMENT"
    assert info.parking_system == "ELECTRONIC"
    assert info.free_parking == "NO" and info.night_parking is True
    assert info.gantry_height_m == 1.8
    assert hdb.parse_carpark_info(INFO_RECORDS[1])[0].free_parking == "SUN_PH_FR_7AM_10_30PM"
    surface = hdb.parse_carpark_info(INFO_RECORDS[2])[0]
    assert surface.carpark_type == "SURFACE" and surface.gantry_height_m is None
    assert hdb.parse_carpark_info({"car_park_no": "X", "x_coord": "", "y_coord": "1"}) is None


def test_parse_availability():
    known = {"ACB": "HDB:ACB", "ACM": "HDB:ACM"}
    readings, unknown = hdb.parse_availability(availability_payload(), known)
    by_key = {(r.carpark_id, r.lot_type): r for r in readings}
    assert set(by_key) == {("HDB:ACB", LotType.CAR), ("HDB:ACB", LotType.MOTORCYCLE),
                           ("HDB:ACM", LotType.HEAVY_VEHICLE)}
    car = by_key[("HDB:ACB", LotType.CAR)]
    assert car.available_lots == 102 and car.total_lots == 105        # first entry kept
    assert car.observed_at.utcoffset() == timedelta(hours=8)          # naive -> SGT
    assert by_key[("HDB:ACM", LotType.HEAVY_VEHICLE)].total_lots is None
    assert unknown == {"ZZZ9"}
    assert hdb.parse_availability({"items": []}, known) == ([], set())


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "snap.csv"
    hdb.save_records_csv(INFO_RECORDS, path)
    rows = hdb.read_records_csv(path)
    assert [r["car_park_no"] for r in rows] == ["ACB", "ACM", "AH1"]
    assert hdb.parse_carpark_info(rows[0])[0].carpark_id == "HDB:ACB"


# ---------------------------------------------------------------- with database

def test_load_into_db():
    assert load(INFO_RECORDS + [{"car_park_no": "BAD"}]) == (3, 1)
    assert load(INFO_RECORDS) == (3, 0)                                # re-run: no duplicates
    near = repo.find_carparks_near(1.3010, 103.8541, radius_m=500)
    assert [n.carpark.carpark_id for n in near] == ["HDB:ACB"]
    assert repo.resolve_carpark_ids(Source.HDB, ["ACB", "ACM", "AH1"]) == {
        "ACB": "HDB:ACB", "ACM": "HDB:ACM", "AH1": "HDB:AH1"}


def test_poll_once_stores_and_dedupes(monkeypatch):
    load(INFO_RECORDS)
    monkeypatch.setattr(hdb, "fetch_availability", lambda at=None: availability_payload())
    assert _collector().poll_once() == 3
    assert _collector().poll_once() == 0                                 # same readings again
    monkeypatch.setattr(hdb, "fetch_availability",
                        lambda at=None: availability_payload(acb_available="50", acb_time="2026-10-18T01:03:32"))
    assert _collector().poll_once() == 2                                 # ACB C + Y changed time
    latest = repo.get_latest_availability(["HDB:ACB"], LotType.CAR)["HDB:ACB"]
    assert latest.available_lots == 50
    assert repo.get_last_successful_run("HDB").rows_inserted == 2


def test_poll_failure_is_recorded_not_raised(monkeypatch):
    load(INFO_RECORDS)

    def boom(at=None):
        raise ConnectionError("data.gov.sg down")
    monkeypatch.setattr(hdb, "fetch_availability", boom)
    assert _collector().poll_once() == 0                                 # no exception
    assert repo.get_last_successful_run("HDB") is None


def test_poll_without_carparks_loaded_fails_clearly(monkeypatch):
    monkeypatch.setattr(hdb, "fetch_availability", lambda at=None: availability_payload())
    assert _collector().poll_once() == 0
    assert repo.get_last_successful_run("HDB") is None
