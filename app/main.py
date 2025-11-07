from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress
from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

from .config import get_settings
from .db import init_db
from .handlers import get_routers
from .middlewares import ErrorHandlingMiddleware, RequestContextMiddleware
from .services.leaderboard import recompute_cache, start_leaderboard_rollup
from .utils.logging import request_ip_var, setup_logging


async def main() -> None:
    setup_logging()
    settings = get_settings()
    init_db()
    recompute_cache()
    start_leaderboard_rollup()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.update.middleware.register(RequestContextMiddleware())
    dp.update.middleware.register(ErrorHandlingMiddleware())

    for router in get_routers():
        dp.include_router(router)

    if settings.webhook_url:
        await _run_webhook(bot, dp, settings.host, settings.port, settings.webhook_url, settings.webhook_secret_token)
    else:
        await _run_polling(bot, dp)


async def _run_polling(bot: Bot, dp: Dispatcher) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Starting long polling mode")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("Polling stopped")


async def _run_webhook(
    bot: Bot,
    dp: Dispatcher,
    host: str,
    port: int,
    webhook_url: str,
    secret_token: Optional[str],
) -> None:
    logger = logging.getLogger(__name__)
    @web.middleware
    async def request_context(request: web.Request, handler):
        forwarded = request.headers.get("X-Forwarded-For")
        remote_ip = None
        if forwarded:
            remote_ip = forwarded.split(",")[0].strip()
        elif request.remote:
            remote_ip = request.remote
        token = request_ip_var.set(remote_ip)
        try:
            return await handler(request)
        finally:
            request_ip_var.reset(token)

    app = web.Application(middlewares=[request_context])

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", health)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret_token)
    handler.register(app, path="/webhook")

    async def on_startup(_: web.Application) -> None:
        dp.startup()
        await bot.set_webhook(
            webhook_url,
            secret_token=secret_token,
            drop_pending_updates=True,
        )
        logger.info(
            "Webhook set",
            extra={"webhook_url": webhook_url, "host": host, "port": port},
        )

    async def on_shutdown(_: web.Application) -> None:
        await bot.delete_webhook(drop_pending_updates=False)
        dp.shutdown()
        await bot.session.close()
        logger.info("Webhook removed")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("Webhook server started", extra={"host": host, "port": port})

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await runner.cleanup()
        logger.info("Webhook server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Bot stopped")
