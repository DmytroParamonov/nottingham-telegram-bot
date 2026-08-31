from __future__ import annotations

from collections import Counter

from .db import loads
from .game_data import GOODS


PHASE_NAMES = {
    "lobby": "Лобі",
    "market": "Торгівля",
    "packing": "Завантаження товарів",
    "declaration": "Декларування",
    "inspection": "Огляд",
    "finished": "Завершено",
    "cancelled": "Скасовано",
}


def player_name(row: dict) -> str:
    return row["full_name"]


def render_hand(hand: list[str]) -> str:
    counter = Counter(hand)
    lines = ["📦 <b>Твоя рука</b>"]
    for key, count in counter.items():
        good = GOODS[key]
        kind = "дозволений товар" if good.legal else "КОНТРАБАНДА"
        lines.append(
            f"{good.emoji} {good.name} ×{count} · {kind} · "
            f"ціна {good.value} · штраф {good.penalty}"
        )
    return "\n".join(lines)


def render_lobby(players: list[dict], owner_id: int) -> str:
    lines = ["🏰 <b>Шериф Ноттінгема — лобі</b>", ""]
    for i, p in enumerate(players, 1):
        crown = " 👑" if p["user_id"] == owner_id else ""
        lines.append(f"{i}. {p['full_name']}{crown}")
    lines += ["", "Команди: /join · /leave · /begin"]
    return "\n".join(lines)


def public_stall_summary(cards: list[str]) -> str:
    legal = Counter(card for card in cards if GOODS[card].legal)
    contraband_count = sum(1 for card in cards if not GOODS[card].legal)
    parts = [f"{GOODS[key].emoji}×{count}" for key, count in legal.items()]
    if contraband_count:
        parts.append(f"🟥 контрабанда ×{contraband_count}")
    return ", ".join(parts) if parts else "порожньо"


def render_status(game: dict, players: list[dict], sheriff: dict | None) -> str:
    lines = [
        "🏰 <b>Стан партії</b>",
        f"Раунд: <b>{game['round_no']}</b>",
        f"Етап: <b>{PHASE_NAMES.get(game['phase'], game['phase'])}</b>",
    ]
    if sheriff:
        lines.append(f"👮 Шериф: <b>{sheriff['full_name']}</b>")
    lines.append("")
    for p in players:
        market = loads(p["market_json"])
        ready = "✅" if (p["bag_locked"] or p["resolved"]) else "⏳"
        lines.append(
            f"{ready} <b>{p['full_name']}</b> · 💰 {p['coins']}\n"
            f"   Прилавок: {public_stall_summary(market)}"
        )
    return "\n".join(lines)


def render_scoreboard(rows: list[dict]) -> str:
    lines = ["🏆 <b>ПІДСУМКИ НОТТІНГЕМА</b>", ""]
    medals = ["🥇", "🥈", "🥉"]
    for idx, row in enumerate(rows):
        s = row["score"]
        medal = medals[idx] if idx < len(medals) else f"{idx + 1}."
        lines.append(
            f"{medal} <b>{row['full_name']}</b> — <b>{s['total']}</b> очок\n"
            f"   💰 {s['coins']} + товари {s['goods']} + бонуси {s['bonus']}\n"
            f"   Дозволених: {s['legal_count']} · контрабанди: {s['contraband_count']}"
        )
    return "\n".join(lines)
