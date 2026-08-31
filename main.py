from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import load_settings
from app.db import Database
from app.handlers import common_router, game_router
from app.service import GameService
from app.runtime import set_service


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
    dp.include_router(common_router)
    dp.include_router(game_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Открыть личное меню"),
        BotCommand(command="newgame", description="Создать лобби в группе"),
        BotCommand(command="join", description="Войти в лобби"),
        BotCommand(command="begin", description="Начать партию"),
        BotCommand(command="hand", description="Показать мою руку"),
        BotCommand(command="bag", description="Собрать мешок"),
        BotCommand(command="bribe", description="Предложить взятку"),
        BotCommand(command="inspect", description="Панель шерифа"),
        BotCommand(command="status", description="Статус партии"),
    ])

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
