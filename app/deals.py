from __future__ import annotations

from collections import Counter
from typing import Iterable

from .db import dumps, loads
from .game_data import GOODS
from .service import GameError, GameService


VALID_ACTIONS = {"pass", "inspect"}
MAX_PROMISE_LENGTH = 300
MAX_PROMISED_PER_GOOD = 9


def _goods_dict(value: str | None) -> dict[str, int]:
    raw = loads(value, {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for key, amount in raw.items():
        if key in GOODS:
            qty = max(0, int(amount))
            if qty:
                result[key] = qty
    return result


def _take_promised_goods(
    cards: Iterable[str],
    promised: dict[str, int],
) -> tuple[list[str], list[str], dict[str, int]]:
    remaining = list(cards)
    paid: list[str] = []
    missing: dict[str, int] = {}
    for key, requested in promised.items():
        available = remaining.count(key)
        taken = min(available, requested)
        for _ in range(taken):
            remaining.remove(key)
            paid.append(key)
        if taken < requested:
            missing[key] = requested - taken
    return remaining, paid, missing


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


async def _inspection_game(service: GameService, user_id: int) -> dict:
    game = await service.game_for_user(user_id)
    if game["phase"] != "inspection":
        raise GameError("Угоди укладаються лише під час етапу «Огляд».")
    return game


async def deal(service: GameService, deal_id: int) -> dict:
    row = await service.db.fetchone("SELECT * FROM deals WHERE id=?", (deal_id,))
    if not row:
        raise GameError("Угоду не знайдено.")
    return row


async def draft(service: GameService, proposer_id: int, *, create: bool = True) -> dict | None:
    game = await _inspection_game(service, proposer_id)
    sheriff = await service.sheriff(game["id"])
    if sheriff["user_id"] == proposer_id:
        raise GameError(
            "Шериф може торгуватися в чаті, а фінальну пропозицію фіксує той, хто платить хабар."
        )

    row = await service.db.fetchone(
        """
        SELECT * FROM deals
        WHERE game_id=? AND round_no=? AND proposer_id=? AND status='draft'
        ORDER BY id DESC LIMIT 1
        """,
        (game["id"], game["round_no"], proposer_id),
    )
    if row or not create:
        return row

    proposer = await service.player(game["id"], proposer_id)
    if proposer["resolved"]:
        merchants = [m for m in await service.merchant_rows(game["id"]) if not m["resolved"]]
        if not merchants:
            raise GameError("Усі мішки цього раунду вже вирішено.")
        target_id = merchants[0]["user_id"]
        action = "inspect"
    else:
        target_id = proposer_id
        action = "pass"

    deal_id = await service.db.execute(
        """
        INSERT INTO deals(
            game_id, round_no, proposer_id, sheriff_id, target_id, action,
            gold, stand_goods_json, bag_goods_json, status
        ) VALUES(?,?,?,?,?,?,0,'{}','{}','draft')
        """,
        (
            game["id"],
            game["round_no"],
            proposer_id,
            sheriff["user_id"],
            target_id,
            action,
        ),
    )
    return await deal(service, deal_id)


async def reset_draft(service: GameService, proposer_id: int) -> dict:
    game = await _inspection_game(service, proposer_id)
    await service.db.execute(
        """
        UPDATE deals SET status='expired', updated_at=CURRENT_TIMESTAMP
        WHERE game_id=? AND round_no=? AND proposer_id=? AND status='draft'
        """,
        (game["id"], game["round_no"], proposer_id),
    )
    created = await draft(service, proposer_id, create=True)
    assert created is not None
    return created


async def set_target_action(
    service: GameService,
    proposer_id: int,
    target_id: int,
    action: str,
) -> dict:
    if action not in VALID_ACTIONS:
        raise GameError("Невідома дія угоди.")
    game = await _inspection_game(service, proposer_id)
    target = await service.player(game["id"], target_id)
    sheriff = await service.sheriff(game["id"])
    if target_id == sheriff["user_id"]:
        raise GameError("Мішка шерифа в цьому раунді немає.")
    if target["resolved"]:
        raise GameError("Цей мішок уже вирішено.")

    row = await draft(service, proposer_id)
    assert row is not None
    bag_goods = _goods_dict(row["bag_goods_json"])
    # Товар із мішка можна автоматично розрахувати лише коли гравець
    # купує пропуск саме для свого мішка. Інші хабарі платяться золотом
    # або товарами з прилавка.
    if bag_goods and not (target_id == proposer_id and action == "pass"):
        bag_goods = {}

    followup = row.get("followup_inspect_id")
    if followup == target_id:
        followup = None

    await service.db.execute(
        """
        UPDATE deals
        SET target_id=?, action=?, bag_goods_json=?, followup_inspect_id=?,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (target_id, action, dumps(bag_goods), followup, row["id"]),
    )
    return await deal(service, row["id"])


async def adjust_gold(service: GameService, proposer_id: int, delta: int) -> dict:
    game = await _inspection_game(service, proposer_id)
    proposer = await service.player(game["id"], proposer_id)
    row = await draft(service, proposer_id)
    assert row is not None
    amount = max(0, min(int(proposer["coins"]), int(row["gold"]) + int(delta)))
    await service.db.execute(
        "UPDATE deals SET gold=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (amount, row["id"]),
    )
    return await deal(service, row["id"])


async def adjust_good(
    service: GameService,
    proposer_id: int,
    source: str,
    good_key: str,
    delta: int,
) -> dict:
    if good_key not in GOODS:
        raise GameError("Невідомий товар.")
    if source not in {"stand", "bag"}:
        raise GameError("Карти з руки не можна використовувати як хабар.")

    await _inspection_game(service, proposer_id)
    row = await draft(service, proposer_id)
    assert row is not None
    if source == "bag" and not (
        row["target_id"] == proposer_id and row["action"] == "pass"
    ):
        raise GameError(
            "Товари з мішка можна додати тут лише до угоди про пропуск власного мішка."
        )

    column = "stand_goods_json" if source == "stand" else "bag_goods_json"
    goods = _goods_dict(row[column])
    amount = max(0, min(MAX_PROMISED_PER_GOOD, goods.get(good_key, 0) + int(delta)))
    if amount:
        goods[good_key] = amount
    else:
        goods.pop(good_key, None)
    await service.db.execute(
        f"UPDATE deals SET {column}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (dumps(goods), row["id"]),
    )
    return await deal(service, row["id"])


async def set_followup_inspection(
    service: GameService,
    proposer_id: int,
    target_id: int | None,
) -> dict:
    game = await _inspection_game(service, proposer_id)
    row = await draft(service, proposer_id)
    assert row is not None
    if target_id is not None:
        sheriff = await service.sheriff(game["id"])
        target = await service.player(game["id"], target_id)
        if target_id == sheriff["user_id"]:
            raise GameError("Шерифа оглядати в його власний раунд не можна.")
        if target["resolved"]:
            raise GameError("Цей мішок уже вирішено.")
        if target_id == row["target_id"]:
            raise GameError("Цей мішок уже є головною умовою угоди.")
    await service.db.execute(
        "UPDATE deals SET followup_inspect_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (target_id, row["id"]),
    )
    return await deal(service, row["id"])


async def set_future_promise(service: GameService, proposer_id: int, text: str | None) -> dict:
    await _inspection_game(service, proposer_id)
    row = await draft(service, proposer_id)
    assert row is not None
    cleaned = (text or "").strip()
    if len(cleaned) > MAX_PROMISE_LENGTH:
        raise GameError(f"Обіцянка має бути коротшою за {MAX_PROMISE_LENGTH} символів.")
    await service.db.execute(
        "UPDATE deals SET future_promise=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (cleaned or None, row["id"]),
    )
    return await deal(service, row["id"])


async def offer_draft(service: GameService, proposer_id: int) -> dict:
    game = await _inspection_game(service, proposer_id)
    row = await draft(service, proposer_id)
    assert row is not None
    target = await service.player(game["id"], row["target_id"])
    if target["resolved"]:
        raise GameError("Цей мішок уже вирішено — пропозиція запізнилася.")
    proposer = await service.player(game["id"], proposer_id)
    if int(row["gold"]) > int(proposer["coins"]):
        raise GameError("У тебе вже немає стільки золота для цієї угоди.")
    if _goods_dict(row["bag_goods_json"]) and not (
        row["target_id"] == proposer_id and row["action"] == "pass"
    ):
        raise GameError("Ця угода некоректно використовує товари з мішка.")

    followup = row.get("followup_inspect_id")
    if followup is not None:
        follow = await service.player(game["id"], followup)
        if follow["resolved"]:
            raise GameError("Додатковий мішок уже вирішено.")

    # Нова формальна пропозиція від того самого гравця замінює його
    # попередню не прийняту пропозицію цього раунду.
    await service.db.execute(
        """
        UPDATE deals SET status='expired', updated_at=CURRENT_TIMESTAMP
        WHERE game_id=? AND round_no=? AND proposer_id=? AND status='offered'
        """,
        (game["id"], game["round_no"], proposer_id),
    )
    await service.db.execute(
        "UPDATE deals SET status='offered', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (row["id"],),
    )
    return await deal(service, row["id"])


async def incoming_offers(service: GameService, sheriff_id: int) -> list[dict]:
    game = await _inspection_game(service, sheriff_id)
    sheriff = await service.sheriff(game["id"])
    if sheriff["user_id"] != sheriff_id:
        raise GameError("Переглядати формальні пропозиції може поточний шериф.")
    rows = await service.db.fetchall(
        """
        SELECT * FROM deals
        WHERE game_id=? AND round_no=? AND sheriff_id=? AND status='offered'
        ORDER BY id
        """,
        (game["id"], game["round_no"], sheriff_id),
    )
    active: list[dict] = []
    for row in rows:
        target = await service.player(game["id"], row["target_id"])
        if target["resolved"]:
            await service.db.execute(
                "UPDATE deals SET status='expired', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (row["id"],),
            )
            continue
        active.append(row)
    return active


async def reject_deal(service: GameService, sheriff_id: int, deal_id: int) -> dict:
    game = await _inspection_game(service, sheriff_id)
    sheriff = await service.sheriff(game["id"])
    if sheriff["user_id"] != sheriff_id:
        raise GameError("Відхилити угоду може лише поточний шериф.")
    row = await deal(service, deal_id)
    if row["status"] != "offered" or row["game_id"] != game["id"]:
        raise GameError("Ця пропозиція вже неактивна.")
    await service.db.execute(
        "UPDATE deals SET status='rejected', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (deal_id,),
    )
    return await deal(service, deal_id)


async def _expire_offers_for_targets(
    service: GameService,
    game_id: int,
    round_no: int,
    target_ids: Iterable[int],
    *,
    except_deal_id: int,
) -> None:
    for target_id in set(target_ids):
        await service.db.execute(
            """
            UPDATE deals SET status='expired', updated_at=CURRENT_TIMESTAMP
            WHERE game_id=? AND round_no=? AND status='offered' AND id<>?
              AND (target_id=? OR followup_inspect_id=?)
            """,
            (game_id, round_no, except_deal_id, target_id, target_id),
        )


async def accept_deal(service: GameService, sheriff_id: int, deal_id: int) -> dict:
    game = await _inspection_game(service, sheriff_id)
    sheriff = await service.sheriff(game["id"])
    if sheriff["user_id"] != sheriff_id:
        raise GameError("Прийняти угоду може лише поточний шериф.")
    row = await deal(service, deal_id)
    if row["status"] != "offered":
        raise GameError("Ця пропозиція вже неактивна.")
    if row["game_id"] != game["id"] or int(row["round_no"]) != int(game["round_no"]):
        raise GameError("Ця пропозиція була зроблена в іншому раунді.")
    if row["sheriff_id"] != sheriff_id:
        raise GameError("Ця угода адресована іншому шерифу.")

    proposer = await service.player(game["id"], row["proposer_id"])
    target = await service.player(game["id"], row["target_id"])
    if target["resolved"]:
        raise GameError("Головний мішок цієї угоди вже вирішено.")
    if int(row["gold"]) > int(proposer["coins"]):
        raise GameError("Гравець уже витратив частину золота — ця пропозиція більше не може бути виконана.")

    followup_id = row.get("followup_inspect_id")
    if followup_id is not None:
        followup_target = await service.player(game["id"], followup_id)
        if followup_target["resolved"]:
            raise GameError("Додатковий мішок цієї угоди вже вирішено.")
        if followup_id == row["target_id"]:
            raise GameError("Некоректна подвійна умова на один мішок.")

    stand_promised = _goods_dict(row["stand_goods_json"])
    bag_promised = _goods_dict(row["bag_goods_json"])
    if bag_promised and not (
        row["proposer_id"] == row["target_id"] and row["action"] == "pass"
    ):
        raise GameError("Товари з мішка в цій угоді не можна коректно розрахувати.")

    proposer_market = loads(proposer["market_json"])
    sheriff_market = loads(sheriff["market_json"])
    remaining_market, paid_stand, missing_stand = _take_promised_goods(
        proposer_market, stand_promised
    )
    sheriff_market.extend(paid_stand)

    proposer_bag = loads(proposer["bag_json"])
    paid_bag: list[str] = []
    missing_bag: dict[str, int] = {}
    if bag_promised:
        proposer_bag, paid_bag, missing_bag = _take_promised_goods(
            proposer_bag, bag_promised
        )
        sheriff_market.extend(paid_bag)

    paid_gold = int(row["gold"])
    await service.db.execute(
        """
        UPDATE game_players
        SET coins=?, market_json=?, bag_json=?
        WHERE game_id=? AND user_id=?
        """,
        (
            int(proposer["coins"]) - paid_gold,
            dumps(remaining_market),
            dumps(proposer_bag),
            game["id"],
            proposer["user_id"],
        ),
    )
    await service.db.execute(
        """
        UPDATE game_players SET coins=?, market_json=?
        WHERE game_id=? AND user_id=?
        """,
        (
            int(sheriff["coins"]) + paid_gold,
            dumps(sheriff_market),
            game["id"],
            sheriff_id,
        ),
    )

    if row["action"] == "pass":
        primary = await service.pass_merchant(
            sheriff_id,
            row["target_id"],
            accept_bribe=False,
        )
    elif row["action"] == "inspect":
        primary = await service.inspect_merchant(sheriff_id, row["target_id"])
    else:
        raise GameError("Невідома дія угоди.")

    followup = None
    if followup_id is not None:
        refreshed = await service.player(game["id"], followup_id)
        if refreshed["resolved"]:
            raise GameError("Додатковий мішок несподівано вже вирішено.")
        # Поточна умова угоди є обов'язковою, тому огляд виконується
        # одразу після головної дії. Так шериф фізично не може порушити
        # домовленість наступним натисканням кнопки.
        followup = await service.inspect_merchant(sheriff_id, followup_id)

    await service.db.execute(
        "UPDATE deals SET status='fulfilled', updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (deal_id,),
    )
    resolved_ids = [row["target_id"]]
    if followup_id is not None:
        resolved_ids.append(followup_id)
    await _expire_offers_for_targets(
        service,
        game["id"],
        game["round_no"],
        resolved_ids,
        except_deal_id=deal_id,
    )

    advanced = (followup or primary).get("advanced")
    return {
        "deal": await deal(service, deal_id),
        "primary": primary,
        "followup": followup,
        "paid_gold": paid_gold,
        "paid_stand": paid_stand,
        "paid_bag": paid_bag,
        "missing_stand": missing_stand,
        "missing_bag": missing_bag,
        "advanced": advanced,
    }


async def render_deal(service: GameService, row: dict) -> str:
    proposer = await service.player(row["game_id"], row["proposer_id"])
    target = await service.player(row["game_id"], row["target_id"])
    action = (
        f"✅ пропустити <b>{target['full_name']}</b> без огляду"
        if row["action"] == "pass"
        else f"🔍 оглянути мішок <b>{target['full_name']}</b>"
    )

    lines = [
        f"🤝 <b>Угода #{row['id']}</b>",
        f"Пропонує: <b>{proposer['full_name']}</b>",
        f"Умова: {action}",
        "",
        "<b>Хабар:</b>",
        f"💰 Золото: <b>{row['gold']}</b>",
        f"🏪 З прилавка: {_goods_phrase(_goods_dict(row['stand_goods_json']))}",
        f"🎒 З мішка: {_goods_phrase(_goods_dict(row['bag_goods_json']))}",
    ]
    if _goods_dict(row["bag_goods_json"]) or _goods_dict(row["stand_goods_json"]):
        lines.append("🎭 Обіцяними товарами дозволено блефувати.")

    if row.get("followup_inspect_id") is not None:
        follow = await service.player(row["game_id"], row["followup_inspect_id"])
        lines += [
            "",
            f"📌 У цьому ж раунді шериф також зобов’язується оглянути <b>{follow['full_name']}</b>.",
        ]

    if row.get("future_promise"):
        lines += [
            "",
            f"💭 Майбутня обіцянка: <i>{row['future_promise']}</i>",
            "⚠️ Обіцянки на майбутній раунд правилами не є обов’язковими.",
        ]

    if not row["gold"] and not _goods_dict(row["stand_goods_json"]) and not _goods_dict(row["bag_goods_json"]):
        if not row.get("future_promise"):
            lines += ["", "Без негайної оплати — лише умови дій шерифа."]
    return "\n".join(lines)


def payment_result_text(outcome: dict) -> str:
    parts = [f"💰 {outcome['paid_gold']} золотих"]
    if outcome["paid_stand"]:
        parts.append(f"🏪 {_paid_goods_phrase(outcome['paid_stand'])}")
    if outcome["paid_bag"]:
        parts.append(f"🎒 {_paid_goods_phrase(outcome['paid_bag'])}")
    missing = {**outcome["missing_stand"]}
    for key, amount in outcome["missing_bag"].items():
        missing[key] = missing.get(key, 0) + amount
    text = "Сплачено: " + "; ".join(parts) + "."
    if missing:
        text += "\n🎭 Частина обіцяних товарів була блефом і не сплачена: " + _goods_phrase(missing) + "."
    return text
