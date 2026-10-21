"""APScheduler wiring for the collector. Jobs never kill the scheduler."""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.db.records import SGT


def build_scheduler(collector: HistoricalAvailabilityCollector, refresh_hour: int = 3) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=SGT)
    sched.add_job(collector.poll_once, "interval", minutes=collector.interval_min,
                  next_run_time=datetime.now(SGT), id="poll_hdb",
                  max_instances=1, coalesce=True, misfire_grace_time=60)
    sched.add_job(collector.refresh_carparks, "cron", hour=refresh_hour, minute=17,
                  id="refresh_carparks", max_instances=1, coalesce=True)
    return sched
