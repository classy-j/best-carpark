"""Load URA carparks + rates, and poll URA availability (Person A).

    python -m app.collectors.ura            # load carparks + rates, then one availability poll
    python -m app.collectors.ura --poll     # availability poll only

Needs URA_API_KEY (the AccessKey URA emails you) in backend/.env. Safe to re-run: carparks are upserted and each URA
carpark's rate scheme (URA_<ppCode>) is rebuilt from the latest Car_Park_Details.

Rates go into the same rate_schemes / rate_rules tables as HDB, so FeeCalculator needs no
change. URA publishes no caps or grace periods in this API; charging is per started
interval (per_minute = False), which can overestimate slightly at electronic carparks.
"""
import argparse
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.clients import ura_data as ura
from app.db.models import Carpark, CarparkSourceId, ChargeMode, LotType, RateRule, RateScheme, RunStatus, Source
from app.db.repository import (finish_collection_run, record_availability, resolve_carpark_ids,
                               start_collection_run, upsert_carparks)
from app.db.session import session_scope

log = logging.getLogger("app.collectors.ura")

BATCH = 500
RATES_SOURCE_NOTE = "URA Car_Park_Details; see collectors/ura.py"


def scheme_name(pp_code: str) -> str:
    return f"URA_{pp_code}"[:64]


def seed_ura_rates(rates: dict[str, list[ura.UraRate]]) -> dict[str, int]:
    """Rebuild URA_<ppCode> schemes and link carparks. Carparks without rates get no scheme
    (fee shown as Unavailable)."""
    with_rates = {code: rs for code, rs in rates.items() if rs}
    today = datetime.now(ura.SGT).date()
    with session_scope() as s:
        ids: dict[str, int] = {}
        if with_rates:
            ins = mysql_insert(RateScheme).values([
                {"name": scheme_name(c), "source": "API", "effective_from": today, "notes": RATES_SOURCE_NOTE}
                for c in with_rates])
            s.execute(ins.on_duplicate_key_update(effective_from=ins.inserted.effective_from,
                                                  notes=ins.inserted.notes))
            by_name = dict(s.execute(select(RateScheme.name, RateScheme.rate_scheme_id)
                                     .where(RateScheme.name.in_([scheme_name(c) for c in with_rates]))).all())
            ids = {c: by_name[scheme_name(c)] for c in with_rates}
            s.execute(delete(RateRule).where(RateRule.rate_scheme_id.in_(list(ids.values()))))
            rule_rows = [{
                "rate_scheme_id": ids[code], "lot_type": r.lot_type, "day_type": r.day_type,
                "start_time": r.start, "end_time": r.end,
                "charge_mode": ChargeMode.FREE if r.rate == 0 else ChargeMode.PER_INTERVAL,
                "rate_sgd": r.rate, "interval_min": None if r.rate == 0 else r.interval_min,
                "per_minute": False, "priority": 0,
            } for code, rs in with_rates.items() for r in rs]
            for i in range(0, len(rule_rows), BATCH):
                s.execute(mysql_insert(RateRule).values(rule_rows[i:i + BATCH]))

        # link carparks (only those loaded, via their URA source id)
        id_map = dict(s.execute(select(CarparkSourceId.source_ref, CarparkSourceId.carpark_id)
                                .where(CarparkSourceId.source == Source.URA)).all())
        by_scheme: dict[Optional[int], list[str]] = {}
        for code, cid in id_map.items():
            by_scheme.setdefault(ids.get(code), []).append(cid)
        for scheme_id, cids in by_scheme.items():
            for i in range(0, len(cids), 1000):
                s.execute(update(Carpark).where(Carpark.carpark_id.in_(cids[i:i + 1000]))
                          .values(rate_scheme_id=scheme_id))
    return {"schemes": len(ids), "rules": sum(len(r) for r in with_rates.values()),
            "carparks_linked": sum(len(c) for k, c in by_scheme.items() if k is not None),
            "carparks_without_rates": len(by_scheme.get(None, []))}


class UraSync:
    """Keeps the parkCapacity map from the last Details load, for availability totals."""

    def __init__(self, client: ura.UraClient):
        self.client = client
        self.capacity: dict[tuple[str, LotType], int] = {}

    def load(self) -> dict[str, int]:
        """Carpark list + rates -> carparks, rate_schemes, rate_rules. Raises on API failure."""
        carparks, rates, self.capacity = ura.parse_details(self.client.fetch_details())
        for i in range(0, len(carparks), BATCH):
            upsert_carparks(Source.URA, carparks[i:i + BATCH])
        counts = {"carparks": len(carparks), **seed_ura_rates(rates)}
        log.info("URA: %(carparks)d carparks, %(schemes)d schemes / %(rules)d rules, "
                 "%(carparks_without_rates)d without rates", counts)
        return counts

    def poll_once(self) -> int:
        """Store one availability snapshot. Never raises (failures go to collection_runs)."""
        run_id = start_collection_run("URA")
        try:
            if not self.capacity:                       # fresh process: get totals (and carparks) first
                self.load()
            rows = self.client.fetch_availability()
            known = resolve_carpark_ids(Source.URA, {str(r.get("carparkNo") or "").strip() for r in rows})
            readings, unknown = ura.parse_availability(rows, known, self.capacity)
            if not readings:
                raise RuntimeError("no usable URA readings (empty response, or carparks not loaded?)")
            inserted = record_availability(readings)
            finish_collection_run(run_id, RunStatus.OK, inserted)
            log.info("URA poll: %d readings, %d new rows, %d unknown carparks", len(readings), inserted, len(unknown))
            return inserted
        except Exception as e:
            finish_collection_run(run_id, RunStatus.FAILED, 0, f"{type(e).__name__}: {e}")
            log.error("URA poll failed: %s", e)
            return 0


def main() -> None:
    from app.dependencies import get_settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poll", action="store_true", help="availability poll only")
    args = ap.parse_args()
    sync = UraSync(ura.UraClient(get_settings().ura_api_key))
    if not args.poll:
        sync.load()
    sync.poll_once()


if __name__ == "__main__":
    main()
