from __future__ import annotations

from datetime import datetime, timezone, time
from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_, desc, asc
from zoneinfo import ZoneInfo

from .db import session_scope
from .models import Boat, BoatStatus, BoatState, BoatStateEnum, Outing, Setting


def _csv_join(ids: Optional[List[str]]) -> Optional[str]:
    if ids is None:
        return None
    return ",".join(ids)


def _csv_parse(s: Optional[str]) -> List[str]:
    if not s:
        return []
    return [x for x in s.split(",") if x]


def create_boat(boat_id: str, display_name: str, beacons: List[str]) -> Boat:
    with session_scope() as s:
        boat = Boat(boat_id=boat_id, display_name=display_name, assigned_beacon_ids=_csv_join(beacons))
        s.add(boat)
        s.flush()
        return boat


def update_boat(boat_pk: int, display_name: Optional[str], status: Optional[BoatStatus], beacons: Optional[List[str]]) -> Optional[Boat]:
    with session_scope() as s:
        boat = s.get(Boat, boat_pk)
        if not boat:
            return None
        if display_name is not None:
            boat.display_name = display_name
        if status is not None:
            boat.status = status
        if beacons is not None:
            boat.assigned_beacon_ids = _csv_join(beacons)
        boat.updated_at = datetime.now(timezone.utc)
        s.add(boat)
        return boat


def list_boats(include_deactivated: bool = False) -> List[Boat]:
    with session_scope() as s:
        stmt = select(Boat)
        if not include_deactivated:
            stmt = stmt.where(Boat.status == BoatStatus.ACTIVE)
        return list(s.scalars(stmt).all())


def ingest_event(boat_id: str, new_state: BoatStateEnum, event_time: datetime) -> Optional[BoatState]:
    event_time = event_time.astimezone(timezone.utc)
    with session_scope() as s:
        boat = s.scalar(select(Boat).where(Boat.boat_id == boat_id))
        if not boat or boat.status == BoatStatus.DEACTIVATED:
            return None

        # Check last state to ignore duplicates
        last_state = s.scalar(
            select(BoatState).where(BoatState.boat_id == boat.id).order_by(desc(BoatState.effective_at)).limit(1)
        )
        if last_state and last_state.state == new_state:
            return last_state

        # State transition → outings tracking
        if last_state and last_state.state == BoatStateEnum.IN_SHED and new_state == BoatStateEnum.ON_WATER:
            outing = Outing(boat_id=boat.id, exit_time=event_time)
            s.add(outing)
        elif last_state and last_state.state == BoatStateEnum.ON_WATER and new_state == BoatStateEnum.IN_SHED:
            outing = s.scalar(select(Outing).where(and_(Outing.boat_id == boat.id, Outing.entry_time.is_(None))).order_by(desc(Outing.exit_time)).limit(1))
            if outing:
                outing.entry_time = event_time
                if outing.exit_time:
                    outing.total_duration = int((outing.entry_time - outing.exit_time).total_seconds())
                s.add(outing)

        bs = BoatState(boat_id=boat.id, state=new_state, effective_at=event_time)
        s.add(bs)
        return bs


def get_closing_time_default() -> str:
    return "20:00"


def get_closing_time() -> str:
    with session_scope() as s:
        st = s.scalar(select(Setting).where(Setting.key == "closing_time"))
        return (st.value if st else get_closing_time_default())


def set_closing_time(value: str) -> str:
    with session_scope() as s:
        st = s.scalar(select(Setting).where(Setting.key == "closing_time"))
        if not st:
            st = Setting(key="closing_time", value=value)
        else:
            st.value = value
        s.add(st)
        return value


def list_history(boat_pk: int, from_ts: Optional[datetime], to_ts: Optional[datetime], page: int, limit: int) -> Tuple[List[Outing], int]:
    from_ts = from_ts.astimezone(timezone.utc) if from_ts else None
    to_ts = to_ts.astimezone(timezone.utc) if to_ts else None
    with session_scope() as s:
        stmt = select(Outing).where(Outing.boat_id == boat_pk)
        if from_ts:
            stmt = stmt.where(Outing.exit_time >= from_ts)
        if to_ts:
            stmt = stmt.where(Outing.exit_time <= to_ts)
        total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(desc(Outing.exit_time)).offset((page - 1) * limit).limit(limit)
        rows = list(s.scalars(stmt).all())
        return rows, int(total)


def usage_summary(from_ts: Optional[datetime], to_ts: Optional[datetime], boat_id: Optional[str] = None) -> List[Tuple[str, int, int]]:
    from_ts = from_ts.astimezone(timezone.utc) if from_ts else None
    to_ts = to_ts.astimezone(timezone.utc) if to_ts else None
    with session_scope() as s:
        # Map boat_pk -> boat_id
        boats = {b.id: b.boat_id for b in s.scalars(select(Boat)).all()}
        stmt = select(Outing)
        if from_ts:
            stmt = stmt.where(Outing.exit_time >= from_ts)
        if to_ts:
            stmt = stmt.where(Outing.exit_time <= to_ts)
        if boat_id:
            b = s.scalar(select(Boat).where(Boat.boat_id == boat_id))
            if not b:
                return []
            stmt = stmt.where(Outing.boat_id == b.id)
        rows = list(s.scalars(stmt).all())
        agg = {}
        for r in rows:
            bid = boats.get(r.boat_id, str(r.boat_id))
            a = agg.setdefault(bid, {"count": 0, "minutes": 0})
            a["count"] += 1
            if r.total_duration:
                a["minutes"] += int(r.total_duration // 60)
        out = [(bid, a["count"], a["minutes"]) for bid, a in agg.items()]
        out.sort(key=lambda x: x[0])
        return out


def _latest_state_for_boat(session, boat_pk: int) -> Optional[BoatState]:
    return session.scalar(
        select(BoatState).where(BoatState.boat_id == boat_pk).order_by(desc(BoatState.effective_at)).limit(1)
    )


def _is_after_closing(now_utc: datetime, closing: str) -> bool:
    try:
        hh, mm = map(int, closing.split(":"))
    except Exception:
        hh, mm = 20, 0
    syd = ZoneInfo("Australia/Sydney")
    local_dt = now_utc.astimezone(syd)
    cutoff = local_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return local_dt >= cutoff


def overdue_boats() -> List[str]:
    """Return list of boat_ids currently ON_WATER after closing time."""
    now_utc = datetime.now(timezone.utc)
    closing = get_closing_time()
    if not _is_after_closing(now_utc, closing):
        return []
    with session_scope() as s:
        boats = s.scalars(select(Boat).where(Boat.status == BoatStatus.ACTIVE)).all()
        result: List[str] = []
        for b in boats:
            last = _latest_state_for_boat(s, b.id)
            if last and last.state == BoatStateEnum.ON_WATER:
                result.append(b.boat_id)
        return result


