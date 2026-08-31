from __future__ import annotations

import random
from collections import Counter

from .db import Database, dumps, loads
from .game_data import (
    BAG_MAX,
    BAG_MIN,
    GOODS,
    HAND_SIZE,
    LEGAL_GOODS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    STARTING_COINS,
    deck_counts_for_players,
    sheriff_turns_for_players,
)
from .rules import final_scores, inspect_bag, settle_debt


class GameError(RuntimeError):
    pass


class GameService:
    def __init__(self, db: Database):
        self.db = db

    async def register_user(self, user_id: int, username: str | None, full_name: str) -> None:
        await self.db.execute(
            """
            INSERT INTO users(user_id, username, full_name)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name
            """,
            (user_id, username, full_name),
        )

    async def active_game(self, chat_id: int) -> dict | None:
        return await self.db.fetchone(
            "SELECT * FROM games WHERE chat_id=? AND status IN ('lobby','playing') ORDER BY id DESC LIMIT 1",
            (chat_id,),
        )

    async def create_game(self, chat_id: int, owner_id: int) -> dict:
        current = await self.active_game(chat_id)
        if current:
            raise GameError("У цьому чаті вже є активна партія.")
        game_id = await self.db.execute(
            "INSERT INTO games(chat_id, owner_id) VALUES(?, ?)",
            (chat_id, owner_id),
        )
        await self._add_player(game_id, owner_id)
        return await self.game(game_id)

    async def game(self, game_id: int) -> dict:
        game = await self.db.fetchone("SELECT * FROM games WHERE id=?", (game_id,))
        if not game:
            raise GameError("Партію не знайдено.")
        return game

    async def players(self, game_id: int) -> list[dict]:
        return await self.db.fetchall(
            """
            SELECT gp.*, u.username, u.full_name
            FROM game_players gp JOIN users u ON u.user_id=gp.user_id
            WHERE gp.game_id=? ORDER BY gp.seat
            """,
            (game_id,),
        )

    async def player(self, game_id: int, user_id: int) -> dict:
        row = await self.db.fetchone(
            """
            SELECT gp.*, u.username, u.full_name
            FROM game_players gp JOIN users u ON u.user_id=gp.user_id
            WHERE gp.game_id=? AND gp.user_id=?
            """,
            (game_id, user_id),
        )
        if not row:
            raise GameError("Ти не береш участі в цій партії.")
        return row

    async def _add_player(self, game_id: int, user_id: int) -> None:
        rows = await self.players(game_id)
        if any(p["user_id"] == user_id for p in rows):
            raise GameError("Ти вже в цій партії.")
        if len(rows) >= MAX_PLAYERS:
            raise GameError(f"Максимум гравців: {MAX_PLAYERS}.")
        await self.db.execute(
            "INSERT INTO game_players(game_id,user_id,seat,coins) VALUES(?,?,?,?)",
            (game_id, user_id, len(rows), STARTING_COINS),
        )

    async def join_game(self, chat_id: int, user_id: int) -> dict:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Зараз немає відкритого лобі.")
        await self._add_player(game["id"], user_id)
        return game

    async def leave_lobby(self, chat_id: int, user_id: int) -> None:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Вийти можна лише з лобі.")
        if game["owner_id"] == user_id:
            raise GameError("Творець партії не може вийти. Використай /cancelgame.")
        await self.db.execute(
            "DELETE FROM game_players WHERE game_id=? AND user_id=?",
            (game["id"], user_id),
        )
        rows = await self.players(game["id"])
        for seat, row in enumerate(rows):
            await self.db.execute(
                "UPDATE game_players SET seat=? WHERE game_id=? AND user_id=?",
                (seat, game["id"], row["user_id"]),
            )

    async def cancel_game(self, chat_id: int, user_id: int) -> None:
        game = await self.active_game(chat_id)
        if not game:
            raise GameError("Активної партії немає.")
        if game["owner_id"] != user_id:
            raise GameError("Скасувати партію може лише її творець.")
        await self.db.execute(
            "UPDATE games SET status='cancelled', phase='cancelled', finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (game["id"],),
        )

    def _new_deck(self, player_count: int) -> list[str]:
        deck: list[str] = []
        for key, count in deck_counts_for_players(player_count).items():
            deck.extend([key] * count)
        random.shuffle(deck)
        return deck

    async def start_game(self, chat_id: int, user_id: int) -> dict:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Відкритого лобі немає.")
        if game["owner_id"] != user_id:
            raise GameError("Почати гру може лише творець партії.")
        players = await self.players(game["id"])
        if len(players) < MIN_PLAYERS:
            raise GameError(f"Потрібно щонайменше {MIN_PLAYERS} гравці.")

        deck = self._new_deck(len(players))
        for p in players:
            hand = [deck.pop() for _ in range(HAND_SIZE)]
            await self.db.execute(
                """
                UPDATE game_players
                SET hand_json=?, market_json='[]', bag_json='[]', declared_good=NULL,
                    bag_locked=0, resolved=0, coins=?
                WHERE game_id=? AND user_id=?
                """,
                (dumps(hand), STARTING_COINS, game["id"], p["user_id"]),
            )

        first_sheriff = random.randrange(len(players))
        await self.db.execute(
            """
            UPDATE games SET status='playing', round_no=1, sheriff_seat=?,
                phase='market', deck_json=?, discard_json='[]'
            WHERE id=?
            """,
            (first_sheriff, dumps(deck), game["id"]),
        )
        return await self.game(game["id"])

    async def game_for_user(self, user_id: int) -> dict:
        row = await self.db.fetchone(
            """
            SELECT g.* FROM games g
            JOIN game_players gp ON gp.game_id=g.id
            WHERE gp.user_id=? AND g.status='playing'
            ORDER BY g.id DESC LIMIT 1
            """,
            (user_id,),
        )
        if not row:
            raise GameError("Зараз у тебе немає активної партії.")
        return row

    async def sheriff(self, game_id: int) -> dict:
        game = await self.game(game_id)
        row = await self.db.fetchone(
            """
            SELECT gp.*, u.username, u.full_name
            FROM game_players gp JOIN users u ON u.user_id=gp.user_id
            WHERE gp.game_id=? AND gp.seat=?
            """,
            (game_id, game["sheriff_seat"]),
        )
        if not row:
            raise GameError("Шерифа не знайдено.")
        return row

    async def merchant_rows(self, game_id: int) -> list[dict]:
        sheriff = await self.sheriff(game_id)
        return [p for p in await self.players(game_id) if p["user_id"] != sheriff["user_id"]]

    async def declaration_order(self, game_id: int) -> list[dict]:
        game = await self.game(game_id)
        players = await self.players(game_id)
        sheriff_seat = int(game["sheriff_seat"])
        by_seat = {int(p["seat"]): p for p in players}
        order: list[dict] = []
        for step in range(1, len(players)):
            seat = (sheriff_seat + step) % len(players)
            order.append(by_seat[seat])
        return order

    async def current_declarer(self, game_id: int) -> dict | None:
        for merchant in await self.declaration_order(game_id):
            if merchant["declared_good"] is None:
                return merchant
        return None

    async def toggle_market_good(self, user_id: int, good_key: str) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "market":
            raise GameError("Етап «Торгівля» вже завершено.")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф під час «Торгівлі» карти не міняє.")
        p = await self.player(game["id"], user_id)
        if p["resolved"]:
            raise GameError("Ти вже завершив торгівлю.")
        if good_key not in GOODS:
            raise GameError("Невідомий товар.")

        hand = loads(p["hand_json"])
        selected = loads(p["bag_json"])
        hand_count = hand.count(good_key)
        selected_count = selected.count(good_key)
        if selected_count < hand_count and len(selected) < 5:
            selected.append(good_key)
        elif selected_count:
            selected.remove(good_key)
        else:
            raise GameError("Цей товар не можна вибрати для скидання.")

        await self.db.execute(
            "UPDATE game_players SET bag_json=? WHERE game_id=? AND user_id=?",
            (dumps(selected), game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def clear_market_selection(self, user_id: int) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "market":
            raise GameError("Зараз не етап «Торгівля».")
        p = await self.player(game["id"], user_id)
        if p["resolved"]:
            raise GameError("Торгівлю вже завершено.")
        await self.db.execute(
            "UPDATE game_players SET bag_json='[]' WHERE game_id=? AND user_id=?",
            (game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def confirm_market(self, user_id: int) -> tuple[dict, bool]:
        game = await self.game_for_user(user_id)
        if game["phase"] != "market":
            raise GameError("Зараз не етап «Торгівля».")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф під час «Торгівлі» карти не міняє.")
        p = await self.player(game["id"], user_id)
        if p["resolved"]:
            raise GameError("Ти вже завершив торгівлю.")

        hand = loads(p["hand_json"])
        selected = loads(p["bag_json"])
        if len(selected) > 5:
            raise GameError("Під час «Торгівлі» можна скинути максимум 5 карток.")
        for card in selected:
            hand.remove(card)

        deck = loads(game["deck_json"])
        discard = loads(game["discard_json"])
        for _ in range(len(selected)):
            if not deck:
                if not discard:
                    raise GameError("У колоді тимчасово не залишилося карток.")
                random.shuffle(discard)
                deck = discard
                discard = []
            hand.append(deck.pop())

        await self.db.execute(
            "UPDATE game_players SET hand_json=?, resolved=1 WHERE game_id=? AND user_id=?",
            (dumps(hand), game["id"], user_id),
        )
        await self.db.execute(
            "UPDATE games SET deck_json=?, discard_json=? WHERE id=?",
            (dumps(deck), dumps(discard), game["id"]),
        )

        merchants = await self.merchant_rows(game["id"])
        all_ready = all((m["user_id"] == user_id) or bool(m["resolved"]) for m in merchants)
        if all_ready:
            # In 2nd edition the cards set aside during Market become the face-up
            # discard pile only after all Merchants have drawn replacements.
            discard = loads((await self.game(game["id"]))["discard_json"])
            refreshed = await self.merchant_rows(game["id"])
            for merchant in refreshed:
                discard.extend(loads(merchant["bag_json"]))
            await self.db.execute(
                "UPDATE games SET phase='packing', discard_json=? WHERE id=?",
                (dumps(discard), game["id"]),
            )
            await self.db.execute(
                "UPDATE game_players SET bag_json='[]', resolved=0 WHERE game_id=?",
                (game["id"],),
            )

        return await self.player(game["id"], user_id), all_ready

    async def toggle_bag_good(self, user_id: int, good_key: str) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "packing":
            raise GameError("Зараз не етап «Завантаження товарів».")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Ти шериф цього раунду й мішок не збираєш.")

        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Мішок уже запечатано.")
        hand = loads(p["hand_json"])
        bag = loads(p["bag_json"])
        if good_key not in GOODS:
            raise GameError("Невідомий товар.")

        hand_count = hand.count(good_key)
        bag_count = bag.count(good_key)
        if bag_count < hand_count and len(bag) < BAG_MAX:
            bag.append(good_key)
        elif bag_count:
            bag.remove(good_key)
        else:
            raise GameError("Цей товар не можна додати.")

        await self.db.execute(
            "UPDATE game_players SET bag_json=? WHERE game_id=? AND user_id=?",
            (dumps(bag), game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def clear_bag(self, user_id: int) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "packing":
            raise GameError("Зараз мішок змінювати не можна.")
        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Мішок уже запечатано.")
        await self.db.execute(
            "UPDATE game_players SET bag_json='[]' WHERE game_id=? AND user_id=?",
            (game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def lock_bag(self, user_id: int) -> tuple[dict, bool, dict | None]:
        game = await self.game_for_user(user_id)
        if game["phase"] != "packing":
            raise GameError("Зараз мішок запечатувати не можна.")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф цього раунду не готує мішок.")
        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Мішок уже запечатано.")
        bag = loads(p["bag_json"])
        if not BAG_MIN <= len(bag) <= BAG_MAX:
            raise GameError(f"У мішку має бути від {BAG_MIN} до {BAG_MAX} товарів.")

        hand = loads(p["hand_json"])
        for card in bag:
            hand.remove(card)
        await self.db.execute(
            """
            UPDATE game_players SET hand_json=?, bag_locked=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(hand), game["id"], user_id),
        )

        merchants = await self.merchant_rows(game["id"])
        refreshed = {m["user_id"]: m for m in await self.merchant_rows(game["id"])}
        all_locked = all(
            (m["user_id"] == user_id) or bool(refreshed[m["user_id"]]["bag_locked"])
            for m in merchants
        )
        first_declarer = None
        if all_locked:
            await self.db.execute(
                "UPDATE games SET phase='declaration' WHERE id=?",
                (game["id"],),
            )
            first_declarer = await self.current_declarer(game["id"])

        return await self.player(game["id"], user_id), all_locked, first_declarer

    async def declare(self, user_id: int, legal_good: str) -> tuple[dict, bool, dict | None]:
        if legal_good not in LEGAL_GOODS:
            raise GameError("Декларувати можна лише дозволений товар.")
        game = await self.game_for_user(user_id)
        if game["phase"] != "declaration":
            raise GameError("Зараз не етап «Декларування».")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф не декларує товари.")
        p = await self.player(game["id"], user_id)
        if not p["bag_locked"]:
            raise GameError("Спочатку запечатай мішок.")
        if p["declared_good"] is not None:
            raise GameError("Твою декларацію вже зафіксовано й змінити її не можна.")

        current = await self.current_declarer(game["id"])
        if not current or current["user_id"] != user_id:
            if current:
                raise GameError(f"Зараз декларує {current['full_name']}. Дочекайся своєї черги.")
            raise GameError("Декларування вже завершено.")

        await self.db.execute(
            """
            UPDATE game_players SET declared_good=?
            WHERE game_id=? AND user_id=?
            """,
            (legal_good, game["id"], user_id),
        )

        next_declarer = await self.current_declarer(game["id"])
        all_declared = next_declarer is None
        if all_declared:
            await self.db.execute(
                "UPDATE games SET phase='inspection' WHERE id=?",
                (game["id"],),
            )

        return await self.player(game["id"], user_id), all_declared, next_declarer

    async def set_bribe(self, user_id: int, coins: int) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "inspection":
            raise GameError("Хабар можна пропонувати під час етапу «Огляд».")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф сам собі хабар не дає 😄")
        p = await self.player(game["id"], user_id)
        if not p["bag_locked"]:
            raise GameError("Спочатку запечатай мішок і подай декларацію.")
        if coins < 0:
            raise GameError("Хабар не може бути від’ємним.")
        if coins > p["coins"]:
            raise GameError("У тебе немає стільки золота.")
        await self.db.execute(
            """
            INSERT INTO bribes(game_id,merchant_id,sheriff_id,coins,status)
            VALUES(?,?,?,?, 'offered')
            ON CONFLICT(game_id,merchant_id)
            DO UPDATE SET sheriff_id=excluded.sheriff_id, coins=excluded.coins, status='offered'
            """,
            (game["id"], user_id, sheriff["user_id"], coins),
        )
        return {"coins": coins, "sheriff": sheriff}

    async def bribe(self, game_id: int, merchant_id: int) -> dict | None:
        return await self.db.fetchone(
            "SELECT * FROM bribes WHERE game_id=? AND merchant_id=?",
            (game_id, merchant_id),
        )

    async def _draw_to_hand(self, game_id: int, user_id: int) -> None:
        game = await self.game(game_id)
        p = await self.player(game_id, user_id)
        hand = loads(p["hand_json"])
        deck = loads(game["deck_json"])
        discard = loads(game["discard_json"])

        while len(hand) < HAND_SIZE:
            if not deck:
                if not discard:
                    break
                random.shuffle(discard)
                deck = discard
                discard = []
            hand.append(deck.pop())

        await self.db.execute(
            "UPDATE game_players SET hand_json=? WHERE game_id=? AND user_id=?",
            (dumps(hand), game_id, user_id),
        )
        await self.db.execute(
            "UPDATE games SET deck_json=?, discard_json=? WHERE id=?",
            (dumps(deck), dumps(discard), game_id),
        )

    async def pass_merchant(
        self,
        sheriff_id: int,
        merchant_id: int,
        *,
        accept_bribe: bool = False,
    ) -> dict:
        game = await self.game_for_user(sheriff_id)
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] != sheriff_id:
            raise GameError("Рішення ухвалює лише поточний шериф.")
        if game["phase"] != "inspection":
            raise GameError("Огляд ще не почався.")
        merchant = await self.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Цей торговець уже пройшов ворота.")
        if merchant["declared_good"] is None:
            raise GameError("Торговець ще не подав декларацію.")

        bag = loads(merchant["bag_json"])
        merchant_market = loads(merchant["market_json"])
        merchant_market.extend(bag)
        merchant_coins = int(merchant["coins"])
        sheriff_coins = int(sheriff["coins"])

        bribe = await self.bribe(game["id"], merchant_id)
        paid = 0
        if accept_bribe:
            if not bribe or bribe["status"] != "offered" or int(bribe["coins"]) <= 0:
                raise GameError("Активного грошового хабара від цього торговця немає.")
            paid = int(bribe["coins"])
            if paid > merchant_coins:
                raise GameError("Торговець уже не має достатньо золота для цього хабара.")
            merchant_coins -= paid
            sheriff_coins += paid
            await self.db.execute(
                "UPDATE bribes SET status='paid' WHERE game_id=? AND merchant_id=?",
                (game["id"], merchant_id),
            )
        elif bribe and bribe["status"] == "offered":
            await self.db.execute(
                "UPDATE bribes SET status='ignored' WHERE game_id=? AND merchant_id=?",
                (game["id"], merchant_id),
            )

        await self.db.execute(
            """
            UPDATE game_players SET market_json=?, coins=?, resolved=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(merchant_market), merchant_coins, game["id"], merchant_id),
        )
        await self.db.execute(
            "UPDATE game_players SET coins=? WHERE game_id=? AND user_id=?",
            (sheriff_coins, game["id"], sheriff_id),
        )

        advanced = await self._advance_if_ready(game["id"])
        legal_cards = [card for card in bag if GOODS[card].legal]
        contraband_count = sum(1 for card in bag if not GOODS[card].legal)
        return {
            "bag": bag,
            "legal_cards": legal_cards,
            "contraband_count": contraband_count,
            "bribe": paid,
            "advanced": advanced,
        }

    async def inspect_merchant(self, sheriff_id: int, merchant_id: int) -> dict:
        game = await self.game_for_user(sheriff_id)
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] != sheriff_id:
            raise GameError("Рішення ухвалює лише поточний шериф.")
        if game["phase"] != "inspection":
            raise GameError("Огляд ще не почався.")
        merchant = await self.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Цього торговця вже оглянули.")

        bag = loads(merchant["bag_json"])
        result = inspect_bag(bag, merchant["declared_good"])
        merchant_market = loads(merchant["market_json"])
        merchant_market.extend(result.admitted)
        sheriff_market = loads(sheriff["market_json"])

        merchant_coins = int(merchant["coins"])
        sheriff_coins = int(sheriff["coins"])
        if result.truthful:
            settlement = settle_debt(
                sheriff_coins,
                sheriff_market,
                merchant_market,
                result.sheriff_pays,
            )
            sheriff_coins = settlement.payer_coins
            sheriff_market = list(settlement.payer_market)
            merchant_coins += settlement.cash_paid
            merchant_market = list(settlement.receiver_market)
            amount_due = result.sheriff_pays
        else:
            settlement = settle_debt(
                merchant_coins,
                merchant_market,
                sheriff_market,
                result.merchant_pays,
            )
            merchant_coins = settlement.payer_coins
            merchant_market = list(settlement.payer_market)
            sheriff_coins += settlement.cash_paid
            sheriff_market = list(settlement.receiver_market)
            amount_due = result.merchant_pays

        current_game = await self.game(game["id"])
        discard = loads(current_game["discard_json"])
        discard.extend(result.confiscated)

        await self.db.execute(
            """
            UPDATE game_players SET market_json=?, coins=?, resolved=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(merchant_market), merchant_coins, game["id"], merchant_id),
        )
        await self.db.execute(
            "UPDATE game_players SET market_json=?, coins=? WHERE game_id=? AND user_id=?",
            (dumps(sheriff_market), sheriff_coins, game["id"], sheriff_id),
        )
        await self.db.execute(
            "UPDATE games SET discard_json=? WHERE id=?",
            (dumps(discard), game["id"]),
        )
        await self.db.execute(
            "UPDATE bribes SET status='rejected' WHERE game_id=? AND merchant_id=?",
            (game["id"], merchant_id),
        )

        advanced = await self._advance_if_ready(game["id"])
        return {
            "result": result,
            "bag": bag,
            "settlement": settlement,
            "amount_due": amount_due,
            "advanced": advanced,
        }

    async def _advance_if_ready(self, game_id: int) -> dict | None:
        game = await self.game(game_id)
        merchants = await self.merchant_rows(game_id)
        if not all(bool(m["resolved"]) for m in merchants):
            return None

        players = await self.players(game_id)
        max_rounds = len(players) * sheriff_turns_for_players(len(players))
        if int(game["round_no"]) >= max_rounds:
            await self.db.execute(
                "UPDATE games SET status='finished', phase='finished', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (game_id,),
            )
            return {"finished": True}

        for p in players:
            await self._draw_to_hand(game_id, p["user_id"])

        next_seat = (int(game["sheriff_seat"]) + 1) % len(players)
        next_round = int(game["round_no"]) + 1
        await self.db.execute("DELETE FROM bribes WHERE game_id=?", (game_id,))
        await self.db.execute(
            """
            UPDATE game_players
            SET bag_json='[]', declared_good=NULL, bag_locked=0, resolved=0
            WHERE game_id=?
            """,
            (game_id,),
        )
        await self.db.execute(
            "UPDATE games SET round_no=?, sheriff_seat=?, phase='market' WHERE id=?",
            (next_round, next_seat, game_id),
        )
        return {"finished": False, "round_no": next_round, "sheriff_seat": next_seat}

    async def scoreboard(self, game_id: int) -> list[dict]:
        players = await self.players(game_id)
        payload = {
            p["user_id"]: {
                "coins": p["coins"],
                "market": loads(p["market_json"]),
            }
            for p in players
        }
        scores = final_scores(payload)
        rows = []
        for p in players:
            row = dict(p)
            row["score"] = scores[p["user_id"]]
            rows.append(row)
        rows.sort(
            key=lambda r: (
                r["score"]["total"],
                r["score"]["legal_count"],
                r["score"]["contraband_count"],
            ),
            reverse=True,
        )
        return rows

    async def status_payload(self, game_id: int) -> dict:
        game = await self.game(game_id)
        players = await self.players(game_id)
        sheriff = await self.sheriff(game_id) if game["status"] == "playing" else None
        return {"game": game, "players": players, "sheriff": sheriff}

    @staticmethod
    def bag_summary(bag: list[str]) -> str:
        counter = Counter(bag)
        if not counter:
            return "порожньо"
        return ", ".join(f"{GOODS[key].emoji}×{count}" for key, count in counter.items())
