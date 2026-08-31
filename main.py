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
    dp.include_router(common_router)
    dp.include_router(game_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Відкрити особисте меню"),
        BotCommand(command="newgame", description="Створити лобі в групі"),
        BotCommand(command="join", description="Приєднатися до лобі"),
        BotCommand(command="begin", description="Почати партію"),
        BotCommand(command="market", description="Торгівля: скинути й добрати карти"),
        BotCommand(command="hand", description="Показати мою руку"),
        BotCommand(command="bag", description="Зібрати мішок"),
        BotCommand(command="bribe", description="Запропонувати хабар"),
        BotCommand(command="inspect", description="Панель шерифа"),
        BotCommand(command="status", description="Стан партії"),
    ])

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
