from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import load_settings
from app.db import Database
from app.handlers import common_router, deals_router, game_router, rules_help_router, ux_router
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
    # Beginner help goes first so the Rules button always opens the detailed guide.
    # UX then handles the button-first game flow; legacy handlers remain fallbacks.
    dp.include_router(rules_help_router)
    dp.include_router(ux_router)
    dp.include_router(common_router)
    dp.include_router(deals_router)
    dp.include_router(game_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Відкрити панель купця"),
        BotCommand(command="newgame", description="Зібрати купців біля брами"),
        BotCommand(command="join", description="Приєднатися до купців"),
        BotCommand(command="begin", description="Вирушити до брами"),
        BotCommand(command="market", description="Торг на ринку"),
        BotCommand(command="hand", description="Показати мої товари"),
        BotCommand(command="bag", description="Зібрати вантаж повозки"),
        BotCommand(command="deal", description="Угоди з міською вартою"),
        BotCommand(command="promise", description="Майбутня обіцянка"),
        BotCommand(command="bribe", description="Швидкий хабар у кронах"),
        BotCommand(command="inspect", description="Панель міської варти"),
        BotCommand(command="status", description="Стан біля брами"),
    ])

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
