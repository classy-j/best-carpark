from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_search_service
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import SearchService
from app.utils.timeutil import now_sg

ARRIVAL_GRACE = timedelta(minutes=15)   # same grace as the search form (SearchEntryUI.ARRIVAL_GRACE_MIN)

router = APIRouter(prefix="/search", tags=["search"])


# Plain `def` (not async): the service layer is blocking, so FastAPI runs it in its threadpool.
@router.post("", response_model=SearchResponse)
def search_carparks(request: SearchRequest, service: SearchService = Depends(get_search_service)):
    if request.arrival_time < now_sg() - ARRIVAL_GRACE:              # UC-02: checked again on the server
        raise HTTPException(status_code=422, detail="Arrival time can't be in the past.")
    return service.search_carparks(request)
