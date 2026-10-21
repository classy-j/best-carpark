from fastapi import APIRouter, Depends

from app.dependencies import get_search_service
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


# Plain `def` (not async): the service layer is blocking, so FastAPI runs it in its threadpool.
@router.post("", response_model=SearchResponse)
def search_carparks(request: SearchRequest, service: SearchService = Depends(get_search_service)):
    return service.search_carparks(request)
