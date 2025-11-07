import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import get_settings
from ..db import session_scope
from ..models import Attribution, AttributionStatus
from ..services import (
    affiliates as affiliates_service,
    attributions as attributions_service,
    integrity as integrity_service,
    leaderboard as leaderboard_service,
    users as users_service,
)
from ..utils import extract_link_code

router = Router(name="commands")
logger = logging.getLogger(__name__)


RATE_LIMITED_COMMANDS = {"ping", "mylink", "deactivate", "reactivate", "mystats", "top"}


class RateLimiter:
    def __init__(self, per_minutes: int = 1, max_calls: int = 5):
        self.per_seconds = per_minutes * 60
        self.max_calls = max_calls
        self._bucket: Dict[int, List[float]] = {}

    def hit(self, user_id: int, now: Optional[float] = None) -> bool:
        import time

        current = now or time.time()
        window_start = current - self.per_seconds
        bucket = self._bucket.setdefault(user_id, [])
        bucket = [timestamp for timestamp in bucket if timestamp > window_start]
        allowed = len(bucket) < self.max_calls
        if allowed:
            bucket.append(current)
        self._bucket[user_id] = bucket
        return allowed


rate_limiter = RateLimiter()


async def _ensure_admin(message: Message) -> bool:
    caller = message.from_user
    if caller is None:
        await message.answer("Cannot resolve your Telegram identity.")
        return False

    if not await _is_admin(message.bot, caller.id):
        await message.answer("Only chat administrators can use this command.")
        return False
    return True


async def _is_admin(bot, user_id: int) -> bool:
    settings = get_settings()
    try:
        member = await bot.get_chat_member(settings.target_chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def _rate_limit(message: Message, command: str) -> bool:
    if command not in RATE_LIMITED_COMMANDS:
        return True
    user = message.from_user
    if user is None:
        return False
    if rate_limiter.hit(user.id):
        return True
    return False


@router.message(Command("ping"))
async def handle_ping(message: Message) -> None:
    if not _rate_limit(message, "ping"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    await message.answer("pong")


@router.message()
async def log_unhandled_message(message: Message) -> None:
    logger.info(
        "Message received with no command handler",
        extra={
            "text": message.text,
            "chat_id": message.chat.id if message.chat else None,
            "chat_type": getattr(message.chat, "type", None),
            "from_user": message.from_user.id if message.from_user else None,
            "entities": [entity.type for entity in (message.entities or [])],
        },
    )




@router.message(Command("mylink"), F.chat.type == ChatType.PRIVATE)
async def handle_my_link(message: Message) -> None:
    if not _rate_limit(message, "mylink"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    settings = get_settings()
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Cannot resolve your Telegram identity.")
        return

    user_payload = {
        "user_id": tg_user.id,
        "username": tg_user.username,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
    }

    invite_link: str | None = None
    link_code: str | None = None
    was_created = False
    reactivated = False
    need_create = False

    with session_scope() as session:
        user = users_service.upsert_user(session, **user_payload)
        affiliate = affiliates_service.get_affiliate_by_owner(session, user.id)
        if affiliate:
            invite_link = affiliate.invite_link
            link_code = affiliate.link_code
            if not affiliate.is_active:
                affiliates_service.set_affiliate_active(session, affiliate, True)
                reactivated = True
        else:
            need_create = True

    if need_create:
        try:
            chat_invite = await message.bot.create_chat_invite_link(
                settings.target_chat_id,
                name=f"AFF_{tg_user.id}",
                creates_join_request=False,
            )
        except TelegramAPIError:
            await message.answer(
                "I could not create your invite link. "
                "Ensure the bot has permission to manage invite links.",
            )
            return

        invite_link = chat_invite.invite_link
        link_code = extract_link_code(invite_link)

        with session_scope() as session:
            user = users_service.upsert_user(session, **user_payload)
            affiliates_service.create_affiliate(
                session,
                owner=user,
                invite_link=invite_link,
                link_code=link_code,
                is_active=True,
            )
            was_created = True

    if not invite_link:
        await message.answer("Failed to resolve your affiliate link. Please try again.")
        return

    instructions = (
        "Share this link to attribute new members to you.\n"
        "Use /deactivate to pause attribution or /reactivate to resume."
    )
    code_line = f"\nCode: `{link_code}`" if link_code else ""

    if was_created:
        text = (
            "Your affiliate link is ready!\n"
            f"{invite_link}{code_line}\n\n"
            f"{instructions}"
        )
    elif reactivated:
        text = (
            "Your affiliate link has been reactivated.\n"
            f"{invite_link}{code_line}\n\n"
            f"{instructions}"
        )
    else:
        text = (
            "Your affiliate link is active.\n"
            f"{invite_link}{code_line}\n\n"
            f"{instructions}"
        )

    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("deactivate"), F.chat.type == ChatType.PRIVATE)
async def handle_deactivate(message: Message) -> None:
    if not _rate_limit(message, "deactivate"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Cannot resolve your Telegram identity.")
        return

    response = "You do not have an affiliate link yet. Send /mylink to create one."

    with session_scope() as session:
        user = users_service.get_user(session, tg_user.id)
        if user:
            affiliate = affiliates_service.get_affiliate_by_owner(session, user.id)
            if affiliate:
                if not affiliate.is_active:
                    response = "Your affiliate link is already deactivated."
                else:
                    affiliates_service.set_affiliate_active(session, affiliate, False)
                    response = (
                        "Your affiliate link has been deactivated. "
                        "Use /reactivate when you are ready to share it again."
                    )

    await message.answer(response, disable_web_page_preview=True)


@router.message(Command("reactivate"), F.chat.type == ChatType.PRIVATE)
async def handle_reactivate(message: Message) -> None:
    if not _rate_limit(message, "reactivate"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Cannot resolve your Telegram identity.")
        return

    response = "You do not have an affiliate link yet. Send /mylink to create one."

    with session_scope() as session:
        user = users_service.get_user(session, tg_user.id)
        if user:
            affiliate = affiliates_service.get_affiliate_by_owner(session, user.id)
            if affiliate:
                if affiliate.is_active:
                    response = (
                        "Your affiliate link is already active.\n"
                        f"{affiliate.invite_link}"
                    )
                else:
                    affiliates_service.set_affiliate_active(session, affiliate, True)
                    response = (
                        "Your affiliate link is active again!\n"
                        f"{affiliate.invite_link}"
                    )

    await message.answer(response, disable_web_page_preview=True)


@router.message(Command("mystats"), F.chat.type == ChatType.PRIVATE)
async def handle_my_stats(message: Message) -> None:
    if not _rate_limit(message, "mystats"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Cannot resolve your Telegram identity.")
        return

    stats = None
    invite_link = None

    with session_scope() as session:
        user = users_service.get_user(session, tg_user.id)
        if not user:
            response = "No affiliate link found. Use /mylink to create one."
        else:
            affiliate = affiliates_service.get_affiliate_by_owner(session, user.id)
            if not affiliate:
                response = "No affiliate link found. Use /mylink to create one."
            else:
                stats = affiliates_service.get_affiliate_stats(session, affiliate.id)
                invite_link = affiliate.invite_link
                response = None

    if stats is None:
        await message.answer(response)
        return

    verified = stats.get(AttributionStatus.VERIFIED, 0)
    pending = stats.get(AttributionStatus.PENDING, 0)
    revoked = stats.get(AttributionStatus.REVOKED, 0)
    invite_line = f"\nLink: {invite_link}" if invite_link else ""

    text = (
        "Your referral stats:\n"
        f"Verified: {verified}\n"
        f"Pending: {pending}\n"
        f"Revoked: {revoked}"
        f"{invite_line}"
    )
    await message.answer(text, disable_web_page_preview=True)


def _affiliate_display_name(affiliate) -> str:
    owner = affiliate.owner
    if owner:
        if owner.username:
            return f"@{owner.username}"
        parts = [owner.first_name, owner.last_name]
        name = " ".join(filter(None, parts)).strip()
        if name:
            return name
        return str(owner.id)
    return f"Affiliate #{affiliate.id}"


def _format_table(rows: Sequence[Tuple]) -> str:
    lines = ["Rank Affiliate            Verified"]
    for index, (affiliate, total) in enumerate(rows, start=1):
        label = _affiliate_display_name(affiliate)
        lines.append(f"{index:>4} {label:<20.20} {total:>9}")
    return "\n".join(lines)


def _format_status_summary(label: str, counts: Dict[AttributionStatus, int]) -> str:
    verified = counts.get(AttributionStatus.VERIFIED, 0)
    pending = counts.get(AttributionStatus.PENDING, 0)
    revoked = counts.get(AttributionStatus.REVOKED, 0)
    return f"{label}: V {verified} | P {pending} | R {revoked}"


@router.message(Command("top"))
async def handle_top(message: Message, command: CommandObject) -> None:
    if not _rate_limit(message, "top"):
        await message.answer("Too many requests. Please try again shortly.")
        return
    args = (command.args or "").split()
    window = "all"
    limit = 10

    if args:
        token = args[0].lower()
        if token in {"7d", "30d"}:
            window = token
            args = args[1:]
    if args:
        try:
            limit = max(1, min(50, int(args[0])))
        except ValueError:
            pass

    with session_scope() as session:
        rows = leaderboard_service.top_affiliates(
            session,
            limit=limit,
            window=window,
        )

    if not rows:
        await message.answer("No verified referrals yet.")
        return

    table = _format_table(rows)
    cache_time = leaderboard_service.cache_generated_at(window)
    footer = ""
    if cache_time:
        footer = f"\n\nCached: {cache_time.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"

    await message.answer(
        f"<pre>{escape(table)}</pre>{footer}",
        disable_web_page_preview=True,
    )


@router.message(Command("affiliates"))
async def handle_affiliates(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    now = datetime.now(tz=timezone.utc)
    with session_scope() as session:
        summary = affiliates_service.count_affiliates(session)
        last_7d = attributions_service.count_by_status_since(session, now - timedelta(days=7))
        last_30d = attributions_service.count_by_status_since(session, now - timedelta(days=30))

    text = (
        "Affiliate overview:\n"
        f"Active: {summary['active']} of {summary['total']} total\n"
        f"Inactive: {summary['inactive']}\n"
        f"{_format_status_summary('Last 7d', last_7d)}\n"
        f"{_format_status_summary('Last 30d', last_30d)}"
    )
    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("pause_links"))
async def handle_pause_links(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    with session_scope() as session:
        updated = affiliates_service.bulk_set_active(session, False)

    await message.answer(
        f"Paused {updated} affiliate link(s). Existing attributions remain intact.",
        disable_web_page_preview=True,
    )


@router.message(Command("resume_links"))
async def handle_resume_links(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    with session_scope() as session:
        updated = affiliates_service.bulk_set_active(session, True)

    await message.answer(
        f"Reactivated {updated} affiliate link(s).",
        disable_web_page_preview=True,
    )


@router.message(Command("rebuild_counts"))
async def handle_rebuild_counts(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    leaderboard_service.recompute_cache()
    parts = []
    for window in leaderboard_service.LEADERBOARD_WINDOWS:
        ts = leaderboard_service.cache_generated_at(window)
        label = window
        if window == "all":
            label = "all_time"
        parts.append(f"{label}: {_format_timestamp(ts) if ts else 'unknown'}")

    await message.answer(
        "Leaderboard counts rebuilt.\n" + "\n".join(parts),
        disable_web_page_preview=True,
    )


@router.message(Command("review_pending"))
async def handle_review_pending(message: Message) -> None:
    if not await _ensure_admin(message):
        return

    with session_scope() as session:
        rows = attributions_service.list_pending_reviews(session, limit=10)

    if not rows:
        await message.answer("No pending suspected attributions.")
        return

    lines: List[str] = []
    keyboard = InlineKeyboardBuilder()
    for item in rows:
        user_label = _friendly_user_label(item.joined_user)
        affiliate_label = _affiliate_display_name(item.affiliate)
        note = item.note or "pending_review"
        joined_at = _format_timestamp(item.joined_at)
        lines.append(
            f"#{item.id} {user_label} via {affiliate_label} [{note}] at {joined_at}"
        )
        keyboard.button(
            text=f"Verify #{item.id}",
            callback_data=f"review:verify:{item.id}",
        )
        keyboard.button(
            text=f"Revoke #{item.id}",
            callback_data=f"review:revoke:{item.id}",
        )

    keyboard.adjust(2)
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboard.as_markup(),
        disable_web_page_preview=True,
    )


def _parse_who_invited_target(command: CommandObject) -> Optional[str]:
    args = (command.args or "").strip()
    return args or None


@router.message(Command("who_invited"))
async def handle_who_invited(message: Message, command: CommandObject) -> None:
    if not await _ensure_admin(message):
        return

    target_arg = _parse_who_invited_target(command)
    if not target_arg:
        await message.answer("Usage: /who_invited <@username|user_id>")
        return

    target_user = None

    with session_scope() as session:
        if target_arg.lstrip("@").isdigit():
            target_user = users_service.get_user(session, int(target_arg.lstrip("@")))
        else:
            target_user = users_service.get_user_by_username(session, target_arg)

        if not target_user:
            await message.answer("No records found for that user.")
            return

        attribution = attributions_service.get_attribution_by_user(session, target_user.id)
        if not attribution:
            await message.answer("No affiliate attribution found for that user.")
            return

        affiliate = attribution.affiliate
        status_text = attribution.status.value
        verified_label = _format_timestamp(attribution.verified_at)
        verified_at = f", verified at {verified_label}" if verified_label else ""
        inviter = _affiliate_display_name(affiliate)

    await message.answer(
        f"{_friendly_user_label(target_user)} was invited by {inviter} (status: {status_text}{verified_at}).",
        disable_web_page_preview=True,
    )


def _friendly_user_label(user) -> str:
    if user.username:
        return f"@{user.username}"
    parts = [user.first_name, user.last_name]
    name = " ".join(filter(None, parts)).strip()
    if name:
        return name
    return str(user.id)


def _format_timestamp(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@router.callback_query(F.data.startswith("review:"))
async def handle_review_callback(callback: CallbackQuery) -> None:
    user = callback.from_user
    if user is None or not await _is_admin(callback.bot, user.id):
        await callback.answer("Admin only.", show_alert=True)
        return

    if not callback.data:
        await callback.answer()
        return

    try:
        _, action, attr_id_str = callback.data.split(":")
        attr_id = int(attr_id_str)
    except ValueError:
        await callback.answer("Invalid data.", show_alert=True)
        return

    now = datetime.now(tz=timezone.utc)
    message_text = ""

    user_id = None
    with session_scope() as session:
        attribution = session.get(Attribution, attr_id)
        if not attribution:
            await callback.answer("Attribution not found.", show_alert=True)
            return

        user_id = attribution.joined_user_id
        if action == "verify":
            attributions_service.update_attribution_status(
                session,
                attribution,
                AttributionStatus.VERIFIED,
                verified_at=now,
            )
            attribution.note = None
            session.add(attribution)
            message_text = f"Attribution #{attr_id} verified."
        elif action == "revoke":
            attributions_service.update_attribution_status(
                session,
                attribution,
                AttributionStatus.REVOKED,
                verified_at=attribution.verified_at,
            )
            attribution.note = attributions_service.merge_note(
                attribution.note, "manual_revoke"
            )
            session.add(attribution)
            message_text = f"Attribution #{attr_id} revoked."
        else:
            await callback.answer("Unsupported action.", show_alert=True)
            return

    await callback.answer(message_text, show_alert=False)
    if user_id is not None:
        integrity_service.cancel_verification(user_id)
