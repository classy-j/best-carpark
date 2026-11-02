"""API tests with the service layer faked out."""
from fastapi.testclient import TestClient

from app.dependencies import get_search_service
from app.exceptions import AddressNotFoundError, ApiClientError, MultipleDestinationsError
from app.main import create_app
from app.schemas.carpark import Location
from app.schemas.search import PlaceMatch, SearchResponse

BODY = {"destination_address": "NTU", "arrival_time": "2099-10-19T13:00:00",
        "departure_time": "2099-10-19T15:00:00", "preference": {"priority_ranking": ["distance", "cost"]}}


class StubService:
    def __init__(self, error=None):
        self.error = error

    def search_carparks(self, request):
        if self.error:
            raise self.error
        return SearchResponse(destination_address=request.destination_address,
                              destination=Location(latitude=1.3, longitude=103.7), results=[])


def client_with(service):
    app = create_app()
    app.dependency_overrides[get_search_service] = lambda: service
    return TestClient(app)


def test_search_ok():
    r = client_with(StubService()).post("/api/v1/search", json=BODY)
    assert r.status_code == 200 and r.json()["results"] == []


def test_validation_error_is_422():
    r = client_with(StubService()).post("/api/v1/search", json={**BODY, "departure_time": "2099-10-19T12:00:00"})
    assert r.status_code == 422


def test_error_mapping():
    post = lambda err: client_with(StubService(err)).post("/api/v1/search", json=BODY)
    assert post(AddressNotFoundError("x")).status_code == 404
    assert post(ApiClientError("x")).status_code == 502
    r = post(MultipleDestinationsError([PlaceMatch(name="A", location=Location(latitude=1.3, longitude=103.7))]))
    assert r.status_code == 409 and r.json()["matches"][0]["name"] == "A"


def test_health():
    assert client_with(StubService()).get("/health").json() == {"status": "ok"}


def test_past_arrival_is_422():
    r = client_with(StubService()).post("/api/v1/search", json={**BODY, "arrival_time": "2020-01-06T13:00:00",
                                                               "departure_time": "2020-01-06T15:00:00"})
    assert r.status_code == 422
