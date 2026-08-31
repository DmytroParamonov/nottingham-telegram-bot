from __future__ import annotations

from collections import Counter
from html import escape

from .db import loads
from .game_data import GOODS
from .texts import PHASE_NAMES, public_stall_summary


def esc(value: object) -> str:
    return escape(str(value), quote=False)


def _phase_icon(phase: str) -> str:
    return {
        "lobby": "🏰",
        "market": "🛒",
        "packing": "🎒",
        "declaration": "📜",
        "inspection": "🔍",
        "finished": "🏆",
        "cancelled": "🚫",
    }.get(phase, "🎲")


def render_group_home() -> str:
    return (
        "🏰 <b>ШЕРИФ НОТТІНГЕМА</b>\n"
        "<i>Telegram-гра про блеф, контрабанду та хабарі</i>\n\n"
        "Ніякої гори команд: створи партію кнопкою нижче, а далі бот сам "
        "показуватиме потрібні дії на кожному кроці.\n\n"
        "👥 3–5 гравців · 🇺🇦 український інтерфейс"
    )


def render_lobby_table(players: list[dict], owner_id: int) -> str:
    lines = [
        "🏰 <b>НОТТІНГЕМ · ЛОБІ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👥 Гравців: <b>{len(players)}/5</b>",
        "",
    ]
    for index, player in enumerate(players, 1):
        crown = " 👑" if player["user_id"] == owner_id else ""
        lines.append(f"{index}. <b>{esc(player['full_name'])}</b>{crown}")
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Кожен гравець має один раз відкрити бота в ЛС і натиснути /start, "
        "щоб я міг надсилати таємну руку.",
    ]
    return "\n".join(lines)


def _player_phase_icon(game: dict, player: dict, sheriff_id: int | None) -> str:
    if sheriff_id == player["user_id"]:
        return "👮"
    phase = game["phase"]
    if phase == "market":
        return "✅" if player["resolved"] else "⏳"
    if phase == "packing":
        return "🔒" if player["bag_locked"] else "🎒"
    if phase == "declaration":
        return "✅" if player["declared_good"] else "📜"
    if phase == "inspection":
        return "✅" if player["resolved"] else "🧳"
    return "•"


def render_game_table(
    game: dict,
    players: list[dict],
    sheriff: dict | None,
    *,
    current_trader: dict | None = None,
    current_declarer: dict | None = None,
) -> str:
    phase = game["phase"]
    sheriff_id = sheriff["user_id"] if sheriff else None
    lines = [
        f"{_phase_icon(phase)} <b>НОТТІНГЕМ · РАУНД {game['round_no']}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Етап: <b>{esc(PHASE_NAMES.get(phase, phase))}</b>",
    ]
    if sheriff:
        lines.append(f"👮 Шериф: <b>{esc(sheriff['full_name'])}</b>")
    if current_trader:
        lines.append(f"🛒 Зараз торгує: <b>{esc(current_trader['full_name'])}</b>")
    if current_declarer:
        lines.append(f"📜 Зараз декларує: <b>{esc(current_declarer['full_name'])}</b>")
    lines += ["", "<b>Гравці</b>"]

    for player in players:
        marker = _player_phase_icon(game, player, sheriff_id)
        market = loads(player["market_json"])
        lines.append(
            f"{marker} <b>{esc(player['full_name'])}</b> · 💰 {player['coins']}\n"
            f"   🏪 {public_stall_summary(market)}"
        )

    phase_hint = {
        "market": "Шериф обирає першого торговця, далі торгуємо по колу.",
        "packing": "Торговці таємно збирають і запечатують мішки.",
        "declaration": "Декларації йдуть по черзі зліва від шерифа.",
        "inspection": "Час переговорів: хабарі, угоди й рішення шерифа.",
    }.get(phase)
    if phase_hint:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━", f"💡 {phase_hint}"]
    return "\n".join(lines)


def render_private_hub(
    game: dict,
    player: dict,
    sheriff: dict,
    *,
    current_trader: dict | None = None,
    current_declarer: dict | None = None,
) -> str:
    is_sheriff = sheriff["user_id"] == player["user_id"]
    role = "👮 <b>ШЕРИФ</b>" if is_sheriff else "🧳 <b>ТОРГОВЕЦЬ</b>"
    market = loads(player["market_json"])
    hand = loads(player["hand_json"])
    bag = loads(player["bag_json"])
    phase = game["phase"]

    lines = [
        "🏰 <b>МІЙ НОТТІНГЕМ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Раунд <b>{game['round_no']}</b> · {_phase_icon(phase)} <b>{esc(PHASE_NAMES.get(phase, phase))}</b>",
        role,
        f"💰 Золото: <b>{player['coins']}</b>",
        f"📦 Рука: <b>{len(hand)}</b> карт",
        f"🏪 Прилавок: {public_stall_summary(market)}",
    ]
    if not is_sheriff and phase in {"packing", "declaration", "inspection"}:
        bag_state = "🔒 запечатано" if player["bag_locked"] else "відкрито"
        lines.append(f"🎒 Мішок: <b>{len(bag)}</b> карт · {bag_state}")
    if player.get("declared_good"):
        good = GOODS[player["declared_good"]]
        lines.append(f"📜 Декларація: <b>{len(bag)} × {good.emoji} {good.name}</b>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━"]
    if phase == "market":
        if is_sheriff and game.get("market_start_seat") is None:
            lines.append("👉 <b>Твоя дія:</b> обери, хто торгує першим.")
        elif is_sheriff:
            name = esc(current_trader["full_name"]) if current_trader else "—"
            lines.append(f"👀 Стеж за Торгівлею. Зараз: <b>{name}</b>.")
        elif current_trader and current_trader["user_id"] == player["user_id"]:
            lines.append("👉 <b>Твоя дія:</b> зараз твій хід у Торгівлі.")
        else:
            name = esc(current_trader["full_name"]) if current_trader else "шериф ще визначає порядок"
            lines.append(f"⏳ Чекай своєї черги. Зараз: <b>{name}</b>.")
    elif phase == "packing":
        lines.append("👉 Збери мішок 1–5 карт і запечатай його.")
    elif phase == "declaration":
        if current_declarer and current_declarer["user_id"] == player["user_id"]:
            lines.append("👉 <b>Твоя черга декларувати товар.</b>")
        else:
            name = esc(current_declarer["full_name"]) if current_declarer else "—"
            lines.append(f"📜 Чекаємо декларацію: <b>{name}</b>.")
    elif phase == "inspection":
        if is_sheriff:
            lines.append("👉 Вирішуй долю мішків і переглядай формальні угоди.")
        elif player["resolved"]:
            lines.append("✅ Твій мішок уже пройшов ворота. Можеш впливати на чужі угодами.")
        else:
            lines.append("😏 Торгуйся з шерифом: золото, товари, блеф і складні угоди.")
    return "\n".join(lines)


def render_hand_panel(hand: list[str]) -> str:
    counter = Counter(hand)
    lines = ["📦 <b>МОЯ РУКА</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for key, count in counter.items():
        good = GOODS[key]
        tag = "🟢 ДОЗВОЛЕНО" if good.legal else "🔴 КОНТРАБАНДА"
        lines.append(
            f"{good.emoji} <b>{good.name}</b> ×{count}\n"
            f"   {tag} · 💎 {good.value} · ⚖️ {good.penalty}"
        )
    return "\n".join(lines)
