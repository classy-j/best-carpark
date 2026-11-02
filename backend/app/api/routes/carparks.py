from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_availability_service, get_busyness_estimator, get_carpark_repository
from app.repositories.carpark_repository import CarparkRepository
from app.schemas.carpark import Availability, CarparkOut, ExpectedBusyness
from app.schemas.search import LotTypeName
from app.services.availability_service import AvailabilityService
from app.services.busyness_estimator import BusynessEstimator
from app.utils.timeutil import now_sg, to_sg

router = APIRouter(prefix="/carparks", tags=["carparks"])


def _get_or_404(repo: CarparkRepository, carpark_id: str):
    carpark = repo.get_carpark_by_id(carpark_id)
    if carpark is None:
        raise HTTPException(status_code=404, detail=f"Carpark {carpark_id!r} not found")
    return carpark


@router.get("/{carpark_id}", response_model=CarparkOut)
def get_carpark(carpark_id: str, repo: CarparkRepository = Depends(get_carpark_repository)):
    return CarparkOut.from_info(_get_or_404(repo, carpark_id))


@router.get("/{carpark_id}/availability", response_model=Optional[Availability])
def current_availability(carpark_id: str, lot_type: LotTypeName = "CAR",
                         repo: CarparkRepository = Depends(get_carpark_repository),
                         service: AvailabilityService = Depends(get_availability_service)):
    _get_or_404(repo, carpark_id)
    return service.get_current_availability(carpark_id, lot_type)          # null = no data


@router.get("/{carpark_id}/expected-busyness", response_model=Optional[ExpectedBusyness])
def expected_busyness(carpark_id: str, lot_type: LotTypeName = "CAR",
                      at: Optional[datetime] = Query(None, description="Arrival time (SGT); default now"),
                      repo: CarparkRepository = Depends(get_carpark_repository),
                      estimator: BusynessEstimator = Depends(get_busyness_estimator)):
    _get_or_404(repo, carpark_id)
    return estimator.get_expected_busyness(carpark_id, lot_type, to_sg(at) if at else now_sg())
