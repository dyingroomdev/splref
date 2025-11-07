from __future__ import annotations

import argparse
import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from .config import get_settings
from .utils.logging import setup_logging


async def _set_webhook(drop_pending: bool) -> None:
    settings = get_settings()
    if not settings.webhook_url:
        raise ValueError("WEBHOOK_URL must be set to configure webhook.")

    setup_logging()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    try:
        await bot.set_webhook(
            settings.webhook_url,
            secret_token=settings.webhook_secret_token,
            drop_pending_updates=drop_pending,
        )
    finally:
        await bot.session.close()
    logging.getLogger(__name__).info(
        "Webhook set",
        extra={"webhook_url": settings.webhook_url, "drop_pending": drop_pending},
    )


async def _delete_webhook() -> None:
    settings = get_settings()
    setup_logging()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    finally:
        await bot.session.close()
    logging.getLogger(__name__).info("Webhook deleted")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage Telegram webhook configuration.")
    parser.add_argument("action", choices=["set", "delete"])
    parser.add_argument(
        "--drop-pending",
        action="store_true",
        help="Drop pending updates when setting webhook.",
    )
    args = parser.parse_args()

    if args.action == "set":
        asyncio.run(_set_webhook(args.drop_pending))
    elif args.action == "delete":
        asyncio.run(_delete_webhook())


if __name__ == "__main__":
    main()
