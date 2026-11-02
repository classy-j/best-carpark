"""Regressions for the 2026 PH calendar, EV filtering/ranking, and fallback routes."""
from datetime import date
from app.db.models import DayType
from app.services.fee_calculator import day_type_of
from app.utils.public_holidays import sg_public_holidays
from app.schemas.search import SearchPreference


def test_observed_deepavali_monday_is_holiday():
    assert date(2026, 11, 9) in sg_public_holidays()
    assert day_type_of(date(2026, 11, 9), sg_public_holidays()) == DayType.SUNDAY_PH


def test_ordinary_monday_is_weekday():
    assert day_type_of(date(2026, 11, 2), sg_public_holidays()) == DayType.WEEKDAY


def test_ev_is_not_a_ranking_factor():
    assert SearchPreference().priority_ranking == ['PRICE', 'WALKING_TIME', 'AVAILABILITY']
    from pydantic import ValidationError
    try:
        SearchPreference(priority_ranking=['EV_CHARGING'])
    except ValidationError:
        pass
    else:
        raise AssertionError('EV must be a filter, not a ranking priority')
