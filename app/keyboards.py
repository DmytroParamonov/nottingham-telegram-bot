from __future__ import annotations

from collections import Counter

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .db import loads
from .game_data import GOODS, LEGAL_GOODS


def private_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Торгівля", callback_data="menu:market")],
        [InlineKeyboardButton(text="🎒 Мій мішок", callback_data="menu:bag")],
        [InlineKeyboardButton(text="📦 Моя рука", callback_data="menu:hand")],
        [InlineKeyboardButton(text="🤝 Угоди та хабарі", callback_data="menu:deals")],
        [InlineKeyboardButton(text="💰 Швидкий хабар", callback_data="menu:bribe")],
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


def deal_builder_keyboard(merchants: list[dict], deal: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    target_id = deal.get("target_id")
    action = deal.get("action")
    for merchant in merchants:
        if merchant["resolved"]:
            continue
        uid = merchant["user_id"]
        pass_mark = "🟢" if target_id == uid and action == "pass" else "✅"
        inspect_mark = "🟠" if target_id == uid and action == "inspect" else "🔍"
        short = merchant["full_name"][:18]
        rows.append([
            InlineKeyboardButton(
                text=f"{pass_mark} Пропустити {short}",
                callback_data=f"deal:target:pass:{uid}",
            ),
            InlineKeyboardButton(
                text=f"{inspect_mark} Оглянути {short}",
                callback_data=f"deal:target:inspect:{uid}",
            ),
        ])

    gold = int(deal.get("gold") or 0)
    rows.append([
        InlineKeyboardButton(text="−5", callback_data="deal:gold:-5"),
        InlineKeyboardButton(text="−1", callback_data="deal:gold:-1"),
        InlineKeyboardButton(text=f"💰 {gold}", callback_data="noop"),
        InlineKeyboardButton(text="+1", callback_data="deal:gold:+1"),
        InlineKeyboardButton(text="+5", callback_data="deal:gold:+5"),
    ])
    rows.append([
        InlineKeyboardButton(text="🏪 Товари з прилавка", callback_data="deal:goods:stand"),
        InlineKeyboardButton(text="🎒 Товари з мішка", callback_data="deal:goods:bag"),
    ])
    follow = "📌 Додатковий огляд"
    if deal.get("followup_inspect_id"):
        follow = "📌 Додатковий огляд ✓"
    rows.append([
        InlineKeyboardButton(text=follow, callback_data="deal:followup"),
        InlineKeyboardButton(text="💭 Майбутня обіцянка", callback_data="deal:promise_help"),
    ])
    rows.append([
        InlineKeyboardButton(text="🧹 Скинути", callback_data="deal:reset"),
        InlineKeyboardButton(text="📤 Надіслати шерифу", callback_data="deal:offer"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deal_goods_keyboard(source: str, deal: dict) -> InlineKeyboardMarkup:
    column = "stand_goods_json" if source == "stand" else "bag_goods_json"
    goods = loads(deal.get(column), {})
    rows: list[list[InlineKeyboardButton]] = []
    for key, good in GOODS.items():
        count = int(goods.get(key, 0))
        rows.append([
            InlineKeyboardButton(text="−", callback_data=f"deal:good:{source}:{key}:-1"),
            InlineKeyboardButton(text=f"{good.emoji} {good.name} ×{count}", callback_data="noop"),
            InlineKeyboardButton(text="+", callback_data=f"deal:good:{source}:{key}:+1"),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ До угоди", callback_data="menu:deals")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deal_followup_keyboard(merchants: list[dict], deal: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🚫 Без додаткового огляду", callback_data="deal:followup:set:0")]
    ]
    primary = deal.get("target_id")
    current = deal.get("followup_inspect_id")
    for merchant in merchants:
        if merchant["resolved"] or merchant["user_id"] == primary:
            continue
        mark = "📌" if merchant["user_id"] == current else "🔍"
        rows.append([
            InlineKeyboardButton(
                text=f"{mark} {merchant['full_name']}",
                callback_data=f"deal:followup:set:{merchant['user_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ До угоди", callback_data="menu:deals")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deal_offer_keyboard(deal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤝 УГОДА — прийняти", callback_data=f"deal:accept:{deal_id}"),
            InlineKeyboardButton(text="❌ Відхилити", callback_data=f"deal:reject:{deal_id}"),
        ]
    ])
