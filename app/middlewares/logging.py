from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..utils.logging import request_id_var, request_ip_var


class RequestContextMiddleware(BaseMiddleware):
    def __init__(self, *, header_key: str = "X-Request-ID") -> None:
        super().__init__()
        self.header_key = header_key

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        request_id = data.get("request_id")
        if not request_id:
            request_id = uuid.uuid4().hex
        token = request_id_var.set(request_id)
        source_ip = data.get("request_ip") or request_ip_var.get()
        if source_ip:
            request_ip_token = request_ip_var.set(source_ip)
        else:
            request_ip_token = None
        data["request_id"] = request_id
        if source_ip:
            data["request_ip"] = source_ip
        try:
            return await handler(event, data)
        finally:
            request_id_var.reset(token)
            if request_ip_token is not None:
                request_ip_var.reset(request_ip_token)


class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger = logging.getLogger("app.middleware.error")
            logger.exception(
                "Unhandled exception during update processing",
                extra={
                    "event_type": type(event).__name__,
                    "request_id": data.get("request_id"),
                },
            )
            raise
