"""EV flags written to the database make the "EV required" filter work end to end."""
from app.clients.lta_datamall import EVStation
from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.collectors.load_carparks import load
from app.collectors.seed_rates import seed
from app.db.repository import get_carpark, set_ev_flags
from app.exceptions import ApiClientError
from app.repositories.carpark_repository import CarparkRepository
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository
from app.services.availability_service import AvailabilityService
from app.services.busyness_estimator import BusynessEstimator
from app.services.ev_charging_service import EVChargingService
from app.services.fee_calculator import FeeCalculator
from app.services.ranking_engine import RankingEngine
from app.services.search_service import SearchService
from app.services.walking_service import WalkingService
from tests.database.test_hdb_collector import INFO_RECORDS
from tests.helpers import MONDAY_1PM, FakeMap, make_request
from tests.unit.test_ev_charging import NEAR, FakeSource


def collector(source):
    return HistoricalAvailabilityCollector(None, HistoricalAvailabilityRepository(),
                                           ev_service=EVChargingService(source))


def search(ev_required):
    carparks, hist, m = CarparkRepository(), HistoricalAvailabilityRepository(), FakeMap()
    svc = SearchService(m, carparks, FeeCalculator(carparks), AvailabilityService(hist), BusynessEstimator(hist),
                        EVChargingService(), RankingEngine(), WalkingService(m))
    return svc.search_carparks(make_request(preference={"ev_required": ev_required}), now=MONDAY_1PM)


def test_set_ev_flags():
    load(INFO_RECORDS)
    assert set_ev_flags({"HDB:ACB": True}) == 1
    assert get_carpark("HDB:ACB").has_ev_charging is True


def test_refresh_ev_enables_ev_required_search():
    load(INFO_RECORDS)
    seed(INFO_RECORDS)
    assert search(True).results == []                       # before: flag unknown -> nothing
    assert collector(FakeSource([EVStation(*NEAR, 2, 1)])).refresh_ev() > 0
    res = search(True)
    assert [r.carpark.carpark_id for r in res.results] == ["HDB:ACB"]
    assert res.results[0].ev_charging.supported is True
    assert get_carpark("HDB:AH1").has_ev_charging is False   # far from the station


def test_failed_download_keeps_existing_flags():
    load(INFO_RECORDS)
    set_ev_flags({"HDB:ACB": True})
    assert collector(FakeSource(error=ApiClientError("down"))).refresh_ev() == 0
    assert get_carpark("HDB:ACB").has_ev_charging is True


def test_loader_reload_does_not_wipe_flags():
    load(INFO_RECORDS)
    set_ev_flags({"HDB:ACB": True})
    load(INFO_RECORDS)                                       # daily carpark refresh
    assert get_carpark("HDB:ACB").has_ev_charging is True
