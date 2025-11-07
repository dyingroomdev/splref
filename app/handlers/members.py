from __future__ import annotations

import ipaddress
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Optional

from aiogram import Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatInviteLink, ChatMemberUpdated

from ..config import get_settings
from ..db import session_scope
from ..models import AttributionStatus, EventType
from ..services import (
    affiliates as affiliates_service,
    attributions as attributions_service,
    events as events_service,
    integrity as integrity_service,
    users as users_service,
)
from ..utils import extract_link_code
from ..utils.logging import request_ip_var

router = Router(name="members")

BURST_WINDOW = timedelta(minutes=5)
BURST_THRESHOLD = 3  # flag when count exceeds this value
_subnet_events: Dict[str, Deque[datetime]] = defaultdict(deque)


@router.chat_member()
async def handle_chat_member(update: ChatMemberUpdated) -> None:
    settings = get_settings()
    if update.chat.id != settings.target_chat_id:
        return

    new_status = update.new_chat_member.status
    old_status = update.old_chat_member.status

    if new_status == ChatMemberStatus.MEMBER and old_status != ChatMemberStatus.MEMBER:
        await _handle_join(update)
    elif (
        old_status == ChatMemberStatus.MEMBER
        and new_status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    ):
        await _handle_leave(update)


def _ip_subnet(ip_str: Optional[str]) -> Optional[str]:
    if not ip_str:
        return None
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address):
        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
        return f"{network.network_address}/24"
    return None


def _record_subnet_event(subnet: str, now: datetime) -> bool:
    bucket = _subnet_events[subnet]
    while bucket and (now - bucket[0]) > BURST_WINDOW:
        bucket.popleft()
    bucket.append(now)
    return len(bucket) > BURST_THRESHOLD


def _is_fresh_account(user) -> bool:
    if getattr(user, "is_bot", False):
        return True
    username = user.username or ""
    first_name = user.first_name or ""
    is_premium = bool(getattr(user, "is_premium", False))
    if is_premium:
        return False
    if username:
        return False
    if len(first_name.strip()) <= 2:
        return True
    return False


async def _handle_join(update: ChatMemberUpdated) -> None:
    invite_link: ChatInviteLink | None = update.invite_link
    if invite_link is None or not invite_link.invite_link:
        return

    link_url = invite_link.invite_link
    link_code = extract_link_code(link_url)
    target_user = update.new_chat_member.user

    source_ip = request_ip_var.get()
    subnet = _ip_subnet(source_ip)
    now = datetime.now(tz=timezone.utc)

    suspicion_reasons: List[str] = []
    if subnet and _record_subnet_event(subnet, now):
        suspicion_reasons.append("ip_burst")
    if _is_fresh_account(target_user):
        suspicion_reasons.append("fresh_account")

    created = False
    flagged_users: List[int] = []

    with session_scope() as session:
        joined_user = users_service.upsert_user(
            session,
            user_id=target_user.id,
            username=target_user.username,
            first_name=target_user.first_name,
            last_name=target_user.last_name,
        )

        affiliate = affiliates_service.get_affiliate_by_code(session, link_code)
        if (
            affiliate is None
            or affiliate.owner_user_id == joined_user.id
            or not affiliate.is_active
        ):
            return

        existing = attributions_service.get_attribution_by_user(session, joined_user.id)
        if existing:
            return

        note = ",".join(suspicion_reasons) if suspicion_reasons else None
        attribution = attributions_service.create_attribution(
            session,
            affiliate=affiliate,
            joined_user=joined_user,
            joined_at=now,
            source_ip=source_ip,
            source_subnet=subnet,
            note=note,
        )

        if "ip_burst" in suspicion_reasons and subnet:
            flagged = attributions_service.flag_subnet_burst(
                session,
                subnet=subnet,
                since=now - BURST_WINDOW,
            )
            flagged_users = [item.joined_user_id for item in flagged]

        events_service.log_event(
            session,
            event_type=EventType.JOIN,
            user=joined_user,
            affiliate=affiliate,
            raw={
                "invite_link": link_url,
                "link_code": link_code,
                "attribution_id": attribution.id,
                "flags": suspicion_reasons,
                "source_ip": source_ip,
                "source_subnet": subnet,
            },
        )
        created = True

    if created:
        if suspicion_reasons:
            integrity_service.cancel_verification(target_user.id)
        else:
            integrity_service.schedule_verification(target_user.id)
        for user_id in flagged_users:
            if user_id != target_user.id:
                integrity_service.cancel_verification(user_id)


async def _handle_leave(update: ChatMemberUpdated) -> None:
    target_user = update.old_chat_member.user
    user_id = target_user.id
    status = update.new_chat_member.status.value

    revoked = False

    with session_scope() as session:
        user = users_service.upsert_user(
            session,
            user_id=user_id,
            username=target_user.username,
            first_name=target_user.first_name,
            last_name=target_user.last_name,
        )
        attribution = attributions_service.get_attribution_by_user(session, user_id)
        if attribution and attribution.status in (
            AttributionStatus.PENDING,
            AttributionStatus.VERIFIED,
        ):
            attributions_service.update_attribution_status(
                session,
                attribution,
                AttributionStatus.REVOKED,
                verified_at=attribution.verified_at,
            )
            events_service.log_event(
                session,
                event_type=EventType.LEAVE,
                user=user,
                affiliate=attribution.affiliate,
                raw={
                    "reason": status,
                    "attribution_id": attribution.id,
                },
            )
            revoked = True

    if revoked:
        integrity_service.cancel_verification(user_id)

