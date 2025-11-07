from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import User


def get_user(session: Session, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    return session.execute(stmt).scalar_one_or_none()


def get_user_by_username(session: Session, username: str) -> Optional[User]:
    normalized = username.lstrip("@")
    if not normalized:
        return None
    stmt = select(User).where(func.lower(User.username) == normalized.lower())
    return session.execute(stmt).scalar_one_or_none()


def upsert_user(
    session: Session,
    *,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> User:
    existing = get_user(session, user_id)
    if existing:
        existing.username = username
        existing.first_name = first_name
        existing.last_name = last_name
        session.add(existing)
        session.flush()
        return existing

    user = User(
        id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    session.add(user)
    session.flush()
    return user


__all__ = ["get_user", "get_user_by_username", "upsert_user"]
