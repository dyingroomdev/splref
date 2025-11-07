from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from ..models import Affiliate, Attribution, AttributionStatus, User


def create_attribution(
    session: Session,
    *,
    affiliate: Affiliate,
    joined_user: User,
    joined_at: Optional[datetime] = None,
    source_ip: Optional[str] = None,
    source_subnet: Optional[str] = None,
    note: Optional[str] = None,
) -> Attribution:
    record = Attribution(
        affiliate=affiliate,
        joined_user=joined_user,
        joined_at=joined_at or datetime.now(tz=timezone.utc),
        note=note,
        last_seen_ip=source_ip,
        source_subnet=source_subnet,
    )
    session.add(record)
    session.flush()
    return record


def get_attribution_by_user(session: Session, user_id: int) -> Optional[Attribution]:
    stmt = select(Attribution).where(Attribution.joined_user_id == user_id)
    return session.execute(stmt).scalar_one_or_none()


def list_attributions_by_affiliate(
    session: Session, affiliate_id: int
) -> Sequence[Attribution]:
    stmt = (
        select(Attribution)
        .where(Attribution.affiliate_id == affiliate_id)
        .order_by(Attribution.joined_at.desc())
    )
    return session.execute(stmt).scalars().all()


def update_attribution_status(
    session: Session,
    attribution: Attribution,
    status: AttributionStatus,
    *,
    verified_at: Optional[datetime] = None,
) -> Attribution:
    attribution.status = status
    if status == AttributionStatus.VERIFIED:
        attribution.verified_at = verified_at or datetime.now(tz=timezone.utc)
    else:
        attribution.verified_at = verified_at
    session.add(attribution)
    session.flush()
    return attribution


def delete_attribution(session: Session, attribution: Attribution) -> None:
    session.delete(attribution)
    session.flush()


def merge_note(existing: Optional[str], reason: str) -> str:
    reasons = {r.strip() for r in (existing or "").split(",") if r.strip()}
    reasons.add(reason)
    return ",".join(sorted(reasons))


def set_attribution_note(
    session: Session,
    attribution: Attribution,
    reason: str,
    *,
    append: bool = True,
) -> Attribution:
    attribution.note = (
        merge_note(attribution.note, reason) if append else reason
    )
    session.add(attribution)
    session.flush()
    return attribution


def count_by_status_since(
    session: Session,
    since: datetime,
) -> Dict[AttributionStatus, int]:
    stmt = (
        select(Attribution.status, func.count())
        .where(Attribution.joined_at >= since)
        .group_by(Attribution.status)
    )
    counts = {status: 0 for status in AttributionStatus}
    for status, total in session.execute(stmt):
        counts[status] = total
    return counts


def flag_subnet_burst(
    session: Session,
    subnet: str,
    since: datetime,
) -> Sequence[Attribution]:
    stmt = (
        select(Attribution)
        .where(
            and_(
                Attribution.source_subnet == subnet,
                Attribution.joined_at >= since,
            )
        )
        .options(
            selectinload(Attribution.joined_user),
            selectinload(Attribution.affiliate),
        )
    )
    updated: list[Attribution] = []
    for attribution in session.execute(stmt).scalars():
        attribution.status = AttributionStatus.PENDING
        attribution.verified_at = None
        attribution.note = merge_note(attribution.note, "ip_burst")
        session.add(attribution)
        updated.append(attribution)
    session.flush()
    return updated


def list_pending_reviews(
    session: Session,
    limit: int = 10,
) -> Sequence[Attribution]:
    stmt = (
        select(Attribution)
        .where(
            and_(
                Attribution.status == AttributionStatus.PENDING,
                Attribution.note.is_not(None),
            )
        )
        .order_by(Attribution.joined_at.asc())
        .limit(limit)
        .options(
            selectinload(Attribution.joined_user),
            selectinload(Attribution.affiliate).selectinload(Affiliate.owner),
        )
    )
    return session.execute(stmt).scalars().all()


__all__ = [
    "create_attribution",
    "delete_attribution",
    "flag_subnet_burst",
    "get_attribution_by_user",
    "list_attributions_by_affiliate",
    "list_pending_reviews",
    "count_by_status_since",
    "merge_note",
    "set_attribution_note",
    "update_attribution_status",
]
