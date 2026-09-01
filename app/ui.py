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
        "packing": "🛞",
        "declaration": "📜",
        "inspection": "🛡",
        "finished": "🏆",
        "cancelled": "🚫",
    }.get(phase, "🎲")


def render_group_home() -> str:
    return (
        "🐺 <b>БРАМА НОВІГРАДА</b>\n"
        "<i>Темне фентезі про купців, контрабанду, брехню та продажну варту</i>\n\n"
        "Ти ведеш свій товар до великого міста. Частина вантажу цілком законна, "
        "а частину краще не показувати варті. Домовляйся, блефуй і заробляй крони.\n\n"
        "👥 3–5 гравців · 🇺🇦 український інтерфейс"
    )


def render_lobby_table(players: list[dict], owner_id: int) -> str:
    lines = [
        "🏰 <b>БРАМА НОВІГРАДА · ЗБІР КУПЦІВ</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"👥 Купців: <b>{len(players)}/5</b>",
        "",
    ]
    for index, player in enumerate(players, 1):
        crown = " 👑" if player["user_id"] == owner_id else ""
        lines.append(f"{index}. <b>{esc(player['full_name'])}</b>{crown}")
    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Кожен гравець має один раз відкрити бота в ЛС і натиснути /start, "
        "щоб отримувати таємні товари, вантаж і приватні угоди.",
    ]
    return "\n".join(lines)


def _player_phase_icon(game: dict, player: dict, sheriff_id: int | None) -> str:
    if sheriff_id == player["user_id"]:
        return "🛡"
    phase = game["phase"]
    if phase == "market":
        return "✅" if player["resolved"] else "⏳"
    if phase == "packing":
        return "🔒" if player["bag_locked"] else "🛞"
    if phase == "declaration":
        return "✅" if player["declared_good"] else "📜"
    if phase == "inspection":
        return "✅" if player["resolved"] else "🐴"
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
        f"{_phase_icon(phase)} <b>БРАМА НОВІГРАДА · РАУНД {game['round_no']}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Етап: <b>{esc(PHASE_NAMES.get(phase, phase))}</b>",
    ]
    if sheriff:
        lines.append(f"🛡 Командир варти: <b>{esc(sheriff['full_name'])}</b>")
    if current_trader:
        lines.append(f"🛒 Зараз торгує: <b>{esc(current_trader['full_name'])}</b>")
    if current_declarer:
        lines.append(f"📜 Біля варти зараз: <b>{esc(current_declarer['full_name'])}</b>")
    lines += ["", "<b>Купці біля брами</b>"]

    for player in players:
        marker = _player_phase_icon(game, player, sheriff_id)
        market = loads(player["market_json"])
        lines.append(
            f"{marker} <b>{esc(player['full_name'])}</b> · 🪙 {player['coins']} крон\n"
            f"   🏪 Лавка: {public_stall_summary(market)}"
        )

    phase_hint = {
        "market": "Командир варти визначає першого купця, далі торг іде по колу.",
        "packing": "Купці таємно вантажать у повозки 1–5 товарів і запечатують вантаж.",
        "declaration": "Кожен називає точну кількість вантажу та один дозволений вид товару.",
        "inspection": "Час торгу з вартою: хабарі, угоди, блеф і ризик обшуку.",
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
    role = "🛡 <b>КОМАНДИР ВАРТИ</b>" if is_sheriff else "🐴 <b>КУПЕЦЬ</b>"
    market = loads(player["market_json"])
    hand = loads(player["hand_json"])
    bag = loads(player["bag_json"])
    phase = game["phase"]

    lines = [
        "🐺 <b>МІЙ ШЛЯХ ДО НОВІГРАДА</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Раунд <b>{game['round_no']}</b> · {_phase_icon(phase)} <b>{esc(PHASE_NAMES.get(phase, phase))}</b>",
        role,
        f"🪙 Крони: <b>{player['coins']}</b>",
        f"📦 Товари в руці: <b>{len(hand)}</b> карт",
        f"🏪 Лавка: {public_stall_summary(market)}",
    ]
    if not is_sheriff and phase in {"packing", "declaration", "inspection"}:
        bag_state = "🔒 запечатано" if player["bag_locked"] else "відкрито"
        lines.append(f"🛞 Вантаж: <b>{len(bag)}</b> карт · {bag_state}")
    if player.get("declared_good"):
        good = GOODS[player["declared_good"]]
        lines.append(f"📜 Заявлено варті: <b>{len(bag)} × {good.emoji} {good.name}</b>")

    lines += ["", "━━━━━━━━━━━━━━━━━━━━"]
    if phase == "market":
        if is_sheriff and game.get("market_start_seat") is None:
            lines.append("👉 <b>Твоя дія:</b> обери, хто з купців торгує першим.")
        elif is_sheriff:
            name = esc(current_trader["full_name"]) if current_trader else "—"
            lines.append(f"👀 Спостерігай за ринком. Зараз торгує: <b>{name}</b>.")
        elif current_trader and current_trader["user_id"] == player["user_id"]:
            lines.append("👉 <b>Твоя дія:</b> зараз твій хід у Торгівлі.")
        else:
            name = esc(current_trader["full_name"]) if current_trader else "варта ще визначає порядок"
            lines.append(f"⏳ Чекай своєї черги. Зараз: <b>{name}</b>.")
    elif phase == "packing":
        if is_sheriff:
            lines.append("👀 Купці зараз таємно готують вантаж. Ти чекаєш біля брами.")
        else:
            lines.append("👉 Завантаж у повозку 1–5 товарів і запечатай вантаж.")
    elif phase == "declaration":
        if is_sheriff:
            lines.append("👂 Слухай декларації купців. Вони можуть брехати про товар, але не про кількість.")
        elif current_declarer and current_declarer["user_id"] == player["user_id"]:
            lines.append("👉 <b>Твоя черга декларувати товар.</b>")
        else:
            name = esc(current_declarer["full_name"]) if current_declarer else "—"
            lines.append(f"📜 Чекаємо декларацію: <b>{name}</b>.")
    elif phase == "inspection":
        if is_sheriff:
            lines.append("👉 Вирішуй, кого пропустити, а чию повозку обшукати. Переглядай угоди й хабарі.")
        elif player["resolved"]:
            lines.append("✅ Твоя повозка вже пройшла браму. Можеш впливати на чужі справи через угоди.")
        else:
            lines.append("😏 Домовляйся з вартою: крони, товари, блеф і складні угоди дозволені.")
    return "\n".join(lines)


def render_hand_panel(hand: list[str]) -> str:
    counter = Counter(hand)
    lines = ["📦 <b>МОЇ ТОВАРИ</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for key, count in counter.items():
        good = GOODS[key]
        tag = "🟢 ДОЗВОЛЕНИЙ ТОВАР" if good.legal else "🟥 ЗАБОРОНЕНИЙ ТОВАР"
        lines.append(
            f"{good.emoji} <b>{good.name}</b> ×{count}\n"
            f"   {tag}\n"
            f"   💰 Вартість: <b>{good.value} крон</b> · ⚖️ Штраф: <b>{good.penalty} крон</b>"
        )
    return "\n".join(lines)
