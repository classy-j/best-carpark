"""URA carparks, rates and availability through the real database layer and search."""
from decimal import Decimal

from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.collectors.load_carparks import load
from app.collectors.seed_rates import seed
from app.collectors.ura import UraSync
from app.db.models import LotType
from app.db.repository import get_carpark, get_latest_availability, get_rate_rules, get_last_successful_run
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
from tests.unit.test_ura_data import SAMPLE

AVAIL = [{"carparkNo": "A0004", "lotType": "C", "lotsAvailable": "10"}]


class FakeUra:
    def __init__(self, details=SAMPLE, avail=AVAIL, error=None):
        self.details, self.avail, self.error = details, avail, error

    def fetch_details(self):
        if self.error:
            raise self.error
        return self.details

    def fetch_availability(self):
        if self.error:
            raise self.error
        return self.avail


def search(**kw):
    carparks, hist, m = CarparkRepository(), HistoricalAvailabilityRepository(), FakeMap()
    svc = SearchService(m, carparks, FeeCalculator(carparks), AvailabilityService(hist), BusynessEstimator(hist),
                        EVChargingService(), RankingEngine(), WalkingService(m))
    return svc.search_carparks(make_request(**kw), now=MONDAY_1PM)


def test_load_rates_and_fee():
    counts = UraSync(FakeUra()).load()
    assert counts["carparks"] == 1 and counts["schemes"] == 1
    assert get_carpark("URA:A0004").operator == "URA"
    assert len(get_rate_rules("URA:A0004", LotType.CAR)) == 6            # 2 windows x 3 day types
    fee = FeeCalculator(CarparkRepository()).calculate_fee_for(
        "URA:A0004", "CAR", MONDAY_1PM, MONDAY_1PM.replace(hour=15))
    assert fee == Decimal("2.40")                                        # 4 x $0.60 per 30 min
    sunday = MONDAY_1PM.replace(day=25)
    assert FeeCalculator(CarparkRepository()).calculate_fee_for(
        "URA:A0004", "CAR", sunday, sunday.replace(hour=15)) == Decimal("0.00")


def test_reload_is_idempotent():
    sync = UraSync(FakeUra())
    sync.load()
    sync.load()
    assert len(get_rate_rules("URA:A0004", LotType.CAR)) == 6


def test_poll_stores_availability_with_capacity():
    sync = UraSync(FakeUra())
    assert sync.poll_once() == 1                     # loads details first (fresh process)
    latest = get_latest_availability(["URA:A0004"], LotType.CAR)["URA:A0004"]
    assert (latest.available_lots, latest.total_lots) == (10, 40)
    assert get_last_successful_run("URA") is not None


def test_poll_failure_is_recorded_not_raised():
    assert UraSync(FakeUra(error=ApiClientError("down"))).poll_once() == 0


def test_search_returns_hdb_and_ura_together():
    load(INFO_RECORDS)
    seed(INFO_RECORDS)
    UraSync(FakeUra()).poll_once()
    res = search()
    ids = {r.carpark.carpark_id: r for r in res.results}
    assert set(ids) == {"HDB:ACB", "URA:A0004"}
    assert ids["URA:A0004"].estimated_fee_sgd == Decimal("2.40")
    assert ids["URA:A0004"].availability.occupancy_pct == 75             # 30 of 40 used


def test_collector_without_ura_key_skips_it():
    c = HistoricalAvailabilityCollector(None, HistoricalAvailabilityRepository())
    assert c.poll_ura() == 0
