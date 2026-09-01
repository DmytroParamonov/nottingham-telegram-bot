from __future__ import annotations

from collections import Counter

from .db import loads
from .game_data import GOODS
from .service import GameService


def _goods_dict(value: str | None) -> dict[str, int]:
    raw = loads(value, {})
    if not isinstance(raw, dict):
        return {}
    return {
        key: max(0, int(amount))
        for key, amount in raw.items()
        if key in GOODS and int(amount) > 0
    }


def _goods_phrase(goods: dict[str, int]) -> str:
    if not goods:
        return "—"
    return ", ".join(
        f"{GOODS[key].emoji} {GOODS[key].name} ×{count}"
        for key, count in goods.items()
    )


def _paid_goods_phrase(cards: list[str]) -> str:
    if not cards:
        return "—"
    counter = Counter(cards)
    return ", ".join(
        f"{GOODS[key].emoji} {GOODS[key].name} ×{count}"
        for key, count in counter.items()
    )


async def render_deal_fantasy(service: GameService, row: dict) -> str:
    proposer = await service.player(row["game_id"], row["proposer_id"])
    target = await service.player(row["game_id"], row["target_id"])
    action = (
        f"✅ пропустити повозку <b>{target['full_name']}</b> без обшуку"
        if row["action"] == "pass"
        else f"🔍 обшукати повозку <b>{target['full_name']}</b>"
    )

    lines = [
        f"🤝 <b>Угода біля брами #{row['id']}</b>",
        f"Пропонує купець: <b>{proposer['full_name']}</b>",
        f"Умова для варти: {action}",
        "",
        "<b>Що отримує варта:</b>",
        f"🪙 Крони: <b>{row['gold']}</b>",
        f"🏪 З лавки: {_goods_phrase(_goods_dict(row['stand_goods_json']))}",
        f"🛞 З вантажу: {_goods_phrase(_goods_dict(row['bag_goods_json']))}",
    ]
    if _goods_dict(row["bag_goods_json"]) or _goods_dict(row["stand_goods_json"]):
        lines.append("🎭 Обіцяними товарами можна блефувати — варта отримає лише те, що реально існує.")

    if row.get("followup_inspect_id") is not None:
        follow = await service.player(row["game_id"], row["followup_inspect_id"])
        lines += [
            "",
            f"📌 Командир варти також зобов'язується обшукати повозку <b>{follow['full_name']}</b> у цьому раунді.",
        ]

    if row.get("future_promise"):
        lines += [
            "",
            f"💭 Майбутня обіцянка: <i>{row['future_promise']}</i>",
            "⚠️ Обіцянка на майбутнє не є обов'язковою — слово купця дешевше за крону.",
        ]

    if not row["gold"] and not _goods_dict(row["stand_goods_json"]) and not _goods_dict(row["bag_goods_json"]):
        if not row.get("future_promise"):
            lines += ["", "Негайної плати немає — лише умова для рішення варти."]
    return "\n".join(lines)


def payment_result_text_fantasy(outcome: dict) -> str:
    parts = [f"🪙 {outcome['paid_gold']} крон"]
    if outcome["paid_stand"]:
        parts.append(f"🏪 {_paid_goods_phrase(outcome['paid_stand'])}")
    if outcome["paid_bag"]:
        parts.append(f"🛞 {_paid_goods_phrase(outcome['paid_bag'])}")
    missing = {**outcome["missing_stand"]}
    for key, amount in outcome["missing_bag"].items():
        missing[key] = missing.get(key, 0) + amount
    text = "Варта отримала: " + "; ".join(parts) + "."
    if missing:
        text += "\n🎭 Частина обіцяних товарів виявилась блефом: " + _goods_phrase(missing) + "."
    return text
