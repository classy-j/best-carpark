"""Load HDB carpark information into the `carparks` table.

    python -m app.collectors.load_carparks              # from data.gov.sg (saves a CSV snapshot)
    python -m app.collectors.load_carparks --csv FILE   # from a CSV (snapshot or data.gov.sg download)

If the API is unreachable and a snapshot exists, the snapshot is used instead.
Safe to run repeatedly: existing carparks are updated, not duplicated.
"""
import argparse
import logging
from pathlib import Path

from app.db.models import Source
from app.db.repository import upsert_carparks

from app.clients import hdb_data as hdb

log = logging.getLogger("app.collectors.load_carparks")

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "hdb_carpark_info.csv"   # backend/data/
BATCH = 500


def load(records: list[dict]) -> tuple[int, int]:
    """Parse and upsert records. Returns (loaded, skipped)."""
    parsed = [p for p in (hdb.parse_carpark_info(r) for r in records) if p is not None]
    for i in range(0, len(parsed), BATCH):
        upsert_carparks(Source.HDB, parsed[i:i + BATCH])
    return len(parsed), len(records) - len(parsed)


def load_hdb_carparks(csv_path: Path | None = None) -> int:
    if csv_path:
        records = hdb.read_records_csv(csv_path)
        log.info("Read %d rows from %s", len(records), csv_path)
    else:
        try:
            records = hdb.fetch_carpark_info_records()
            log.info("Fetched %d rows from data.gov.sg", len(records))
            SNAPSHOT.parent.mkdir(exist_ok=True)
            hdb.save_records_csv(records, SNAPSHOT)
            log.info("Saved snapshot to %s", SNAPSHOT)
        except Exception as e:
            if not SNAPSHOT.exists():
                raise
            log.warning("data.gov.sg failed (%s); using snapshot %s", e, SNAPSHOT)
            records = hdb.read_records_csv(SNAPSHOT)

    loaded, skipped = load(records)
    log.info("Loaded %d carparks (%d rows skipped: missing ID or coordinates)", loaded, skipped)
    return loaded


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, help="load from this CSV instead of the API")
    args = ap.parse_args()
    load_hdb_carparks(args.csv)


if __name__ == "__main__":
    main()
