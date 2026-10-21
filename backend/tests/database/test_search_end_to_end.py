"""Whole search against the real database layer (carparks + rates + availability); OneMap faked."""
from datetime import timedelta
from decimal import Decimal

from app.collectors.load_carparks import load
from app.collectors.seed_rates import seed
from app.db.models import LotType
from app.db.records import AvailabilityReading
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


def test_search_albert_centre():
    load(INFO_RECORDS)
    seed(INFO_RECORDS)
    hist = HistoricalAvailabilityRepository()
    fresh = MONDAY_1PM - timedelta(minutes=5)
    hist.save_availability_records(
        [AvailabilityReading("HDB:ACB", LotType.CAR, 20, 100, fresh, fresh)] +
        [AvailabilityReading("HDB:ACB", LotType.CAR, 50, 100, MONDAY_1PM - timedelta(days=7 * k), fresh)
         for k in range(1, 4)])

    carparks, m = CarparkRepository(), FakeMap()
    svc = SearchService(m, carparks, FeeCalculator(carparks), AvailabilityService(hist), BusynessEstimator(hist),
                        EVChargingService(), RankingEngine(), WalkingService(m))
    res = svc.search_carparks(make_request(), now=MONDAY_1PM)

    [acb] = res.results                                      # ACM / AH1 are > 1 km away
    assert acb.carpark.carpark_id == "HDB:ACB"
    assert acb.estimated_fee_sgd == Decimal("4.80")          # Central Area, Mon 13:00-15:00: 120 min x $0.04
    assert acb.availability.available_lots == 20 and not acb.availability.is_stale
    assert acb.expected_busyness.occupancy_pct == 58      # (80 + 50 + 50 + 50) / 4: same weekday + time slot
    assert acb.expected_busyness.level == "LOW"
