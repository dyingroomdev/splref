from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Affiliate, Event, EventType, User


def log_event(
    session: Session,
    *,
    event_type: EventType,
    user: User,
    affiliate: Optional[Affiliate] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Event:
    record = Event(
        type=event_type,
        user=user,
        affiliate=affiliate,
        raw=raw or {},
    )
    session.add(record)
    session.flush()
    return record


def events_for_user(
    session: Session, user_id: int, limit: int = 50
) -> Sequence[Event]:
    stmt = (
        select(Event)
        .where(Event.user_id == user_id)
        .order_by(desc(Event.created_at))
        .limit(limit)
    )
    return session.execute(stmt).scalars().all()


def events_for_affiliate(
    session: Session, affiliate_id: int, limit: int = 50
) -> Sequence[Event]:
    stmt = (
        select(Event)
        .where(Event.affiliate_id == affiliate_id)
        .order_by(desc(Event.created_at))
        .limit(limit)
    )
    return session.execute(stmt).scalars().all()


__all__ = ["events_for_affiliate", "events_for_user", "log_event"]
