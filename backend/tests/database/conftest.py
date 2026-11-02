"""Tests run against a separate database `carpark_test`, rebuilt from backend/db/schema.sql.
Your real database is never touched. Skipped automatically if MySQL is not running.
Connection: root with no password on 127.0.0.1:3306 (the conda setup in docs/DATABASE.md)."""
import os
import re
from pathlib import Path

import pymysql
import pytest

HOST, PORT, USER, PASSWORD = "127.0.0.1", 3306, "root", ""
TEST_DB = "carpark_test"
# DATABASE_URL is set in tests/conftest.py

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"
TABLES = ["availability_history", "availability_latest", "carpark_source_ids",
          "collection_runs", "rate_rules", "carparks", "rate_schemes"]


def _statements():
    sql = re.sub(r"--[^\n]*", "", SCHEMA.read_text())
    return [s.strip() for s in sql.split(";") if s.strip()]


@pytest.fixture(scope="session", autouse=True)
def test_database():
    try:
        conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PASSWORD,
                               autocommit=True, connect_timeout=3)
    except pymysql.err.OperationalError as e:
        pytest.skip(f"MySQL not reachable at {HOST}:{PORT} ({e.args[0]}); database tests skipped")
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        cur.execute(f"CREATE DATABASE {TEST_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
        cur.execute(f"USE {TEST_DB}")
        for stmt in _statements():
            cur.execute(stmt)
    yield
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    conn.close()


@pytest.fixture(autouse=True)
def clean_tables(test_database):
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PASSWORD,
                           database=TEST_DB, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in TABLES:
            cur.execute(f"TRUNCATE TABLE {t}")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.close()
    yield
