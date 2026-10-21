"""Database access functions — the public interface of Person A's module.

Other backend modules call ONLY these functions (not SQL, not ORM models).
Every function opens and closes its own session, so callers need no setup:

    from db.repository import find_carparks_near
    nearby = find_carparks_near(1.3483, 103.6831)

Who uses what:
    C (search)        get_carpark, find_carparks_near, get_latest_availability
    B (fee/ranking)   get_rate_rules
    D (availability)  get_latest_availability, get_historical_occupancy, get_last_successful_run
    A (loader/poller) upsert_carparks, resolve_carpark_ids, record_availability,
                      start_collection_run, finish_collection_run
"""
import math
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from .models import (
    AvailabilityHistory, AvailabilityLatest, Carpark, CarparkSourceId,
    CollectionRun, LotType, RateRule, RunStatus, Source,
)
from .session import session_scope
from .records import (
    SGT, AvailabilityReading, CarparkInfo, CollectionRunInfo, HistoricalAvailability, NearbyCarpark,
    OccupancyStats, RateRuleInfo, from_db_time, to_db_time,
)

EARTH_RADIUS_M = 6_371_000
METRES_PER_DEG_LAT = 111_320
SLOTS_PER_DAY = 96  # 15-minute slots


# ---------------------------------------------------------------- helpers

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _to_info(c: Carpark) -> CarparkInfo:
    return CarparkInfo(
        carpark_id=c.carpark_id, name=c.name, address=c.address,
        latitude=float(c.latitude), longitude=float(c.longitude),
        carpark_type=c.carpark_type, parking_system=c.parking_system,
        operator=c.operator,
        gantry_height_m=None if c.gantry_height_m is None else float(c.gantry_height_m),
        free_parking=c.free_parking, night_parking=c.night_parking,
        has_ev_charging=c.has_ev_charging, rate_scheme_id=c.rate_scheme_id,
        short_term_parking=c.short_term_parking,
    )


def mysql_day_of_week(dt: datetime) -> int:
    """Python datetime -> MySQL DAYOFWEEK (1=Sunday ... 7=Saturday)."""
    return dt.isoweekday() % 7 + 1


def slot_15m(dt: datetime) -> int:
    """Python datetime -> 15-minute slot of the day (0..95)."""
    return dt.hour * 4 + dt.minute // 15


# ---------------------------------------------------------------- carparks (C)

def get_carpark(carpark_id: str) -> Optional[CarparkInfo]:
    """One carpark by internal ID (e.g. 'HDB:ACB'), or None if it does not exist."""
    with session_scope() as s:
        c = s.get(Carpark, carpark_id)
        return None if c is None else _to_info(c)


def find_carparks_near(
    lat: float,
    lng: float,
    radius_m: float = 1000,
    carpark_types: Optional[Sequence[str]] = None,
    ev_required: bool = False,
    include_season_only: bool = False,
) -> list[NearbyCarpark]:
    """Carparks within radius_m (straight line) of a point, nearest first.

    carpark_types: keep only these types (e.g. ['MULTI_STOREY', 'BASEMENT']); None = all.
    ev_required:   keep only carparks KNOWN to have EV charging (unknown is excluded).
    include_season_only: by default, carparks with no short-term parking at all
                   (season parking only) are excluded, since visitors cannot park there.
    """
    dlat = radius_m / METRES_PER_DEG_LAT
    dlng = radius_m / (METRES_PER_DEG_LAT * math.cos(math.radians(lat)))
    stmt = select(Carpark).where(
        Carpark.latitude.between(lat - dlat, lat + dlat),
        Carpark.longitude.between(lng - dlng, lng + dlng),
    )
    if carpark_types:
        stmt = stmt.where(Carpark.carpark_type.in_(list(carpark_types)))
    if ev_required:
        stmt = stmt.where(Carpark.has_ev_charging.is_(True))
    if not include_season_only:
        stmt = stmt.where(or_(Carpark.short_term_parking.is_(None), Carpark.short_term_parking != "NO"))

    with session_scope() as s:
        rows = s.scalars(stmt).all()
        result = []
        for c in rows:  # bounding box is a square; trim corners with the real distance
            d = _haversine_m(lat, lng, float(c.latitude), float(c.longitude))
            if d <= radius_m:
                result.append(NearbyCarpark(carpark=_to_info(c), straight_line_m=round(d, 1)))
    return sorted(result, key=lambda n: n.straight_line_m)


# ---------------------------------------------------------------- rates (B)

def get_rate_rules(carpark_id: str, lot_type: LotType) -> list[RateRuleInfo]:
    """All rate rules that apply to this carpark and lot type, highest priority first.

    Empty list = no reliable pricing for this carpark (show estimatedFeeSgd as null).
    """
    with session_scope() as s:
        scheme_id = s.scalar(select(Carpark.rate_scheme_id).where(Carpark.carpark_id == carpark_id))
        if scheme_id is None:
            return []
        rules = s.scalars(
            select(RateRule)
            .where(RateRule.rate_scheme_id == scheme_id, RateRule.lot_type == lot_type)
            .order_by(RateRule.priority.desc(), RateRule.start_time)
        ).all()
        return [
            RateRuleInfo(
                rule_id=r.rule_id, rate_scheme_id=r.rate_scheme_id, lot_type=r.lot_type,
                day_type=r.day_type, start_time=r.start_time, end_time=r.end_time,
                charge_mode=r.charge_mode, rate_sgd=r.rate_sgd, interval_min=r.interval_min,
                per_minute=r.per_minute, first_interval_min=r.first_interval_min,
                first_rate_sgd=r.first_rate_sgd, cap_sgd=r.cap_sgd, cap_scope=r.cap_scope,
                grace_min=r.grace_min, priority=r.priority,
            )
            for r in rules
        ]


# ---------------------------------------------------------------- availability (C, D)

def get_latest_availability(
    carpark_ids: Iterable[str], lot_type: LotType
) -> dict[str, AvailabilityReading]:
    """Most recent reading per carpark. Carparks with no reading are simply absent
    from the dict (-> availability: null in the API). Staleness is D's call:
    compare observed_at with the current time."""
    ids = list(carpark_ids)
    if not ids:
        return {}
    with session_scope() as s:
        rows = s.scalars(
            select(AvailabilityLatest).where(
                AvailabilityLatest.carpark_id.in_(ids),
                AvailabilityLatest.lot_type == lot_type,
            )
        ).all()
        return {
            r.carpark_id: AvailabilityReading(
                carpark_id=r.carpark_id, lot_type=r.lot_type,
                available_lots=r.available_lots, total_lots=r.total_lots,
                observed_at=from_db_time(r.observed_at),
                collected_at=from_db_time(r.collected_at),
            )
            for r in rows
        }


def _history_filter(carpark_id: str, lot_type: LotType, at: datetime,
                    window_slots: int, lookback_days: int) -> list:
    """Same weekday and time of day as `at` (+/- window_slots x 15 min), last N days."""
    at_sgt = at.astimezone(SGT) if at.tzinfo else at
    centre = slot_15m(at_sgt)
    slots = sorted({(centre + k) % SLOTS_PER_DAY for k in range(-window_slots, window_slots + 1)})
    since = to_db_time(datetime.now(SGT) - timedelta(days=lookback_days))
    h = AvailabilityHistory
    return [h.carpark_id == carpark_id, h.lot_type == lot_type,
            h.day_of_week == mysql_day_of_week(at_sgt), h.slot_15m.in_(slots),
            h.observed_at >= since]


def get_historical_records(
    carpark_id: str,
    lot_type: LotType,
    at: datetime,
    window_slots: int = 1,
    lookback_days: int = 56,
) -> list[HistoricalAvailability]:
    """Raw past observations for the same weekday and time of day as `at`, oldest first.
    Input for D's BusynessEstimator. Slots wrap within the same weekday near midnight."""
    h = AvailabilityHistory
    with session_scope() as s:
        rows = s.scalars(select(h).where(*_history_filter(carpark_id, lot_type, at, window_slots, lookback_days))
                         .order_by(h.observed_at)).all()
        return [HistoricalAvailability(r.carpark_id, r.lot_type, r.available_lots, r.total_lots,
                                       from_db_time(r.observed_at)) for r in rows]


def get_historical_occupancy(
    carpark_id: str,
    lot_type: LotType,
    at: datetime,
    window_slots: int = 1,
    lookback_days: int = 56,
) -> Optional[OccupancyStats]:
    """Convenience: average occupancy % over the same records as get_historical_records
    (rows without total_lots are skipped). None if nothing usable."""
    h = AvailabilityHistory
    occupancy = func.greatest(0, func.least(100, 100 * (h.total_lots - h.available_lots) / h.total_lots))
    with session_scope() as s:
        mean, count = s.execute(
            select(func.avg(occupancy), func.count()).where(
                *_history_filter(carpark_id, lot_type, at, window_slots, lookback_days),
                h.total_lots > 0)
        ).one()
    if not count:
        return None
    return OccupancyStats(mean_occupancy_pct=round(float(mean), 1), sample_count=count)


# ---------------------------------------------------------------- loader (A)

def upsert_carparks(source: Source, items: Sequence[tuple[CarparkInfo, str]]) -> int:
    """Insert or update carparks from one source.

    items: (CarparkInfo, source_ref) pairs, where source_ref is the ID used by
    that source (HDB car_park_no, URA ppCode, LTA CarParkID).
    Returns the number of carparks processed.
    """
    if not items:
        return 0
    now = to_db_time(datetime.now(SGT))
    carpark_rows = [
        {
            "carpark_id": c.carpark_id, "name": c.name, "address": c.address,
            "latitude": c.latitude, "longitude": c.longitude,
            "carpark_type": c.carpark_type, "parking_system": c.parking_system,
            "operator": c.operator, "gantry_height_m": c.gantry_height_m,
            "free_parking": c.free_parking, "night_parking": c.night_parking,
            "short_term_parking": c.short_term_parking,
            "has_ev_charging": c.has_ev_charging, "rate_scheme_id": c.rate_scheme_id,
            "updated_at": now,
        }
        for c, _ in items
    ]
    ins = mysql_insert(Carpark).values(carpark_rows)
    # Don't overwrite has_ev_charging (D fills it) or rate_scheme_id (seeded separately)
    # with NULLs from a source that doesn't know them.
    keep_if_null = {"has_ev_charging", "rate_scheme_id"}
    update_cols = {
        col: (func.coalesce(ins.inserted[col], getattr(Carpark, col)) if col in keep_if_null
              else ins.inserted[col])
        for col in carpark_rows[0] if col != "carpark_id"
    }
    source_rows = [
        {"source": source, "source_ref": ref, "carpark_id": c.carpark_id} for c, ref in items
    ]
    with session_scope() as s:
        s.execute(ins.on_duplicate_key_update(**update_cols))
        sins = mysql_insert(CarparkSourceId).values(source_rows)
        s.execute(sins.on_duplicate_key_update(carpark_id=sins.inserted.carpark_id))
    return len(items)


def resolve_carpark_ids(source: Source, source_refs: Iterable[str]) -> dict[str, str]:
    """Map source IDs to internal carpark IDs, e.g. {'ACB': 'HDB:ACB'}.
    Refs we don't know (carpark not loaded yet) are absent from the result."""
    refs = list(source_refs)
    if not refs:
        return {}
    with session_scope() as s:
        rows = s.execute(
            select(CarparkSourceId.source_ref, CarparkSourceId.carpark_id).where(
                CarparkSourceId.source == source, CarparkSourceId.source_ref.in_(refs)
            )
        ).all()
    return {ref: cid for ref, cid in rows}


# ---------------------------------------------------------------- poller (A)

def record_availability(readings: Sequence[AvailabilityReading]) -> int:
    """Store one poll's readings.

    - availability_history: new readings appended; a reading with the same
      (carpark, lot type, observed_at) as an existing row is skipped.
    - availability_latest: updated only if the reading is newer than what's stored.
    Returns the number of NEW history rows.
    """
    if not readings:
        return 0
    rows = [
        {
            "carpark_id": r.carpark_id, "lot_type": r.lot_type,
            "available_lots": r.available_lots, "total_lots": r.total_lots,
            "observed_at": to_db_time(r.observed_at), "collected_at": to_db_time(r.collected_at),
        }
        for r in readings
    ]
    with session_scope() as s:
        hist = mysql_insert(AvailabilityHistory).values(rows).prefix_with("IGNORE")
        inserted = s.execute(hist).rowcount

        latest = mysql_insert(AvailabilityLatest).values(rows)
        newer = latest.inserted.observed_at >= AvailabilityLatest.observed_at
        # MySQL applies these left to right, so observed_at must be updated LAST,
        # otherwise the comparisons after it would see the new value.
        latest = latest.on_duplicate_key_update([
            (col, func.if_(newer, latest.inserted[col], getattr(AvailabilityLatest, col)))
            for col in ("available_lots", "total_lots", "collected_at", "observed_at")
        ])
        s.execute(latest)
    return inserted


def start_collection_run(source: str) -> int:
    """Log the start of a poll ('HDB', 'URA' or 'LTA'). Returns run_id."""
    with session_scope() as s:
        run = CollectionRun(
            source=source, started_at=to_db_time(datetime.now(SGT)),
            status=RunStatus.PARTIAL, rows_inserted=0,
        )
        s.add(run)
        s.flush()
        return run.run_id


def finish_collection_run(
    run_id: int, status: RunStatus, rows_inserted: int, error_message: Optional[str] = None
) -> None:
    """Log the end of a poll."""
    with session_scope() as s:
        s.execute(
            update(CollectionRun).where(CollectionRun.run_id == run_id).values(
                finished_at=to_db_time(datetime.now(SGT)), status=status,
                rows_inserted=rows_inserted,
                error_message=None if error_message is None else error_message[:500],
            )
        )


def get_last_successful_run(source: str) -> Optional[CollectionRunInfo]:
    """Most recent OK poll for a source. If it's old, the source is probably down."""
    with session_scope() as s:
        r = s.scalars(
            select(CollectionRun)
            .where(CollectionRun.source == source, CollectionRun.status == RunStatus.OK)
            .order_by(CollectionRun.finished_at.desc(), CollectionRun.run_id.desc())  # DATETIME is per-second
            .limit(1)
        ).first()
        if r is None:
            return None
        return CollectionRunInfo(
            run_id=r.run_id, source=r.source, started_at=from_db_time(r.started_at),
            finished_at=from_db_time(r.finished_at), status=r.status,
            rows_inserted=r.rows_inserted, error_message=r.error_message,
        )


def get_lot_types(carpark_ids: Iterable[str]) -> dict[str, set[LotType]]:
    """Lot types each carpark is known to have (from its availability readings).
    Carparks with no readings at all are absent -> their lot types are unknown."""
    ids = list(carpark_ids)
    if not ids:
        return {}
    out: dict[str, set[LotType]] = {}
    with session_scope() as s:
        for cid, lot in s.execute(
            select(AvailabilityLatest.carpark_id, AvailabilityLatest.lot_type)
            .where(AvailabilityLatest.carpark_id.in_(ids))
        ):
            out.setdefault(cid, set()).add(lot)
    return out
