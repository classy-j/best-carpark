"""Optional live tests for Person C's OneMap integration.

These tests are skipped unless OneMap credentials are configured in backend/.env.
They make real network requests and therefore are kept separate from unit tests.
"""
import pytest

from app.clients.onemap import OneMapAdapter
from app.config import Settings
from app.schemas.carpark import Location


@pytest.fixture(scope="module")
def live_onemap() -> OneMapAdapter:
    settings = Settings()

    has_login = bool(
        settings.onemap_email
        and settings.onemap_password
    )

    has_token = bool(
        settings.onemap_api_token
    )

    if not (has_login or has_token):
        pytest.skip(
            "Set ONEMAP_EMAIL + ONEMAP_PASSWORD "
            "or ONEMAP_API_TOKEN in backend/.env"
        )

    return OneMapAdapter(
        settings.onemap_base_url,
        settings.onemap_email,
        settings.onemap_password,
        settings.onemap_api_token,
    )


def test_live_onemap_search(
    live_onemap: OneMapAdapter,
):
    matches = live_onemap.search_locations(
        "Nanyang Technological University"
    )

    assert matches

    assert all(
        1.1 <= match.location.latitude <= 1.5
        for match in matches
    )

    assert all(
        103.5 <= match.location.longitude <= 104.1
        for match in matches
    )


def test_live_onemap_walking_route(
    live_onemap: OneMapAdapter,
):
    # Coordinates from OneMap's official
    # routing documentation example.
    start = Location(
        latitude=1.319728,
        longitude=103.8421,
    )

    end = Location(
        latitude=1.319728905,
        longitude=103.8421581,
    )

    route = live_onemap.walking_route(
        start,
        end,
    )

    assert route.distance_m > 0
    assert route.duration_s > 0