from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Affiliate, Attribution, AttributionStatus
from . import attributions as attributions_service

VERIFICATION_DELAY_SECONDS = 600
_verification_tasks: Dict[int, asyncio.Task] = {}
_logger = logging.getLogger(__name__)


def schedule_verification(joined_user_id: int) -> None:
    cancel_verification(joined_user_id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:  # pragma: no cover
        _logger.warning("No running event loop to schedule verification: %s", exc)
        return

    task = loop.create_task(_verify_after_delay(joined_user_id, VERIFICATION_DELAY_SECONDS))
    _verification_tasks[joined_user_id] = task


def cancel_verification(joined_user_id: int) -> None:
    task = _verification_tasks.pop(joined_user_id, None)
    if task:
        task.cancel()


async def _verify_after_delay(joined_user_id: int, delay: int) -> None:
    try:
        await asyncio.sleep(delay)
        with session_scope() as session:
            attribution = attributions_service.get_attribution_by_user(session, joined_user_id)
            if (
                attribution
                and attribution.status == AttributionStatus.PENDING
                and not attribution.note
            ):
                attributions_service.update_attribution_status(
                    session,
                    attribution,
                    AttributionStatus.VERIFIED,
                    verified_at=datetime.now(tz=timezone.utc),
                )
    except asyncio.CancelledError:
        raise
    except Exception:  # pragma: no cover - defensive
        _logger.exception("Failed to verify attribution for user %s", joined_user_id)
    finally:
        _verification_tasks.pop(joined_user_id, None)


def run_integrity_checks(session: Session) -> Dict[str, int]:
    """Return a count of detected issues for quick health checks."""
    issues = {
        "inactive_affiliates_with_verified": 0,
        "dangling_attributions": 0,
    }

    stmt = (
        select(Attribution, Affiliate)
        .join(Affiliate, Attribution.affiliate_id == Affiliate.id, isouter=True)
    )
    for attribution, affiliate in session.execute(stmt):
        if affiliate is None:
            issues["dangling_attributions"] += 1
            continue
        if (
            not affiliate.is_active
            and attribution.status == AttributionStatus.VERIFIED
        ):
            issues["inactive_affiliates_with_verified"] += 1

    return issues


__all__ = ["cancel_verification", "run_integrity_checks", "schedule_verification", "VERIFICATION_DELAY_SECONDS"]
