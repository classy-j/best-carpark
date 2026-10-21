"""Database connection and session handling.

Connection settings come from the repo's .env file (see .env.example):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
DATABASE_URL, if set, overrides them all (the tests use this).
"""
import os
from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()  # real environment variables still take precedence


def database_url() -> "str | URL":
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    return URL.create(
        "mysql+pymysql",
        username=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        database=os.environ.get("DB_NAME", "smart_carpark"),
        query={"charset": "utf8mb4"},
    )


engine = create_engine(
    database_url(),
    pool_pre_ping=True,   # reconnect cleanly if MySQL restarted
    pool_recycle=3600,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Open a session, commit on success, roll back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
