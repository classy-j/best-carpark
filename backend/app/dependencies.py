"""Composition root: builds adapters -> repositories -> services once and hands them to FastAPI."""
from functools import lru_cache

from app.clients.hdb import HdbAdapter
from app.clients.lta_datamall import LtaDataMallAdapter
from app.clients.onemap import OneMapAdapter
from app.clients.ura_data import UraClient
from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.config import Settings
from app.repositories.carpark_repository import CarparkRepository
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository
from app.services.availability_service import AvailabilityService
from app.services.busyness_estimator import BusynessEstimator
from app.services.ev_charging_service import EVChargingService
from app.services.fee_calculator import FeeCalculator
from app.services.ranking_engine import RankingEngine
from app.services.search_service import SearchService
from app.services.walking_service import WalkingService
from app.utils.public_holidays import sg_public_holidays


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---- adapters (interfaces to external actors) ----
@lru_cache
def get_map_service() -> OneMapAdapter:
    s = get_settings()
    return OneMapAdapter(s.onemap_base_url, s.onemap_email, s.onemap_password, s.onemap_api_token)


@lru_cache
def get_ev_source() -> LtaDataMallAdapter:
    s = get_settings()
    return LtaDataMallAdapter(s.lta_base_url, s.lta_api_key)


@lru_cache
def get_ev_charging_service() -> EVChargingService:
    """One instance per process, so the collector's download is what search reads."""
    return EVChargingService(get_ev_source())


# ---- persistent stores ----
@lru_cache
def get_carpark_repository() -> CarparkRepository:
    return CarparkRepository()


@lru_cache
def get_availability_repository() -> HistoricalAvailabilityRepository:
    return HistoricalAvailabilityRepository()


# ---- controls ----
@lru_cache
def get_availability_service() -> AvailabilityService:
    return AvailabilityService(get_availability_repository())


@lru_cache
def get_busyness_estimator() -> BusynessEstimator:
    return BusynessEstimator(get_availability_repository())


@lru_cache
def get_search_service() -> SearchService:
    s = get_settings()
    return SearchService(
        map_service=get_map_service(),
        carpark_repo=get_carpark_repository(),
        fee_calculator=FeeCalculator(get_carpark_repository(), holidays=sg_public_holidays()),
        availability_service=get_availability_service(),
        busyness_estimator=get_busyness_estimator(),
        ev_charging_service=get_ev_charging_service(),
        ranking_engine=RankingEngine(),
        walking_service=WalkingService(get_map_service()),
        search_radius_m=s.search_radius_m,
        max_walking_routes=s.max_walking_routes,
    )


def build_collector() -> HistoricalAvailabilityCollector:
    return HistoricalAvailabilityCollector(HdbAdapter(), get_availability_repository(),
                                           get_settings().collect_interval_minutes,
                                           ev_service=get_ev_charging_service(),
                                           ura=_build_ura_sync())


def _build_ura_sync():
    """None until URA_API_KEY is set, so the collector simply skips URA."""
    key = get_settings().ura_api_key
    if not key:
        return None
    from app.collectors.ura import UraSync
    return UraSync(UraClient(key))
