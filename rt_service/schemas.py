from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class BoatStatus(str, Enum):
    active = "active"
    deactivated = "deactivated"


class BoatStateEnum(str, Enum):
    IN_SHED = "IN_SHED"
    ON_WATER = "ON_WATER"


class BoatCreate(BaseModel):
    boat_id: str
    display_name: str
    assigned_beacon_ids: List[str] = Field(default_factory=list)


class BoatUpdate(BaseModel):
    display_name: Optional[str]
    status: Optional[BoatStatus]
    assigned_beacon_ids: Optional[List[str]]


class BoatOut(BaseModel):
    id: int
    boat_id: str
    display_name: str
    status: BoatStatus
    assigned_beacon_ids: List[str] = []
    class Config:
        from_attributes = True


class EventIngest(BaseModel):
    beacon_id: str
    boat_id: str
    new_state: BoatStateEnum
    event_time: datetime


class HistoryRow(BaseModel):
    exit_time: Optional[datetime]
    entry_time: Optional[datetime]
    duration_seconds: Optional[int]


class UsageSummary(BaseModel):
    boat_id: Optional[str]
    total_outings: int
    total_minutes: int




