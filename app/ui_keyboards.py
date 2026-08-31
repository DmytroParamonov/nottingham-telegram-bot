from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def group_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Створити партію", callback_data="ui:create")],
        [InlineKeyboardButton(text="📜 Як грати", callback_data="ui:rules")],
    ])


def lobby_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Приєднатися", callback_data="ui:join"),
            InlineKeyboardButton(text="🚪 Вийти", callback_data="ui:leave"),
        ],
        [InlineKeyboardButton(text="🚀 ПОЧАТИ ГРУ", callback_data="ui:begin")],
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data="ui:table"),
            InlineKeyboardButton(text="📜 Правила", callback_data="ui:rules"),
        ],
    ])


def game_table_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 МОЯ ПАНЕЛЬ", callback_data="ui:me")],
        [
            InlineKeyboardButton(text="🔄 Оновити стіл", callback_data="ui:table"),
            InlineKeyboardButton(text="📜 Правила", callback_data="ui:rules"),
        ],
    ])


def private_hub_keyboard(
    *,
    phase: str,
    is_sheriff: bool,
    is_current_trader: bool = False,
    market_order_missing: bool = False,
    is_current_declarer: bool = False,
    resolved: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if phase == "market":
        if is_sheriff and market_order_missing:
            rows.append([InlineKeyboardButton(text="👮 Обрати першого торговця", callback_data="menu:market")])
        elif not is_sheriff and is_current_trader:
            rows.append([InlineKeyboardButton(text="🛒 ЗРОБИТИ ХІД У ТОРГІВЛІ", callback_data="menu:market")])
    elif phase == "packing" and not is_sheriff:
        rows.append([InlineKeyboardButton(text="🎒 ЗІБРАТИ МІШОК", callback_data="menu:bag")])
    elif phase == "declaration" and not is_sheriff and is_current_declarer:
        rows.append([InlineKeyboardButton(text="📜 ЗАДЕКЛАРУВАТИ ТОВАР", callback_data="ui:declare")])
    elif phase == "inspection":
        if is_sheriff:
            rows.append([InlineKeyboardButton(text="👮 ПАНЕЛЬ ШЕРИФА", callback_data="sheriff:list")])
            rows.append([InlineKeyboardButton(text="🤝 Вхідні угоди", callback_data="menu:deals")])
        else:
            rows.append([InlineKeyboardButton(text="🤝 УГОДИ ТА ХАБАРІ", callback_data="menu:deals")])
            if not resolved:
                rows.append([InlineKeyboardButton(text="💰 Швидкий хабар", callback_data="menu:bribe")])

    rows.append([
        InlineKeyboardButton(text="📦 Рука", callback_data="ui:hand"),
        InlineKeyboardButton(text="📊 Стан", callback_data="menu:status"),
    ])
    rows.append([InlineKeyboardButton(text="🔄 Оновити мою панель", callback_data="ui:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def private_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 ВІДКРИТИ МОЮ ПАНЕЛЬ", callback_data="ui:home")],
        [InlineKeyboardButton(text="📜 Короткі правила", callback_data="ui:rules")],
    ])
