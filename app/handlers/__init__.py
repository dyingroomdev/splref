from typing import Iterable

from aiogram import Router

from . import admin, commands, members


def get_routers() -> Iterable[Router]:
    return (
        commands.router,
        members.router,
        admin.router,
    )


__all__ = ["get_routers"]
