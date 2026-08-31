import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.db import Database, dumps, loads
from app.deals import (
    accept_deal,
    adjust_gold,
    adjust_good,
    draft,
    offer_draft,
    set_followup_inspection,
    set_future_promise,
    set_target_action,
)
from app.service import GameError, GameService


def test_binding_deal_with_bluffed_goods_and_followup_inspection():
    asyncio.run(_binding_deal_with_bluffed_goods_and_followup_inspection())


async def _prepared_inspection_game():
    tmp = TemporaryDirectory()
    db = Database(Path(tmp.name) / "nottingham.sqlite3")
    await db.init()
    service = GameService(db)

    users = [
        (201, "one", "Олена"),
        (202, "two", "Тарас"),
        (203, "three", "Марко"),
    ]
    for uid, username, name in users:
        await service.register_user(uid, username, name)

    chat_id = -100991
    game = await service.create_game(chat_id, 201)
    await service.join_game(chat_id, 202)
    await service.join_game(chat_id, 203)
    game = await service.start_game(chat_id, 201)

    sheriff = await service.sheriff(game["id"])
    merchants = await service.merchant_rows(game["id"])
    first, second = merchants

    await service.db.execute(
        "UPDATE games SET phase='inspection' WHERE id=?",
        (game["id"],),
    )
    await service.db.execute(
        """
        UPDATE game_players
        SET coins=50, market_json=?, bag_json=?, bag_locked=1,
            declared_good='apple', resolved=0
        WHERE game_id=? AND user_id=?
        """,
        (dumps(["apple"]), dumps(["apple", "pepper"]), game["id"], first["user_id"]),
    )
    await service.db.execute(
        """
        UPDATE game_players
        SET coins=50, market_json='[]', bag_json=?, bag_locked=1,
            declared_good='cheese', resolved=0
        WHERE game_id=? AND user_id=?
        """,
        (dumps(["cheese"]), game["id"], second["user_id"]),
    )
    await service.db.execute(
        """
        UPDATE game_players SET coins=50, market_json='[]'
        WHERE game_id=? AND user_id=?
        """,
        (game["id"], sheriff["user_id"]),
    )
    return tmp, service, game, sheriff, first, second


async def _binding_deal_with_bluffed_goods_and_followup_inspection():
    tmp, service, game, sheriff, first, second = await _prepared_inspection_game()
    try:
        row = await draft(service, first["user_id"])
        assert row["target_id"] == first["user_id"]
        assert row["action"] == "pass"

        await adjust_gold(service, first["user_id"], 8)
        # Promise 2 Apples from the stand although only 1 exists: legal bluff.
        await adjust_good(service, first["user_id"], "stand", "apple", 1)
        await adjust_good(service, first["user_id"], "stand", "apple", 1)
        # Promise the Pepper that is actually in the bag.
        await adjust_good(service, first["user_id"], "bag", "pepper", 1)
        await set_followup_inspection(service, first["user_id"], second["user_id"])
        await set_future_promise(
            service,
            first["user_id"],
            "Коли стану шерифом наступного разу, не оглядатиму твій мішок",
        )
        offered = await offer_draft(service, first["user_id"])
        assert offered["status"] == "offered"

        outcome = await accept_deal(service, sheriff["user_id"], offered["id"])
        assert outcome["deal"]["status"] == "fulfilled"
        assert outcome["paid_gold"] == 8
        assert outcome["paid_stand"] == ["apple"]
        assert outcome["missing_stand"] == {"apple": 1}
        assert outcome["paid_bag"] == ["pepper"]
        assert outcome["missing_bag"] == {}
        assert outcome["followup"] is not None
        assert outcome["primary"]["advanced"] is None
        assert outcome["advanced"] is not None

        # First merchant passed; promised Pepper left the bag for Sheriff's stand.
        # Because the follow-up inspection resolves the final bag, the game then
        # starts round 2 and resets per-round resolved flags back to zero.
        first_after = await service.player(game["id"], first["user_id"])
        assert first_after["resolved"] == 0
        assert first_after["coins"] == 42
        assert loads(first_after["market_json"]) == ["apple"]

        # Follow-up inspection is binding and executed immediately. The second
        # merchant was truthful, so Sheriff pays the Cheese penalty (2 Gold).
        second_after = await service.player(game["id"], second["user_id"])
        assert second_after["resolved"] == 0
        assert second_after["coins"] == 52

        sheriff_after = await service.player(game["id"], sheriff["user_id"])
        assert sheriff_after["coins"] == 56
        sheriff_market = loads(sheriff_after["market_json"])
        assert "apple" in sheriff_market
        assert "pepper" in sheriff_market

        # Resolving both merchants advances the round; future promise was merely
        # recorded and did not create any forced future state.
        next_game = await service.game(game["id"])
        assert next_game["round_no"] == 2
        assert next_game["phase"] == "market"
        assert outcome["deal"]["future_promise"]
    finally:
        tmp.cleanup()


def test_hand_cards_cannot_be_added_to_deal():
    asyncio.run(_hand_cards_cannot_be_added_to_deal())


async def _hand_cards_cannot_be_added_to_deal():
    tmp, service, _, _, first, _ = await _prepared_inspection_game()
    try:
        await draft(service, first["user_id"])
        with pytest.raises(GameError, match="руки"):
            await adjust_good(service, first["user_id"], "hand", "apple", 1)
    finally:
        tmp.cleanup()


def test_bag_goods_only_for_own_pass_deal():
    asyncio.run(_bag_goods_only_for_own_pass_deal())


async def _bag_goods_only_for_own_pass_deal():
    tmp, service, _, _, first, second = await _prepared_inspection_game()
    try:
        await draft(service, first["user_id"])
        await set_target_action(service, first["user_id"], second["user_id"], "inspect")
        with pytest.raises(GameError, match="мішка"):
            await adjust_good(service, first["user_id"], "bag", "pepper", 1)
    finally:
        tmp.cleanup()


def test_gold_offer_never_exceeds_actual_gold():
    asyncio.run(_gold_offer_never_exceeds_actual_gold())


async def _gold_offer_never_exceeds_actual_gold():
    tmp, service, _, _, first, _ = await _prepared_inspection_game()
    try:
        row = await draft(service, first["user_id"])
        assert row["gold"] == 0
        row = await adjust_gold(service, first["user_id"], 999)
        assert row["gold"] == 50
    finally:
        tmp.cleanup()
