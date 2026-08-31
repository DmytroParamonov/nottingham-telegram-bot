from __future__ import annotations

from collections import Counter

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .game_data import GOODS, LEGAL_GOODS


def private_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Торгівля", callback_data="menu:market")],
        [InlineKeyboardButton(text="🎒 Мій мішок", callback_data="menu:bag")],
        [InlineKeyboardButton(text="📦 Моя рука", callback_data="menu:hand")],
        [InlineKeyboardButton(text="💰 Хабар", callback_data="menu:bribe")],
        [InlineKeyboardButton(text="📊 Стан партії", callback_data="menu:status")],
    ])


def market_first_keyboard(merchants: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"▶️ {merchant['full_name']}",
                callback_data=f"market:first:{merchant['user_id']}",
            )
        ]
        for merchant in merchants
    ])


def market_keyboard(hand: list[str], selected: list[str]) -> InlineKeyboardMarkup:
    hand_counter = Counter(hand)
    selected_counter = Counter(selected)
    rows: list[list[InlineKeyboardButton]] = []
    for key, total in hand_counter.items():
        good = GOODS[key]
        chosen = selected_counter[key]
        rows.append([
            InlineKeyboardButton(
                text=f"{good.emoji} {good.name}: скинути {chosen}/{total}",
                callback_data=f"market:toggle:{key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(text="🧹 Очистити", callback_data="market:clear"),
        InlineKeyboardButton(text="✅ Завершити торгівлю", callback_data="market:confirm"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        InlineKeyboardButton(text="🧹 Очистити", callback_data="bag:clear"),
        InlineKeyboardButton(text="🔒 Запечатати", callback_data="bag:lock"),
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
            InlineKeyboardButton(text="−5", callback_data=f"bribe:set:{max(0, current - 5)}"),
            InlineKeyboardButton(text="−1", callback_data=f"bribe:set:{max(0, current - 1)}"),
            InlineKeyboardButton(text=f"💰 {current}", callback_data="noop"),
            InlineKeyboardButton(text="+1", callback_data=f"bribe:set:{current + 1}"),
            InlineKeyboardButton(text="+5", callback_data=f"bribe:set:{current + 5}"),
        ],
        [InlineKeyboardButton(text="✅ Запропонувати", callback_data=f"bribe:confirm:{current}")],
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
        title = (
            f"{merchant['full_name']} · {bag_size} "
            f"{declaration.emoji if declaration else '📦'} · 💰{bribe}"
        )
        rows.append([InlineKeyboardButton(text=title, callback_data=f"sheriff:merchant:{uid}")])
    return InlineKeyboardMarkup(
        inline_keyboard=rows or [[InlineKeyboardButton(text="✅ Усе вирішено", callback_data="noop")]]
    )


def sheriff_decision_keyboard(merchant_id: int, bribe: int = 0) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if bribe > 0:
        rows.append([
            InlineKeyboardButton(
                text=f"💰 Прийняти хабар {bribe} і пропустити",
                callback_data=f"sheriff:accept:{merchant_id}",
            )
        ])
    rows.extend([
        [InlineKeyboardButton(text="✅ Пропустити без хабара", callback_data=f"sheriff:pass:{merchant_id}")],
        [InlineKeyboardButton(text="🔍 Оглянути мішок", callback_data=f"sheriff:inspect:{merchant_id}")],
        [InlineKeyboardButton(text="⬅️ До торговців", callback_data="sheriff:list")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
