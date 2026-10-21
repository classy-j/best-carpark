"""Time helpers. Every datetime inside the app is timezone-aware Singapore time (+08:00).
Naive input (e.g. "2026-10-19T13:00" from the browser) is taken as Singapore time."""
from datetime import datetime

from app.db.records import SGT


def now_sg() -> datetime:
    return datetime.now(SGT)


def to_sg(value: datetime) -> datetime:
    return value.replace(tzinfo=SGT) if value.tzinfo is None else value.astimezone(SGT)
