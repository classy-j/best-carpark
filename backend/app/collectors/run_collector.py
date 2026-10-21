"""Run the collector as its own process (recommended: keep it running 24/7).

    python -m app.collectors.run_collector                # poll every 10 min, refresh carparks daily
    python -m app.collectors.run_collector --interval 15
    python -m app.collectors.run_collector --once         # one poll, then exit
    python -m app.collectors.run_collector --backfill 28  # load the last 28 days, then exit

If the API server also runs the collector (COLLECTOR_ENABLED=true), don't run this as well.
"""
import argparse
import logging
import time

from sqlalchemy import func, select

from app.db.models import Carpark
from app.db.session import session_scope
from app.dependencies import build_collector
from app.collectors.scheduler import build_scheduler

log = logging.getLogger("app.collectors.run_collector")


def _hdb_carpark_count() -> int:
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(Carpark).where(Carpark.operator == "HDB"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=int, help="minutes between polls (default from settings: 10)")
    ap.add_argument("--once", action="store_true", help="poll once and exit")
    ap.add_argument("--backfill", type=int, metavar="DAYS", help="load past DAYS of history and exit")
    args = ap.parse_args()

    collector = build_collector()
    if args.interval:
        collector.interval_min = args.interval
    if _hdb_carpark_count() == 0:
        log.info("No HDB carparks in the database yet; loading them first")
        collector.refresh_carparks()

    if args.backfill:
        log.info("Backfill finished: %s", collector.backfill(args.backfill))
        return
    if args.once:
        collector.poll_once()
        return

    sched = build_scheduler(collector)
    sched.start()
    log.info("Collector started: every %d min. Press Ctrl+C to stop.", collector.interval_min)
    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown(wait=False)


if __name__ == "__main__":
    main()
