from __future__ import annotations

from collections import Counter

from .db import loads
from .game_data import GOODS


def player_name(row: dict) -> str:
    return row["full_name"]


def render_hand(hand: list[str]) -> str:
    counter = Counter(hand)
    lines = ["📦 <b>Твоя рука</b>"]
    for key, count in counter.items():
        good = GOODS[key]
        kind = "легально" if good.legal else "КОНТРАБАНДА"
        lines.append(f"{good.emoji} {good.name} ×{count} · {kind} · цена {good.value}")
    return "\n".join(lines)


def render_lobby(players: list[dict], owner_id: int) -> str:
    lines = ["🏰 <b>Рынок Ноттингема — лобби</b>", ""]
    for i, p in enumerate(players, 1):
        crown = " 👑" if p["user_id"] == owner_id else ""
        lines.append(f"{i}. {p['full_name']}{crown}")
    lines += ["", "Команды: /join · /leave · /begin"]
    return "\n".join(lines)


def render_status(game: dict, players: list[dict], sheriff: dict | None) -> str:
    lines = [
        "🏰 <b>Статус партии</b>",
        f"Раунд: <b>{game['round_no']}</b>",
        f"Этап: <b>{game['phase']}</b>",
    ]
    if sheriff:
        lines.append(f"👮 Шериф: <b>{sheriff['full_name']}</b>")
    lines.append("")
    for p in players:
        market = loads(p["market_json"])
        ready = "✅" if p["bag_locked"] else "⏳"
        lines.append(f"{ready} {p['full_name']} · 💰 {p['coins']} · рынок {len(market)}")
    return "\n".join(lines)


def render_scoreboard(rows: list[dict]) -> str:
    lines = ["🏆 <b>ИТОГИ НОТТИНГЕМА</b>", ""]
    medals = ["🥇", "🥈", "🥉"]
    for idx, row in enumerate(rows):
        s = row["score"]
        medal = medals[idx] if idx < len(medals) else f"{idx+1}."
        lines.append(
            f"{medal} <b>{row['full_name']}</b> — <b>{s['total']}</b>\n"
            f"   💰{s['coins']} + товары {s['goods']} + бонусы {s['bonus']}"
        )
    return "\n".join(lines)
