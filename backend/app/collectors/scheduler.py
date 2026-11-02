"""APScheduler wiring for the collector. Jobs never kill the scheduler."""
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.collectors.historical_availability_collector import HistoricalAvailabilityCollector
from app.db.records import SGT


def build_scheduler(collector: HistoricalAvailabilityCollector, refresh_hour: int = 3,
                    ev_interval_min: int = 60) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=SGT)
    sched.add_job(collector.poll_once, "interval", minutes=collector.interval_min,
                  next_run_time=datetime.now(SGT), id="poll_hdb",
                  max_instances=1, coalesce=True, misfire_grace_time=60)
    sched.add_job(collector.refresh_carparks, "cron", hour=refresh_hour, minute=17,
                  id="refresh_carparks", max_instances=1, coalesce=True)
    if collector.ura is not None:
        sched.add_job(collector.poll_ura, "interval", minutes=collector.interval_min,
                      next_run_time=datetime.now(SGT), id="poll_ura",
                      max_instances=1, coalesce=True, misfire_grace_time=60)
    if collector.ev_service is not None:
        sched.add_job(collector.refresh_ev, "interval", minutes=ev_interval_min,
                      next_run_time=datetime.now(SGT), id="refresh_ev",
                      max_instances=1, coalesce=True, misfire_grace_time=300)
    return sched
