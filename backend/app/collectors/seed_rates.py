"""Seed HDB short-term parking rates and link every HDB carpark to its rate scheme.

    python -m app.collectors.seed_rates

Reads the HDB carpark snapshot (data/hdb_carpark_info.csv, written by the loader)
because the scheme depends on fields we don't store in `carparks`
(short_term_parking, free_parking). Safe to re-run: HDB schemes are rebuilt.

Rules (verified against HDB, Oct 2026):
  https://www.hdb.gov.sg/cs/infoweb/car-parks/short-term-parking/short-term-parking-charges
  https://www.hdb.gov.sg/car-parks/shortterm-parking/electronic-parking
  Car, outside Central Area:  $0.60 / 30 min
  Car, Central Area:          $1.20 / 30 min Mon-Sat 07:00-17:00, otherwise $0.60 / 30 min
  Car day cap (07:00-22:30):  $12 outside / $20 within Central Area
  Car night cap (22:30-07:00): $5, only at carparks with the Night Parking Scheme
  No Night Parking Scheme:    no short-term parking at night
  Motorcycle:                 $0.65 per lot, whole day (07:00-22:30) or whole night
  Heavy vehicle:              $1.20 / 30 min at all times
  Electronic (EPS):           charged per minute, 15-min grace period
  Coupon:                     charged per full 30 min

Known gaps (fee will be slightly off for these):
  - ~20 HDB carparks with peak-hour pricing are not identified (HDB publishes no list);
    they get the standard rates, while in reality caps do not apply there.
  - Public holidays: B must treat them as SUNDAY_PH using a holiday calendar.
"""
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, select, update

from app.db.models import (
    CapScope, Carpark, CarparkSourceId, ChargeMode, DayType, LotType, RateRule, RateScheme, Source,
)
from app.db.session import session_scope

from app.clients import hdb_data as hdb
from .load_carparks import SNAPSHOT

log = logging.getLogger("app.collectors.seed_rates")

CENTRAL_AREA = {"ACB", "BBB", "BRB1", "CY", "DUXM", "HLM", "KAB", "KAM", "KAS",
                "PRM", "SLS", "SR1", "SR2", "TPM", "UCS", "WCB"}

DAY_START, DAY_END, CENTRAL_PEAK_END = time(7, 0), time(22, 30), time(17, 0)
RATES_VERIFIED = date(2026, 10, 18)
D = Decimal


@dataclass(frozen=True)
class Rule:
    lot_type: LotType
    day_type: DayType
    start: time
    end: time
    mode: ChargeMode
    rate: Decimal = D("0")
    interval: Optional[int] = None
    per_minute: bool = False
    cap: Optional[Decimal] = None
    cap_scope: Optional[CapScope] = None
    grace: Optional[int] = None
    priority: int = 0


@dataclass(frozen=True)
class SchemeSpec:
    central: bool
    electronic: bool
    night: bool
    short_term: tuple[time, time] | None   # None = whole day
    free: tuple[time, time] | None         # Sunday/PH free window
    rules: tuple[Rule, ...] = field(default=(), compare=False)

    @property
    def name(self) -> str:
        def w(win):
            return "WD" if win is None else f"{win[0]:%H%M}-{win[1]:%H%M}"
        return (f"HDB_{'CEN' if self.central else 'NC'}_{'EPS' if self.electronic else 'CPN'}"
                f"_{'N' if self.night else 'D'}_ST{w(self.short_term)}"
                f"_FP{'NO' if self.free is None else w(self.free)}")


# ---------------------------------------------------------------- parsing helpers

_TIME = r"(\d{1,2})(?:\.(\d{2}))?\s*(AM|PM)"


def _t(h: str, m: Optional[str], ampm: str) -> time:
    hour = int(h) % 12 + (12 if ampm == "PM" else 0)
    return time(hour, int(m or 0))


def parse_window(text: str) -> Optional[tuple[time, time]]:
    """'7AM-10.30PM' -> (07:00, 22:30). None if not a time window."""
    m = re.search(_TIME + r"\s*-\s*" + _TIME, (text or "").upper())
    if not m:
        return None
    return _t(*m.group(1, 2, 3)), _t(*m.group(4, 5, 6))


def _clip(start: time, end: time, win: Optional[tuple[time, time]]) -> Optional[tuple[time, time]]:
    """Intersect a same-day segment with the allowed short-term window."""
    if win is None:
        return start, end
    s, e = max(start, win[0]), min(end, win[1])
    return (s, e) if s < e else None


# ---------------------------------------------------------------- rule generation (pure)

def spec_for(record: dict) -> Optional[SchemeSpec]:
    """Decide the rate scheme for one row of the HDB carpark dataset.
    None = no short-term parking (or unparseable) -> fee shown as null."""
    ref = (record.get("car_park_no") or "").strip()
    st_text = (record.get("short_term_parking") or "").strip().upper()
    if not ref or st_text in ("", "NO"):
        return None
    if st_text == "WHOLE DAY":
        short_term = None
    else:
        short_term = parse_window(st_text)
        if short_term is None:
            log.warning("Unrecognised short_term_parking %r for %s; no rates", st_text, ref)
            return None

    fp_text = (record.get("free_parking") or "").strip().upper()
    free = None if fp_text in ("", "NO") else parse_window(fp_text)
    if fp_text not in ("", "NO") and free is None:
        log.warning("Unrecognised free_parking %r for %s; ignoring free parking", fp_text, ref)

    spec = SchemeSpec(
        central=ref in CENTRAL_AREA,
        electronic="ELECTRONIC" in (record.get("type_of_parking_system") or "").upper(),
        night=(record.get("night_parking") or "").strip().upper() == "YES" and short_term is None,
        short_term=short_term,
        free=free,
    )
    return replace(spec, rules=tuple(build_rules(spec)))


def build_rules(s: SchemeSpec) -> list[Rule]:
    eps = dict(per_minute=s.electronic, grace=15 if s.electronic else None)
    day_cap = dict(cap=D("20.00") if s.central else D("12.00"), cap_scope=CapScope.DAY)
    rules: list[Rule] = []

    def car(day_type, start, end, rate):
        seg = _clip(start, end, s.short_term)
        if seg:
            rules.append(Rule(LotType.CAR, day_type, *seg, ChargeMode.PER_INTERVAL,
                              D(rate), 30, **eps, **day_cap))

    # Cars, daytime
    if s.central:
        for dt in (DayType.WEEKDAY, DayType.SATURDAY):
            car(dt, DAY_START, CENTRAL_PEAK_END, "1.20")
            car(dt, CENTRAL_PEAK_END, DAY_END, "0.60")
        car(DayType.SUNDAY_PH, DAY_START, DAY_END, "0.60")
    else:
        car(DayType.ALL, DAY_START, DAY_END, "0.60")

    # Cars, night (crosses midnight)
    if s.night:
        rules.append(Rule(LotType.CAR, DayType.ALL, DAY_END, DAY_START, ChargeMode.PER_INTERVAL,
                          D("0.60"), 30, **eps, cap=D("5.00"), cap_scope=CapScope.WINDOW))

    # Free Parking Scheme on Sundays / public holidays (overrides the paid rule)
    if s.free:
        seg = _clip(*s.free, s.short_term)
        if seg:
            rules.append(Rule(LotType.CAR, DayType.SUNDAY_PH, *seg, ChargeMode.FREE, priority=10))

    # Motorcycles: flat per lot, whole day / whole night
    seg = _clip(DAY_START, DAY_END, s.short_term)
    if seg:
        rules.append(Rule(LotType.MOTORCYCLE, DayType.ALL, *seg, ChargeMode.PER_ENTRY, D("0.65"),
                          grace=eps["grace"]))
    if s.night:
        rules.append(Rule(LotType.MOTORCYCLE, DayType.ALL, DAY_END, DAY_START, ChargeMode.PER_ENTRY,
                          D("0.65"), grace=eps["grace"]))

    # Heavy vehicles: $1.20 / 30 min at all times (no published cap)
    if seg:
        rules.append(Rule(LotType.HEAVY_VEHICLE, DayType.ALL, *seg, ChargeMode.PER_INTERVAL,
                          D("1.20"), 30, **eps))
    if s.night:
        rules.append(Rule(LotType.HEAVY_VEHICLE, DayType.ALL, DAY_END, DAY_START,
                          ChargeMode.PER_INTERVAL, D("1.20"), 30, **eps))
    return rules


# ---------------------------------------------------------------- write to DB

def seed(records: list[dict]) -> dict[str, int]:
    """Rebuild HDB schemes from dataset rows and link carparks. Returns counts."""
    specs: dict[str, SchemeSpec] = {}
    assignment: dict[str, Optional[str]] = {}       # car_park_no -> scheme name
    for r in records:
        ref = (r.get("car_park_no") or "").strip()
        if not ref:
            continue
        spec = spec_for(r)
        assignment[ref] = None if spec is None else spec.name
        if spec is not None:
            specs.setdefault(spec.name, spec)

    with session_scope() as s:
        # 1. schemes: upsert by name, then replace their rules
        existing = {sc.name: sc for sc in s.scalars(select(RateScheme).where(RateScheme.name.like("HDB\\_%")))}
        ids: dict[str, int] = {}
        for name in specs:
            sc = existing.get(name) or RateScheme(name=name, source="MANUAL")
            sc.effective_from = RATES_VERIFIED
            sc.notes = "HDB short-term rates; see collector/seed_rates.py"
            s.add(sc)
            s.flush()
            ids[name] = sc.rate_scheme_id
        if ids:
            s.execute(delete(RateRule).where(RateRule.rate_scheme_id.in_(list(ids.values()))))
        for name, spec in specs.items():
            s.add_all(RateRule(
                rate_scheme_id=ids[name], lot_type=r.lot_type, day_type=r.day_type,
                start_time=r.start, end_time=r.end, charge_mode=r.mode, rate_sgd=r.rate,
                interval_min=r.interval, per_minute=r.per_minute, cap_sgd=r.cap,
                cap_scope=r.cap_scope, grace_min=r.grace, priority=r.priority,
            ) for r in spec.rules)

        # 2. link carparks (via source IDs, so only carparks actually loaded are touched)
        id_map = dict(s.execute(
            select(CarparkSourceId.source_ref, CarparkSourceId.carpark_id)
            .where(CarparkSourceId.source == Source.HDB)).all())
        by_scheme: dict[Optional[int], list[str]] = {}
        for ref, name in assignment.items():
            cid = id_map.get(ref)
            if cid is not None:
                by_scheme.setdefault(None if name is None else ids[name], []).append(cid)
        for scheme_id, cids in by_scheme.items():
            s.execute(update(Carpark).where(Carpark.carpark_id.in_(cids)).values(rate_scheme_id=scheme_id))
        linked = sum(len(c) for k, c in by_scheme.items() if k is not None)
        no_rates = len(by_scheme.get(None, []))

    counts = {"schemes": len(specs), "rules": sum(len(sp.rules) for sp in specs.values()),
              "carparks_linked": linked, "carparks_without_rates": no_rates}
    return counts


def seed_from_snapshot() -> dict[str, int]:
    if SNAPSHOT.exists():
        records = hdb.read_records_csv(SNAPSHOT)
        log.info("Read %d rows from %s", len(records), SNAPSHOT)
    else:
        records = hdb.fetch_carpark_info_records()
        log.info("Fetched %d rows from data.gov.sg", len(records))
    counts = seed(records)
    log.info("Seeded %(schemes)d schemes / %(rules)d rules; linked %(carparks_linked)d carparks, "
             "%(carparks_without_rates)d without short-term parking", counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_from_snapshot()


if __name__ == "__main__":
    main()
