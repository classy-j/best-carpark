from collector import hdb
from collector.load_carparks import load
from db import repository as repo
from test_hdb_collector import INFO_RECORDS

ACB = INFO_RECORDS[0]   # Albert Centre, WHOLE DAY


def test_parse_short_term_parking():
    assert hdb.parse_carpark_info(ACB)[0].short_term_parking == "WHOLE_DAY"
    assert hdb.parse_carpark_info({**ACB, "short_term_parking": "NO"})[0].short_term_parking == "NO"
    assert hdb.parse_carpark_info({**ACB, "short_term_parking": "7AM-10.30PM"})[0].short_term_parking == "7AM_10_30PM"


def test_season_only_carparks_excluded_from_search():
    load([ACB,
          {**ACB, "car_park_no": "SEASON", "short_term_parking": "NO"},
          {**ACB, "car_park_no": "DAYONLY", "short_term_parking": "7AM-10.30PM"}])
    near = {n.carpark.carpark_id for n in repo.find_carparks_near(1.3010, 103.8541, radius_m=500)}
    assert near == {"HDB:ACB", "HDB:DAYONLY"}
    with_season = {n.carpark.carpark_id
                   for n in repo.find_carparks_near(1.3010, 103.8541, radius_m=500, include_season_only=True)}
    assert with_season == {"HDB:ACB", "HDB:DAYONLY", "HDB:SEASON"}
    assert repo.get_carpark("HDB:SEASON").short_term_parking == "NO"   # still viewable by ID
