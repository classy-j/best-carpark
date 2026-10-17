"""Historical Data Collector: polls HDB live availability and stores it (FR5.1 / UC-13).

    python -m collector.poller                 # run forever: poll every 10 min, refresh carpark info daily
    python -m collector.poller --interval 15   # poll every 15 min
    python -m collector.poller --once          # one poll, then exit (for testing or an external cron)

Keep it running for as long as possible: every hour it is stopped is history
that the expected-busyness estimate will never have.
"""
import argparse
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import func, select

from db.models import Carpark, RunStatus, Source
from db.repository import (
    finish_collection_run, record_availability, resolve_carpark_ids, start_collection_run,
)
from db.session import session_scope
from db.records import SGT

from . import hdb
from .load_carparks import load_hdb_carparks
from .seed_rates import seed_from_snapshot

log = logging.getLogger("collector.poller")


def poll_hdb_once() -> int:
    """Fetch live HDB availability and store it. Returns new history rows.
    Never raises: failures are logged and recorded in collection_runs."""
    run_id = start_collection_run("HDB")
    try:
        payload = hdb.fetch_availability()
        known = resolve_carpark_ids(Source.HDB, hdb.availability_refs(payload))
        readings, unknown = hdb.parse_availability(payload, known)
        if not readings:
            raise RuntimeError("no usable readings (empty response, or carparks not loaded?)")
        inserted = record_availability(readings)
        finish_collection_run(run_id, RunStatus.OK, inserted)
        log.info("HDB poll: %d readings, %d new rows, %d unknown carpark numbers",
                 len(readings), inserted, len(unknown))
        return inserted
    except Exception as e:
        finish_collection_run(run_id, RunStatus.FAILED, 0, f"{type(e).__name__}: {e}")
        log.error("HDB poll failed: %s", e)
        return 0


def refresh_carparks() -> None:
    """Reload carpark info, then re-link rate schemes (new carparks get prices too)."""
    try:
        load_hdb_carparks()
        seed_from_snapshot()
    except Exception as e:
        log.error("Carpark info refresh failed (keeping existing data): %s", e)


def _hdb_carpark_count() -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(Carpark).where(Carpark.operator == "HDB"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=int, default=10, help="minutes between polls (default 10)")
    ap.add_argument("--once", action="store_true", help="poll once and exit")
    args = ap.parse_args()

    if _hdb_carpark_count() == 0:
        log.info("No HDB carparks in the database yet; loading them first")
        load_hdb_carparks()
        seed_from_snapshot()

    if args.once:
        poll_hdb_once()
        return

    sched = BlockingScheduler(timezone="Asia/Singapore")
    sched.add_job(poll_hdb_once, "interval", minutes=args.interval, next_run_time=datetime.now(SGT),
                  id="poll_hdb", max_instances=1, coalesce=True, misfire_grace_time=60)
    sched.add_job(refresh_carparks, "cron", hour=3, minute=17, id="refresh_carparks",
                  max_instances=1, coalesce=True)
    log.info("Poller started: every %d min. Press Ctrl+C to stop.", args.interval)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Poller stopped")


if __name__ == "__main__":
    main()
