from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import (
    Column, Integer, String, Enum as SAEnum, DateTime, JSON, ForeignKey, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum

from .db import Base


class BoatStatus(str, Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class BoatStateEnum(str, Enum):
    IN_SHED = "IN_SHED"
    ON_WATER = "ON_WATER"


class Boat(Base):
    __tablename__ = "boats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boat_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[BoatStatus] = mapped_column(SAEnum(BoatStatus), default=BoatStatus.ACTIVE, nullable=False)
    assigned_beacon_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # comma-separated for SQLite
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    states: Mapped[List["BoatState"]] = relationship("BoatState", back_populates="boat")
    outings: Mapped[List["Outing"]] = relationship("Outing", back_populates="boat")


class BoatState(Base):
    __tablename__ = "boat_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boat_id: Mapped[int] = mapped_column(ForeignKey("boats.id"), nullable=False)
    state: Mapped[BoatStateEnum] = mapped_column(SAEnum(BoatStateEnum), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    boat: Mapped[Boat] = relationship("Boat", back_populates="states")


class Outing(Base):
    __tablename__ = "outings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boat_id: Mapped[int] = mapped_column(ForeignKey("boats.id"), nullable=False)
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    entry_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    total_duration: Mapped[Optional[int]] = mapped_column(Integer)  # seconds
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    boat: Mapped[Boat] = relationship("Boat", back_populates="outings")


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)




