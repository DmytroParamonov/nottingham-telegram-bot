from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..tutorials import beginner_rules_text


router = Router(name="rules_help")


@router.callback_query(F.data == "ui:rules")
async def ui_rules_for_beginners(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(beginner_rules_text())
