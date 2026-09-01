from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..tutorials import beginner_rules_text


router = Router(name="rules_help")


def split_telegram_text(text: str, limit: int = 3500) -> list[str]:
    """Split long HTML-formatted help text on paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)

        # Fallback for an unexpectedly huge single paragraph.
        while len(paragraph) > limit:
            cut = paragraph.rfind("\n", 0, limit)
            if cut <= 0:
                cut = paragraph.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()

        current = paragraph

    if current:
        chunks.append(current)

    return chunks


@router.callback_query(F.data == "ui:rules")
async def ui_rules_for_beginners(callback: CallbackQuery) -> None:
    await callback.answer("Відкриваю правила 📜")
    chunks = split_telegram_text(beginner_rules_text())
    total = len(chunks)

    for index, chunk in enumerate(chunks, 1):
        if total > 1:
            chunk = f"<b>Правила · {index}/{total}</b>\n\n{chunk}"
        await callback.message.answer(chunk)
