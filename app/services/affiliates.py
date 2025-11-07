from __future__ import annotations

from typing import Dict, Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Affiliate, Attribution, AttributionStatus, User


def get_affiliate(session: Session, affiliate_id: int) -> Optional[Affiliate]:
    stmt = select(Affiliate).where(Affiliate.id == affiliate_id)
    return session.execute(stmt).scalar_one_or_none()


def get_affiliate_by_code(session: Session, link_code: str) -> Optional[Affiliate]:
    stmt = select(Affiliate).where(Affiliate.link_code == link_code)
    return session.execute(stmt).scalar_one_or_none()


def list_affiliates(session: Session, active_only: bool = False) -> Sequence[Affiliate]:
    stmt = select(Affiliate)
    if active_only:
        stmt = stmt.where(Affiliate.is_active.is_(True))
    stmt = stmt.order_by(Affiliate.created_at.desc())
    return session.execute(stmt).scalars().all()


def create_affiliate(
    session: Session,
    owner: User,
    invite_link: str,
    link_code: str,
    *,
    is_active: bool = True,
) -> Affiliate:
    affiliate = Affiliate(
        owner=owner,
        invite_link=invite_link,
        link_code=link_code,
        is_active=is_active,
    )
    session.add(affiliate)
    session.flush()
    return affiliate


def set_affiliate_active(
    session: Session, affiliate: Affiliate, is_active: bool
) -> Affiliate:
    affiliate.is_active = is_active
    session.add(affiliate)
    session.flush()
    return affiliate


def get_affiliate_by_owner(session: Session, owner_user_id: int) -> Optional[Affiliate]:
    stmt = select(Affiliate).where(Affiliate.owner_user_id == owner_user_id)
    return session.execute(stmt).scalar_one_or_none()


def get_affiliate_stats(session: Session, affiliate_id: int) -> Dict[AttributionStatus, int]:
    stmt = (
        select(Attribution.status, func.count())
        .where(Attribution.affiliate_id == affiliate_id)
        .group_by(Attribution.status)
    )
    counts = {status: 0 for status in AttributionStatus}
    for status, total in session.execute(stmt):
        counts[status] = total
    return counts


def bulk_set_active(session: Session, is_active: bool) -> int:
    result = session.execute(
        update(Affiliate).values(is_active=is_active)
    )
    session.flush()
    return result.rowcount if result else 0


def count_affiliates(session: Session) -> Dict[str, int]:
    total = session.execute(select(func.count()).select_from(Affiliate)).scalar_one()
    active = session.execute(
        select(func.count()).select_from(Affiliate).where(Affiliate.is_active.is_(True))
    ).scalar_one()
    inactive = max(total - active, 0)
    return {"active": int(active or 0), "inactive": int(inactive or 0), "total": int(total or 0)}


__all__ = [
    "bulk_set_active",
    "count_affiliates",
    "create_affiliate",
    "get_affiliate",
    "get_affiliate_by_code",
    "get_affiliate_by_owner",
    "get_affiliate_stats",
    "list_affiliates",
    "set_affiliate_active",
]
