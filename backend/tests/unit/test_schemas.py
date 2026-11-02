from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.db.records import SGT
from tests.helpers import make_request


def test_departure_must_be_after_arrival():
    with pytest.raises(ValidationError):
        make_request(arrival_time="2026-10-19T15:00:00", departure_time="2026-10-19T14:00:00")


def test_duration_instead_of_departure():          # UC-01 AF2
    r = make_request(departure_time=None, parking_duration_minutes=90)
    assert r.get_parking_duration() == timedelta(minutes=90)
    with pytest.raises(ValidationError):
        make_request(departure_time=None)


def test_blank_address_rejected():
    with pytest.raises(ValidationError):
        make_request(destination_address="   ")


def test_priorities_normalised_and_validated():
    r = make_request(preference={"priority_ranking": ["cost", "Distance", "cost"]})
    assert r.preference.priority_ranking == ["PRICE", "WALKING_TIME"]
    with pytest.raises(ValidationError):
        make_request(preference={"priority_ranking": ["VIBES"]})


def test_times_are_singapore_time():
    r = make_request(arrival_time="2026-10-19T05:00:00Z", departure_time="2026-10-19T07:00:00Z")
    assert r.arrival_time == datetime(2026, 10, 19, 13, 0, tzinfo=SGT)
    assert make_request().arrival_time.utcoffset() == timedelta(hours=8)     # naive input = SGT
