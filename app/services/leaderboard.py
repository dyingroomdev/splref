from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import session_scope
from ..models import Affiliate, Attribution, AttributionStatus

LEADERBOARD_WINDOWS: Dict[str, Optional[timedelta]] = {
    "all": None,
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

_cache: Dict[str, Dict[int, int]] = {}
_cache_generated_at: Dict[str, datetime] = {}
_rollup_task: Optional[asyncio.Task] = None
_logger = logging.getLogger(__name__)


def _window_cutoff(window_key: str) -> Optional[datetime]:
    delta = LEADERBOARD_WINDOWS.get(window_key, None)
    if delta is None:
        return None
    return datetime.now(tz=timezone.utc) - delta


def _sorted_affiliates_from_counts(
    session: Session,
    counts: Dict[int, int],
    limit: int,
) -> List[Tuple[Affiliate, int]]:
    if not counts:
        return []
    affiliate_ids = sorted(counts.keys(), key=lambda x: counts[x], reverse=True)[:limit]
    if not affiliate_ids:
        return []
    stmt = (
        select(Affiliate)
        .where(Affiliate.id.in_(affiliate_ids))
        .options(selectinload(Affiliate.owner))
    )
    affiliates = {affiliate.id: affiliate for affiliate in session.execute(stmt).scalars()}
    return [
        (affiliates[affiliate_id], counts[affiliate_id])
        for affiliate_id in affiliate_ids
        if affiliate_id in affiliates
    ]


def _live_query_top_affiliates(
    session: Session,
    window_key: str,
    limit: int,
) -> List[Tuple[Affiliate, int]]:
    cutoff = _window_cutoff(window_key)
    stmt = (
        select(Affiliate, func.count(Attribution.id).label("total"))
        .join(Attribution, Attribution.affiliate_id == Affiliate.id)
        .where(Attribution.status == AttributionStatus.VERIFIED)
    )
    if cutoff is not None:
        stmt = stmt.where(Attribution.joined_at >= cutoff)
    stmt = (
        stmt.group_by(Affiliate.id)
        .options(selectinload(Affiliate.owner))
        .order_by(func.count(Attribution.id).desc())
        .limit(limit)
    )
    return [
        (affiliate, total)
        for affiliate, total in session.execute(stmt).all()
    ]


def top_affiliates(
    session: Session,
    limit: int = 10,
    *,
    window: str = "all",
    use_cache: bool = True,
) -> Sequence[Tuple[Affiliate, int]]:
    window_key = window if window in LEADERBOARD_WINDOWS else "all"
    if use_cache and window_key in _cache:
        counts = _cache[window_key]
        return _sorted_affiliates_from_counts(session, counts, limit)
    return _live_query_top_affiliates(session, window_key, limit)


def recompute_cache() -> None:
    with session_scope() as session:
        for window_key in LEADERBOARD_WINDOWS:
            cutoff = _window_cutoff(window_key)
            stmt = (
                select(Attribution.affiliate_id, func.count(Attribution.id))
                .where(Attribution.status == AttributionStatus.VERIFIED)
            )
            if cutoff is not None:
                stmt = stmt.where(Attribution.joined_at >= cutoff)
            stmt = stmt.group_by(Attribution.affiliate_id)
            results = session.execute(stmt).all()
            counts: Dict[int, int] = defaultdict(int)
            for affiliate_id, total in results:
                counts[int(affiliate_id)] = total
            _cache[window_key] = dict(counts)
            _cache_generated_at[window_key] = datetime.now(tz=timezone.utc)
    _logger.info("Leaderboard cache recomputed")


async def _rollup_worker(interval: int) -> None:
    while True:
        try:
            recompute_cache()
        except Exception:  # pragma: no cover - defensive
            _logger.exception("Failed to recompute leaderboard cache")
        await asyncio.sleep(interval)


def start_leaderboard_rollup(interval_seconds: int = 7 * 24 * 3600) -> None:
    global _rollup_task
    if _rollup_task and not _rollup_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:  # pragma: no cover
        _logger.warning("Cannot start leaderboard rollup without running loop: %s", exc)
        return
    _rollup_task = loop.create_task(_rollup_worker(interval_seconds))


def cache_generated_at(window: str = "all") -> Optional[datetime]:
    return _cache_generated_at.get(window)


__all__ = [
    "LEADERBOARD_WINDOWS",
    "cache_generated_at",
    "recompute_cache",
    "start_leaderboard_rollup",
    "top_affiliates",
]
