from __future__ import annotations

from collections import Counter

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .game_data import GOODS, LEGAL_GOODS


def private_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎒 Мой мешок", callback_data="menu:bag")],
        [InlineKeyboardButton(text="📦 Моя рука", callback_data="menu:hand")],
        [InlineKeyboardButton(text="💰 Взятка", callback_data="menu:bribe")],
        [InlineKeyboardButton(text="📊 Статус партии", callback_data="menu:status")],
    ])


def bag_keyboard(hand: list[str], bag: list[str]) -> InlineKeyboardMarkup:
    hand_counter = Counter(hand)
    bag_counter = Counter(bag)
    rows: list[list[InlineKeyboardButton]] = []
    for key, total in hand_counter.items():
        good = GOODS[key]
        selected = bag_counter[key]
        rows.append([
            InlineKeyboardButton(
                text=f"{good.emoji} {good.name}: {selected}/{total}",
                callback_data=f"bag:toggle:{key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🧹 Очистить", callback_data="bag:clear"),
        InlineKeyboardButton(text="🔒 Запечатать", callback_data="bag:lock"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def declaration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=GOODS[key].label, callback_data=f"declare:{key}")]
        for key in LEGAL_GOODS
    ])


def bribe_keyboard(current: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="−5", callback_data=f"bribe:set:{max(0, current-5)}"),
            InlineKeyboardButton(text="−1", callback_data=f"bribe:set:{max(0, current-1)}"),
            InlineKeyboardButton(text=f"💰 {current}", callback_data="noop"),
            InlineKeyboardButton(text="+1", callback_data=f"bribe:set:{current+1}"),
            InlineKeyboardButton(text="+5", callback_data=f"bribe:set:{current+5}"),
        ],
        [InlineKeyboardButton(text="✅ Предложить", callback_data=f"bribe:confirm:{current}")],
    ])


def sheriff_keyboard(merchants: list[dict], bribes: dict[int, int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for merchant in merchants:
        if merchant["resolved"]:
            continue
        uid = merchant["user_id"]
        declaration = GOODS.get(merchant["declared_good"])
        bag_size = len(__import__("json").loads(merchant["bag_json"]))
        bribe = bribes.get(uid, 0)
        title = f"{merchant['full_name']} · {bag_size} {declaration.emoji if declaration else '📦'} · 💰{bribe}"
        rows.append([InlineKeyboardButton(text=title, callback_data=f"sheriff:merchant:{uid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="✅ Все решено", callback_data="noop")]])


def sheriff_decision_keyboard(merchant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Пропустить", callback_data=f"sheriff:pass:{merchant_id}")],
        [InlineKeyboardButton(text="🔍 Вскрыть мешок", callback_data=f"sheriff:inspect:{merchant_id}")],
        [InlineKeyboardButton(text="⬅️ К торговцам", callback_data="sheriff:list")],
    ])
