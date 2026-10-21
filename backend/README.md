# Best Carpark App (SC2006 Group 5, SCMD)

Find the best carpark within 1 km of a destination, ranked by price, walking time,
availability and EV charging.

```
backend/                     FastAPI + MySQL
  app/
    main.py                  AppBootstrap «startup», FastAPI app
    api/routes/              REST endpoints (/api/v1/search, /api/v1/carparks/...)
    services/                «control» classes
      search_service.py        SearchService (coordinator / facade)
      fee_calculator.py        FeeCalculator        (UC-03)
      availability_service.py  AvailabilityService  (UC-04, 15-min staleness)
      busyness_estimator.py    BusynessEstimator    (UC-05)
      ev_charging_service.py   EVChargingService    (UC-06)
      ranking_engine.py        RankingEngine + RankedResultList «container» (UC-07)
      walking_service.py       walking routes via MapService, cached
    clients/                 interfaces to external actors + adapters
      interfaces.py            «interface» MapService, CarparkDataSource, EVChargingSource
      onemap.py                OneMapAdapter
      hdb.py, hdb_data.py      HdbAdapter (data.gov.sg)
      lta_datamall.py          LtaDataMallAdapter (EV: TODO)
    repositories/            «persistent store» CarparkRepository, HistoricalAvailabilityRepository
    db/                      SQLAlchemy models, queries, session
    collectors/              HistoricalAvailabilityCollector (UC-13), loader, rate seed, backfill
    schemas/                 request/response models
  sql/schema.sql             database schema (+ migrations/)
  data/hdb_carpark_info.csv  HDB carpark snapshot (fallback if data.gov.sg is down)
  tests/                     pytest (unit + database)
frontend/                    static HTML/JS (Leaflet + OneMap tiles)
```

## Run

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env                               # fill in DB + OneMap
mysql -u root -e "CREATE DATABASE smart_carpark"   # first time only
mysql -u root smart_carpark < sql/schema.sql

python -m app.collectors.load_carparks             # HDB carparks
python -m app.collectors.seed_rates                # HDB parking rates
python -m app.collectors.run_collector --backfill 28   # optional: 4 weeks of history
python -m app.collectors.run_collector             # keep running: availability every 10 min

uvicorn app.main:app --reload                      # API on http://localhost:8000 (docs: /docs)
```
Frontend: open `frontend/index.html` with a static server (e.g. VS Code Live Server on port 5500).

## Test

```bash
cd backend && python -m pytest        # database tests use a throwaway `carpark_test` DB; skipped if MySQL is down
```
