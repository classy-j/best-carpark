"""Backfill historical HDB availability from data.gov.sg (the API keeps past snapshots).

    python -m app.collectors.backfill                       # last 28 days, one snapshot every 15 min
    python -m app.collectors.backfill --days 56             # 8 weeks (what the busyness lookback uses)
    python -m app.collectors.backfill --step 30 --delay 1   # fewer requests / faster

Gives the busyness estimate weeks of history immediately, instead of waiting for
the poller to collect it. Safe to stop (Ctrl+C) and re-run: time slots that are
already in the database are skipped, and duplicate observations are ignored.

Size guide: 28 days x 15 min = ~2,700 requests (~2 h at the default pace),
about 6-7 million rows (~1 GB of MySQL storage). 56 days doubles both.
"""
import argparse
import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional

from sqlalchemy import func, select

from app.db.models import AvailabilityHistory, Source
from app.db.records import SGT, to_db_time
from app.db.repository import record_availability, resolve_carpark_ids
from app.db.session import session_scope

from app.clients import hdb_data as hdb

log = logging.getLogger("app.collectors.backfill")

MIN_ROWS_FOR_COVERED_SLOT = 1000   # a full HDB snapshot is ~2,400 rows
MAX_SNAPSHOT_DRIFT = timedelta(hours=1)
# The API returns the latest snapshot at or before the requested time *within the same day*,
# so asking for exactly 00:00:00 returns nothing. Ask one minute later instead.
QUERY_OFFSET = timedelta(minutes=1)


def target_times(days: int, step_min: int, now: Optional[datetime] = None) -> list[datetime]:
    """Snapshot times from `days` ago up to now, aligned to step_min, oldest first."""
    now = (now or datetime.now(SGT)).astimezone(SGT)
    step = timedelta(minutes=step_min)
    end = now.replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % step_min)
    t = end - timedelta(days=days)
    out = []
    while t <= end:
        out.append(t)
        t += step
    return out


def covered_buckets(since: datetime, step_min: int) -> set[int]:
    """Time buckets (step_min wide) that already hold a near-complete snapshot."""
    bucket = _bucket_expr(func.unix_timestamp(AvailabilityHistory.observed_at), step_min)
    with session_scope() as s:
        rows = s.execute(
            select(bucket, func.count())
            .where(AvailabilityHistory.observed_at >= to_db_time(since))
            .group_by(bucket)
            .having(func.count() >= MIN_ROWS_FOR_COVERED_SLOT)
        ).all()
    return {int(b) for b, _ in rows}


def _bucket_expr(unix_ts, step_min: int):
    """Round to the NEAREST step: the API answers 09:30 with the 09:29 snapshot,
    so rounding down would put it in the previous slot."""
    return func.floor((unix_ts + step_min * 30) / (step_min * 60))


def _bucket_of(t: datetime, step_min: int) -> int:
    # Computed by MySQL too, so it interprets the naive SGT time exactly like observed_at.
    with session_scope() as s:
        return int(s.scalar(select(_bucket_expr(func.unix_timestamp(to_db_time(t)), step_min))))


def backfill(
    times: Iterable[datetime],
    step_min: int,
    delay_s: float = 2.0,
    fetch: Callable[[datetime], dict] = lambda at: hdb.fetch_availability(at),
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    times = list(times)
    if not times:
        return {"fetched": 0, "skipped": 0, "failed": 0, "rows": 0}
    done = covered_buckets(times[0] - timedelta(minutes=step_min), step_min)
    todo = [t for t in times if _bucket_of(t, step_min) not in done]
    stats = {"fetched": 0, "skipped": len(times) - len(todo), "failed": 0, "rows": 0}
    log.info("%d snapshots to fetch (%d already in the database)", len(todo), stats["skipped"])

    id_cache: dict[str, str] = {}
    started = time.monotonic()
    for i, t in enumerate(todo, 1):
        try:
            payload = fetch(t + QUERY_OFFSET)
            items = payload.get("items") or []
            snap = hdb._parse_time(items[0].get("timestamp")) if items else None
            if snap is None or abs(snap - t) > MAX_SNAPSHOT_DRIFT:
                raise RuntimeError(f"API returned snapshot {snap} for requested {t:%Y-%m-%d %H:%M}")
            refs = [r for r in hdb.availability_refs(payload) if r not in id_cache]
            if refs:
                id_cache.update(resolve_carpark_ids(Source.HDB, refs))
            readings, _ = hdb.parse_availability(payload, id_cache)
            stats["rows"] += record_availability(readings)
            stats["fetched"] += 1
        except Exception as e:
            stats["failed"] += 1
            log.warning("%s: %s", t.strftime("%Y-%m-%d %H:%M"), e)
            sleep(30)   # back off (usually rate limiting); this slot is retried on the next run
        if i % 50 == 0 or i == len(todo):
            rate = (time.monotonic() - started) / i
            log.info("%d/%d done, %d new rows, %d failed, ~%d min left",
                     i, len(todo), stats["rows"], stats["failed"], rate * (len(todo) - i) / 60)
        sleep(delay_s)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=28, help="how far back (default 28)")
    ap.add_argument("--step", type=int, default=15, help="minutes between snapshots (default 15)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between requests (default 2)")
    args = ap.parse_args()

    stats = backfill(target_times(args.days, args.step), args.step, args.delay)
    log.info("Finished: %(fetched)d fetched, %(skipped)d already present, %(failed)d failed, "
             "%(rows)d new rows", stats)
    if stats["failed"]:
        log.info("Re-run the same command to retry the failed time slots.")


if __name__ == "__main__":
    main()
