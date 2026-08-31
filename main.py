from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import load_settings
from app.db import Database
from app.handlers import common_router, deals_router, game_router, ux_router
from app.runtime import set_service
from app.service import GameService


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    settings = load_settings()
    db = Database(settings.database_path)
    await db.init()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    service = GameService(db)
    set_service(service)

    dp = Dispatcher()
    # UX first: it intercepts start/lobby commands and presents the button-first
    # interface. Legacy handlers stay enabled as a fallback for old messages.
    dp.include_router(ux_router)
    dp.include_router(common_router)
    dp.include_router(deals_router)
    dp.include_router(game_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Відкрити ігрову панель"),
        BotCommand(command="newgame", description="Створити лобі"),
        BotCommand(command="join", description="Приєднатися до лобі"),
        BotCommand(command="begin", description="Почати партію"),
        BotCommand(command="market", description="Торгівля"),
        BotCommand(command="hand", description="Показати руку"),
        BotCommand(command="bag", description="Зібрати мішок"),
        BotCommand(command="deal", description="Угоди та хабарі"),
        BotCommand(command="promise", description="Майбутня обіцянка"),
        BotCommand(command="bribe", description="Швидкий грошовий хабар"),
        BotCommand(command="inspect", description="Панель шерифа"),
        BotCommand(command="status", description="Стан партії"),
    ])

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
