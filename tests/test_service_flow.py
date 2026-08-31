import asyncio
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.db import Database, loads
from app.game_data import deck_counts_for_players
from app.market_order import (
    choose_first_trader,
    current_market_trader,
    ensure_market_turn,
    market_order,
)
from app.service import GameError, GameService


def test_full_three_player_round_flow():
    asyncio.run(_full_three_player_round_flow())


async def _full_three_player_round_flow():
    with TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "nottingham.sqlite3")
        await db.init()
        service = GameService(db)

        users = [
            (101, "alice", "Аліса"),
            (102, "bob", "Богдан"),
            (103, "carol", "Катерина"),
        ]
        for user_id, username, full_name in users:
            await service.register_user(user_id, username, full_name)

        chat_id = -100777
        game = await service.create_game(chat_id, 101)
        await service.join_game(chat_id, 102)
        await service.join_game(chat_id, 103)
        game = await service.start_game(chat_id, 101)

        # 3-player setup uses the official reduced 156-card deck.
        players = await service.players(game["id"])
        all_cards = Counter(loads(game["deck_json"]))
        for player in players:
            hand = loads(player["hand_json"])
            assert len(hand) == 6
            all_cards.update(hand)
        assert all_cards == Counter(deck_counts_for_players(3))

        sheriff = await service.sheriff(game["id"])
        merchants = await service.merchant_rows(game["id"])
        assert len(merchants) == 2

        # Sheriff chooses the first Market trader; nobody can jump the queue.
        first = merchants[-1]
        await choose_first_trader(service, sheriff["user_id"], first["user_id"])
        order = await market_order(service, game["id"])
        assert order[0]["user_id"] == first["user_id"]
        assert sheriff["user_id"] not in [p["user_id"] for p in order]

        current = await current_market_trader(service, game["id"])
        assert current["user_id"] == first["user_id"]
        other = next(m for m in merchants if m["user_id"] != first["user_id"])
        with pytest.raises(GameError):
            await ensure_market_turn(service, other["user_id"])

        await ensure_market_turn(service, first["user_id"])
        _, ready = await service.confirm_market(first["user_id"])
        assert ready is False
        current = await current_market_trader(service, game["id"])
        assert current["user_id"] == other["user_id"]

        await ensure_market_turn(service, other["user_id"])
        _, ready = await service.confirm_market(other["user_id"])
        assert ready is True
        game = await service.game(game["id"])
        assert game["phase"] == "packing"

        # All merchants secretly put one card in a bag and lock it.
        merchants = await service.merchant_rows(game["id"])
        last_lock_result = None
        for merchant in merchants:
            fresh = await service.player(game["id"], merchant["user_id"])
            first_card = loads(fresh["hand_json"])[0]
            await service.toggle_bag_good(merchant["user_id"], first_card)
            last_lock_result = await service.lock_bag(merchant["user_id"])

        assert last_lock_result is not None
        _, all_locked, first_declarer = last_lock_result
        assert all_locked is True
        assert first_declarer is not None
        game = await service.game(game["id"])
        assert game["phase"] == "declaration"

        declaration_order = await service.declaration_order(game["id"])
        assert first_declarer["user_id"] == declaration_order[0]["user_id"]

        # Declarations are fixed and must happen clockwise from sheriff's left.
        wrong_first = declaration_order[1]
        with pytest.raises(GameError):
            await service.declare(wrong_first["user_id"], "apple")

        first_declared, all_declared, next_declarer = await service.declare(
            declaration_order[0]["user_id"], "apple"
        )
        assert first_declared["declared_good"] == "apple"
        assert all_declared is False
        assert next_declarer["user_id"] == declaration_order[1]["user_id"]
        with pytest.raises(GameError):
            await service.declare(declaration_order[0]["user_id"], "cheese")

        _, all_declared, next_declarer = await service.declare(
            declaration_order[1]["user_id"], "cheese"
        )
        assert all_declared is True
        assert next_declarer is None
        game = await service.game(game["id"])
        assert game["phase"] == "inspection"

        # An offered bribe is not automatically taken if sheriff passes for free.
        bribing_merchant = declaration_order[0]
        await service.set_bribe(bribing_merchant["user_id"], 5)
        sheriff_before = await service.player(game["id"], sheriff["user_id"])
        merchant_before = await service.player(game["id"], bribing_merchant["user_id"])
        result = await service.pass_merchant(
            sheriff["user_id"],
            bribing_merchant["user_id"],
            accept_bribe=False,
        )
        assert result["bribe"] == 0
        sheriff_after = await service.player(game["id"], sheriff["user_id"])
        merchant_after = await service.player(game["id"], bribing_merchant["user_id"])
        assert sheriff_after["coins"] == sheriff_before["coins"]
        assert merchant_after["coins"] == merchant_before["coins"]
        bribe = await service.bribe(game["id"], bribing_merchant["user_id"])
        assert bribe["status"] == "ignored"

        # Resolve the second bag: round advances, sheriff rotates left, everyone draws to 6.
        second = declaration_order[1]
        result = await service.pass_merchant(
            sheriff["user_id"], second["user_id"], accept_bribe=False
        )
        assert result["advanced"] == {
            "finished": False,
            "round_no": 2,
            "sheriff_seat": (int(sheriff["seat"]) + 1) % 3,
        }

        next_game = await service.game(game["id"])
        assert next_game["round_no"] == 2
        assert next_game["phase"] == "market"
        assert next_game["market_start_seat"] is None

        next_sheriff = await service.sheriff(game["id"])
        assert next_sheriff["user_id"] != sheriff["user_id"]
        for player in await service.players(game["id"]):
            assert len(loads(player["hand_json"])) == 6
            assert player["resolved"] == 0
            assert player["bag_locked"] == 0
            assert player["declared_good"] is None
