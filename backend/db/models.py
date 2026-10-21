"""SQLAlchemy ORM models. Mirrors db/schema.sql (schema.sql is the source of truth).

Only Person A's code should import these directly. Other modules use the
functions in db/repository.py, which return plain dataclasses.
"""
import enum
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, DateTime, Enum,
    ForeignKey, Index, Integer, Numeric, SmallInteger, String, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------- Enums (values must match the ENUMs in schema.sql) ----------

class LotType(str, enum.Enum):
    CAR = "CAR"
    MOTORCYCLE = "MOTORCYCLE"
    HEAVY_VEHICLE = "HEAVY_VEHICLE"


class Source(str, enum.Enum):
    HDB = "HDB"
    URA = "URA"
    LTA = "LTA"
    MANUAL = "MANUAL"


class DayType(str, enum.Enum):
    WEEKDAY = "WEEKDAY"
    SATURDAY = "SATURDAY"
    SUNDAY_PH = "SUNDAY_PH"
    ALL = "ALL"


class ChargeMode(str, enum.Enum):
    PER_INTERVAL = "PER_INTERVAL"
    PER_ENTRY = "PER_ENTRY"
    FREE = "FREE"


class CapScope(str, enum.Enum):
    WINDOW = "WINDOW"
    ENTRY = "ENTRY"
    DAY = "DAY"


class RunStatus(str, enum.Enum):
    OK = "OK"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


def _enum(e):
    return Enum(e, values_callable=lambda x: [m.value for m in x], native_enum=True)


# ---------- 1. Carparks ----------

class Carpark(Base):
    __tablename__ = "carparks"

    carpark_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[Optional[str]] = mapped_column(String(255))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    carpark_type: Mapped[Optional[str]] = mapped_column(String(32))
    parking_system: Mapped[Optional[str]] = mapped_column(String(32))
    operator: Mapped[Optional[str]] = mapped_column(String(64))
    gantry_height_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    free_parking: Mapped[Optional[str]] = mapped_column(String(32))
    night_parking: Mapped[Optional[bool]] = mapped_column(Boolean)
    short_term_parking: Mapped[Optional[str]] = mapped_column(String(32))
    has_ev_charging: Mapped[Optional[bool]] = mapped_column(Boolean)
    rate_scheme_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rate_schemes.rate_scheme_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (Index("idx_location", "latitude", "longitude"),)


class CarparkSourceId(Base):
    __tablename__ = "carpark_source_ids"

    source: Mapped[Source] = mapped_column(_enum(Source), primary_key=True)
    source_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    carpark_id: Mapped[str] = mapped_column(ForeignKey("carparks.carpark_id"))


# ---------- 2. Parking rates ----------

class RateScheme(Base):
    __tablename__ = "rate_schemes"

    rate_scheme_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(Enum("API", "MANUAL"))
    effective_from: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(String(255))


class RateRule(Base):
    __tablename__ = "rate_rules"

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rate_scheme_id: Mapped[int] = mapped_column(ForeignKey("rate_schemes.rate_scheme_id"))
    lot_type: Mapped[LotType] = mapped_column(_enum(LotType))
    day_type: Mapped[DayType] = mapped_column(_enum(DayType))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    charge_mode: Mapped[ChargeMode] = mapped_column(_enum(ChargeMode))
    rate_sgd: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    interval_min: Mapped[Optional[int]] = mapped_column(Integer)
    per_minute: Mapped[bool] = mapped_column(Boolean, default=False)
    first_interval_min: Mapped[Optional[int]] = mapped_column(Integer)
    first_rate_sgd: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    cap_sgd: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    cap_scope: Mapped[Optional[CapScope]] = mapped_column(_enum(CapScope))
    grace_min: Mapped[Optional[int]] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("idx_lookup", "rate_scheme_id", "lot_type", "day_type"),
        CheckConstraint("charge_mode <> 'PER_INTERVAL' OR interval_min IS NOT NULL"),
        CheckConstraint("(cap_sgd IS NULL) = (cap_scope IS NULL)"),
    )


# ---------- 3. Availability ----------

class AvailabilityHistory(Base):
    __tablename__ = "availability_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    carpark_id: Mapped[str] = mapped_column(ForeignKey("carparks.carpark_id"))
    lot_type: Mapped[LotType] = mapped_column(_enum(LotType))
    available_lots: Mapped[int] = mapped_column(Integer)
    total_lots: Mapped[Optional[int]] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    day_of_week: Mapped[int] = mapped_column(
        SmallInteger, Computed("DAYOFWEEK(observed_at)", persisted=True))
    slot_15m: Mapped[int] = mapped_column(
        SmallInteger,
        Computed("HOUR(observed_at) * 4 + MINUTE(observed_at) DIV 15", persisted=True))

    __table_args__ = (
        UniqueConstraint("carpark_id", "lot_type", "observed_at", name="uq_obs"),
        Index("idx_busyness", "carpark_id", "lot_type", "day_of_week", "slot_15m"),
    )


class AvailabilityLatest(Base):
    __tablename__ = "availability_latest"

    carpark_id: Mapped[str] = mapped_column(ForeignKey("carparks.carpark_id"), primary_key=True)
    lot_type: Mapped[LotType] = mapped_column(_enum(LotType), primary_key=True)
    available_lots: Mapped[int] = mapped_column(Integer)
    total_lots: Mapped[Optional[int]] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime)


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Enum("HDB", "URA", "LTA"))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus))
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(String(500))
