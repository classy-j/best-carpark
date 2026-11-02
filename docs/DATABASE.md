# Database layer & Historical Data Collector (Person A)

Implements `CarparkRepository`, `HistoricalAvailabilityRepository` and
`HistoricalAvailabilityCollector` from [BACKEND_INTERFACES.md](BACKEND_INTERFACES.md).

```
backend/
  db/
    schema.sql          # tables (source of truth for new databases)
    migrations/         # updates for existing databases, run once each, in order
    repositories.py     # <- CarparkRepository, HistoricalAvailabilityRepository (use these)
    records.py          # dataclasses returned to callers
    repository.py       # lower-level functions behind the classes
    models.py           # SQLAlchemy models (Person A only)
    session.py          # connection; reads DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD from .env
  collector/
    poller.py           # HistoricalAvailabilityCollector: polls HDB availability every 10 min
    backfill.py         # fills past weeks of history from the API's snapshots
    load_carparks.py    # loads ~2,300 HDB carparks from data.gov.sg
    seed_rates.py       # HDB parking rates -> rate_schemes / rate_rules
    hdb.py, svy21.py    # data.gov.sg client + parsing, SVY21 -> WGS84
  data/hdb_carpark_info.csv   # snapshot of the HDB dataset; fallback if the API is down
tests/database/         # needs MySQL; uses a separate carpark_test database
```

## Setup (once)

1. MySQL 8.x running locally. One way (conda):
   ```bash
   conda create -n carpark -c conda-forge mysql-server=8.4.2 mysql-client=8.4.2 python=3.12 -y
   conda activate carpark
   mysqld --initialize-insecure --datadir=$HOME/mysql-data
   # start (keep this terminal open):
   mysqld --datadir=$HOME/mysql-data --port=3306 --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci
   ```
2. Create the database and tables (from the repo root):
   ```bash
   mysql -u root -h 127.0.0.1 -e "CREATE DATABASE smart_carpark CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
   mysql -u root -h 127.0.0.1 smart_carpark < backend/db/schema.sql
   ```
3. `pip install -r requirements.txt`, then `cp .env.example .env` and set `DB_USER`, `DB_PASSWORD` (empty for the conda setup above) and `DB_NAME`.
4. `python -m pytest -q` from the repo root (tests use a separate `carpark_test` database, created and dropped automatically).

## Running (from `backend/`)

```bash
cd backend
python -m collector.load_carparks   # carparks (the poller also does this if the table is empty)
python -m collector.seed_rates      # parking rates (re-run daily by the poller)
python -m collector.poller          # keep running; Ctrl+C to stop
```

History doesn't have to be collected live: the availability API keeps past snapshots,
so `backfill` fills them in (resumable; re-run to retry failures or top up gaps):

```bash
python -m collector.backfill              # last 28 days, every 15 min: ~2,700 requests, ~2 h, ~1 GB
python -m collector.backfill --days 56    # 8 weeks (the busyness lookback)
```

The poller keeps `availability_latest` fresh for live availability, so it should be running
whenever the app is used (e.g. the demo). Gaps in history can be filled later with `backfill`.
On a Mac, `caffeinate -i python -m collector.poller` stops idle sleep.

## Interfaces

Code runs from `backend/`, so imports are `from db.repositories import ...`.
Method names are the snake_case form of the names in BACKEND_INTERFACES.md.
All datetimes returned are timezone-aware Singapore time (+08:00); money is `Decimal`.
`lot_type` accepts `LotType.CAR` or the string `"CAR"` (`CAR`, `MOTORCYCLE`, `HEAVY_VEHICLE`).

```python
from db.repositories import CarparkRepository, HistoricalAvailabilityRepository

carparks = CarparkRepository()
nearby = carparks.get_nearby_carparks(destination_location, radius_m=1000)  # list[CarparkInfo], nearest first
cp = carparks.get_carpark_by_id("HDB:ACB")                                # CarparkInfo or None
rules = carparks.get_rate_rules("HDB:ACB", "CAR")                         # list[RateRuleInfo]; [] -> fee null

history = HistoricalAvailabilityRepository()
records = history.get_historical_records("HDB:ACB", "CAR", arrival_time)  # list[HistoricalAvailability]
latest = history.get_latest_availability(["HDB:ACB"], "CAR")             # dict[id, AvailabilityReading]
```

| Method | Used by | Notes |
|---|---|---|
| `CarparkRepository.get_nearby_carparks(destination_location, radius_m=1000, *, carpark_types=None, ev_required=False, include_season_only=False)` | C | `destination_location`: object with `.latitude/.longitude`, a dict, or `(lat, lng)`. Straight-line radius. Season-parking-only carparks (~149 HDB) are excluded by default. `ev_required=True` excludes unknown EV status. |
| `CarparkRepository.get_carpark_by_id(carpark_id)` | C | `None` -> `CARPARK_NOT_FOUND` |
| `CarparkRepository.get_rate_rules(carpark_id, lot_type)` | B | *Not in BACKEND_INTERFACES.md.* See "Rate rules" below. |
| `HistoricalAvailabilityRepository.get_historical_records(carpark_id, lot_type, arrival_time, *, window_minutes=15, lookback_days=56)` | D | Same weekday, arrival time of day +/- 15 min, last 8 weeks, oldest first. `total_lots` may be `None`. |
| `HistoricalAvailabilityRepository.get_latest_availability(carpark_ids, lot_type)` | D | *Not in the doc.* Latest stored reading (<= 10 min old while the collector runs). `timestamp`/`observed_at` lets D set `isStale`. |
| `HistoricalAvailabilityRepository.save_availability_record(carpark_id, lot_type, available_lots, total_lots, timestamp)` | collector | Duplicate observations are ignored. |

### `CarparkInfo` fields
`carpark_id` (`HDB:<car_park_no>`), `name`, `address`, `latitude`, `longitude`, `carpark_type`
(`MULTI_STOREY`, `SURFACE`, `BASEMENT`, ...), `parking_system` (`ELECTRONIC`/`COUPON`), `operator`,
`gantry_height_m`, `free_parking`, `night_parking`, `has_ev_charging` (`None` = unknown; D fills it),
`rate_scheme_id`, `short_term_parking` (`WHOLE_DAY`, `NO`, or hours such as `7AM_10_30PM`).

### Rate rules (B)
HDB rates as of Oct 2026 (sources in `collector/seed_rates.py`).
- Pick rules whose `day_type` matches: `WEEKDAY` Mon–Fri, `SATURDAY`, `SUNDAY_PH` (Sunday **and public holidays** — needs a holiday calendar), `ALL`. Where windows overlap, higher `priority` wins (e.g. `FREE` Sunday rule over the paid one).
- `end_time <= start_time`: window crosses midnight (night 22:30–07:00).
- `PER_INTERVAL`: `rate_sgd` per `interval_min`; `per_minute=True` (electronic) is pro-rated by the minute, `False` (coupon) charges every started interval.
- `PER_ENTRY`: flat `rate_sgd` once per window the stay touches (motorcycles). `FREE`: no charge.
- `grace_min`: stays up to this long are free (15 min at electronic carparks).
- `cap_scope=DAY`: all DAY-capped charges in one 07:00–22:30 period together capped at `cap_sgd` ($12; $20 Central Area). `WINDOW`: per occurrence of that rule's window (night $5).
- **If part of the stay is not covered by any rule, the carpark cannot be used for that stay** (limited short-term hours, or no night parking) — exclude it.
- Not modelled: ~20 HDB carparks with peak-hour pricing (no official list).

## Notes for the team
- `FeeCalculator.calculateFee(carpark, arrivalTime, departureTime)` also needs the **lot type**: rates differ for cars, motorcycles and heavy vehicles.
- Live availability for search can come from `get_latest_availability` (the collector refreshes it every 10 min) instead of calling data.gov.sg on every search.
- HDB carparks are always loaded. URA carparks, rates and availability are loaded when URA_API_KEY is set (`python -m app.collectors.ura`, and by the collector). LTA is used for EV charging only.
