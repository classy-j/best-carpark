"""HistoricalAvailabilityCollector «control»: collects carpark availability in the background
(UC-13, FR5.1). Runs independently of any search; started by AppBootstrap or run_collector.

  poll_once()        live HDB availability -> history + latest (every 10 min)
  backfill(days)     past snapshots from data.gov.sg, so estimates work from day one
  refresh_carparks() daily reload of carpark info and rate-scheme links
"""
import logging
from datetime import datetime

from app.clients.hdb import HdbAdapter
from app.collectors import backfill as _backfill
from app.collectors.load_carparks import load_hdb_carparks
from app.collectors.seed_rates import seed_from_snapshot
from app.db.models import RunStatus, Source
from app.db.repository import finish_collection_run, resolve_carpark_ids, start_collection_run
from app.repositories.historical_availability_repository import HistoricalAvailabilityRepository

log = logging.getLogger(__name__)


class HistoricalAvailabilityCollector:
    def __init__(self, source: HdbAdapter, repo: HistoricalAvailabilityRepository, interval_min: int = 10):
        self._source = source
        self._repo = repo
        self.interval_min = interval_min

    def poll_once(self, at: datetime | None = None) -> int:
        """Fetch and store one snapshot. Returns new history rows. Never raises:
        failures are logged and recorded in collection_runs (UC-13 EX1)."""
        run_id = start_collection_run("HDB")
        try:
            readings = self._source.fetch_availability(lambda refs: resolve_carpark_ids(Source.HDB, refs), at)
            if not readings:
                raise RuntimeError("no usable readings (empty response, or carparks not loaded?)")
            inserted = self._repo.save_availability_records(readings)
            finish_collection_run(run_id, RunStatus.OK, inserted)
            log.info("HDB poll: %d readings, %d new rows", len(readings), inserted)
            return inserted
        except Exception as e:
            finish_collection_run(run_id, RunStatus.FAILED, 0, f"{type(e).__name__}: {e}")
            log.error("HDB poll failed: %s", e)
            return 0

    def backfill(self, days: int = 28, step_min: int = 15, delay_s: float = 2.0) -> dict[str, int]:
        """Load past snapshots (safe to re-run: slots already stored are skipped)."""
        return _backfill.backfill(_backfill.target_times(days, step_min), step_min, delay_s)

    @staticmethod
    def refresh_carparks() -> None:
        """Reload carpark info, then re-link rate schemes (new carparks get prices too)."""
        try:
            load_hdb_carparks()
            seed_from_snapshot()
        except Exception as e:
            log.error("Carpark info refresh failed (keeping existing data): %s", e)
