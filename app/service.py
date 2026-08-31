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
    SHERIFF_TURNS_PER_PLAYER,
    STARTING_COINS,
)
from .rules import final_scores, inspect_bag


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
            raise GameError("В этом чате уже есть активная партия.")
        game_id = await self.db.execute(
            "INSERT INTO games(chat_id, owner_id) VALUES(?, ?)",
            (chat_id, owner_id),
        )
        await self._add_player(game_id, owner_id)
        return await self.game(game_id)

    async def game(self, game_id: int) -> dict:
        game = await self.db.fetchone("SELECT * FROM games WHERE id=?", (game_id,))
        if not game:
            raise GameError("Партия не найдена.")
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
            raise GameError("Ты не участвуешь в этой партии.")
        return row

    async def _add_player(self, game_id: int, user_id: int) -> None:
        rows = await self.players(game_id)
        if any(p["user_id"] == user_id for p in rows):
            raise GameError("Ты уже в этой партии.")
        if len(rows) >= MAX_PLAYERS:
            raise GameError(f"Максимум игроков: {MAX_PLAYERS}.")
        await self.db.execute(
            "INSERT INTO game_players(game_id,user_id,seat,coins) VALUES(?,?,?,?)",
            (game_id, user_id, len(rows), STARTING_COINS),
        )

    async def join_game(self, chat_id: int, user_id: int) -> dict:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Сейчас нет открытого лобби.")
        await self._add_player(game["id"], user_id)
        return game

    async def leave_lobby(self, chat_id: int, user_id: int) -> None:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Выйти можно только из лобби.")
        if game["owner_id"] == user_id:
            raise GameError("Создатель не может выйти. Используй /cancelgame.")
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
            raise GameError("Активной партии нет.")
        if game["owner_id"] != user_id:
            raise GameError("Отменить партию может только создатель.")
        await self.db.execute(
            "UPDATE games SET status='cancelled', phase='cancelled', finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (game["id"],),
        )

    def _new_deck(self) -> list[str]:
        deck: list[str] = []
        for key, good in GOODS.items():
            deck.extend([key] * good.count)
        random.shuffle(deck)
        return deck

    async def start_game(self, chat_id: int, user_id: int) -> dict:
        game = await self.active_game(chat_id)
        if not game or game["status"] != "lobby":
            raise GameError("Открытого лобби нет.")
        if game["owner_id"] != user_id:
            raise GameError("Начать игру может только создатель.")
        players = await self.players(game["id"])
        if len(players) < MIN_PLAYERS:
            raise GameError(f"Нужно минимум {MIN_PLAYERS} игрока.")

        deck = self._new_deck()
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

        await self.db.execute(
            """
            UPDATE games SET status='playing', round_no=1, sheriff_seat=0,
                phase='packing', deck_json=?, discard_json='[]'
            WHERE id=?
            """,
            (dumps(deck), game["id"]),
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
            raise GameError("У тебя сейчас нет активной партии.")
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
            raise GameError("Шериф не найден.")
        return row

    async def merchant_rows(self, game_id: int) -> list[dict]:
        sheriff = await self.sheriff(game_id)
        return [p for p in await self.players(game_id) if p["user_id"] != sheriff["user_id"]]

    async def toggle_bag_good(self, user_id: int, good_key: str) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] != "packing":
            raise GameError("Сейчас мешки уже не собирают.")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Ты шериф этого раунда и мешок не собираешь.")

        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Мешок уже запечатан.")
        hand = loads(p["hand_json"])
        bag = loads(p["bag_json"])
        if good_key not in GOODS:
            raise GameError("Неизвестный товар.")

        hand_count = hand.count(good_key)
        bag_count = bag.count(good_key)
        if bag_count < hand_count and len(bag) < BAG_MAX:
            bag.append(good_key)
        elif bag_count:
            bag.remove(good_key)
        else:
            raise GameError("Этот товар нельзя добавить.")

        await self.db.execute(
            "UPDATE game_players SET bag_json=? WHERE game_id=? AND user_id=?",
            (dumps(bag), game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def clear_bag(self, user_id: int) -> dict:
        game = await self.game_for_user(user_id)
        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Мешок уже запечатан.")
        await self.db.execute(
            "UPDATE game_players SET bag_json='[]' WHERE game_id=? AND user_id=?",
            (game["id"], user_id),
        )
        return await self.player(game["id"], user_id)

    async def lock_bag(self, user_id: int) -> dict:
        game = await self.game_for_user(user_id)
        p = await self.player(game["id"], user_id)
        bag = loads(p["bag_json"])
        if not BAG_MIN <= len(bag) <= BAG_MAX:
            raise GameError(f"В мешке должно быть от {BAG_MIN} до {BAG_MAX} товаров.")
        return p

    async def declare(self, user_id: int, legal_good: str) -> tuple[dict, bool]:
        if legal_good not in LEGAL_GOODS:
            raise GameError("Объявить можно только легальный товар.")
        game = await self.game_for_user(user_id)
        if game["phase"] != "packing":
            raise GameError("Декларации уже закрыты.")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф не подаёт декларацию.")
        p = await self.player(game["id"], user_id)
        if p["bag_locked"]:
            raise GameError("Ты уже подал декларацию.")
        bag = loads(p["bag_json"])
        if not BAG_MIN <= len(bag) <= BAG_MAX:
            raise GameError(f"В мешке должно быть от {BAG_MIN} до {BAG_MAX} товаров.")

        hand = loads(p["hand_json"])
        for card in bag:
            hand.remove(card)
        await self.db.execute(
            """
            UPDATE game_players SET hand_json=?, declared_good=?, bag_locked=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(hand), legal_good, game["id"], user_id),
        )
        merchants = await self.merchant_rows(game["id"])
        all_ready = all(
            (m["user_id"] == user_id) or bool(m["bag_locked"])
            for m in merchants
        )
        if all_ready:
            await self.db.execute(
                "UPDATE games SET phase='inspection' WHERE id=?",
                (game["id"],),
            )
        return await self.player(game["id"], user_id), all_ready

    async def set_bribe(self, user_id: int, coins: int) -> dict:
        game = await self.game_for_user(user_id)
        if game["phase"] not in {"packing", "inspection"}:
            raise GameError("Сейчас взятку предложить нельзя.")
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] == user_id:
            raise GameError("Шериф сам себе взятку не даёт 😄")
        p = await self.player(game["id"], user_id)
        if not p["bag_locked"]:
            raise GameError("Сначала запечатай мешок и подай декларацию.")
        if coins < 0:
            raise GameError("Взятка не может быть отрицательной.")
        if coins > p["coins"]:
            raise GameError("Столько золота у тебя нет.")
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

    async def pass_merchant(self, sheriff_id: int, merchant_id: int) -> dict:
        game = await self.game_for_user(sheriff_id)
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] != sheriff_id:
            raise GameError("Решения принимает только текущий шериф.")
        if game["phase"] != "inspection":
            raise GameError("Проверка ещё не началась.")
        merchant = await self.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Этот торговец уже прошёл ворота.")
        if not merchant["bag_locked"]:
            raise GameError("Торговец ещё не подал декларацию.")

        bag = loads(merchant["bag_json"])
        market = loads(merchant["market_json"])
        market.extend(bag)
        bribe = await self.bribe(game["id"], merchant_id)
        paid = 0
        if bribe and bribe["status"] == "offered":
            paid = min(int(bribe["coins"]), int(merchant["coins"]))

        await self.db.execute(
            """
            UPDATE game_players SET market_json=?, coins=coins-?, resolved=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(market), paid, game["id"], merchant_id),
        )
        await self.db.execute(
            "UPDATE game_players SET coins=coins+? WHERE game_id=? AND user_id=?",
            (paid, game["id"], sheriff_id),
        )
        if bribe:
            await self.db.execute(
                "UPDATE bribes SET status='paid', coins=? WHERE game_id=? AND merchant_id=?",
                (paid, game["id"], merchant_id),
            )

        await self._draw_to_hand(game["id"], merchant_id)
        advanced = await self._advance_if_ready(game["id"])
        return {"bag": bag, "bribe": paid, "advanced": advanced}

    async def inspect_merchant(self, sheriff_id: int, merchant_id: int) -> dict:
        game = await self.game_for_user(sheriff_id)
        sheriff = await self.sheriff(game["id"])
        if sheriff["user_id"] != sheriff_id:
            raise GameError("Решения принимает только текущий шериф.")
        if game["phase"] != "inspection":
            raise GameError("Проверка ещё не началась.")
        merchant = await self.player(game["id"], merchant_id)
        if merchant["resolved"]:
            raise GameError("Этот торговец уже проверен.")

        bag = loads(merchant["bag_json"])
        result = inspect_bag(bag, merchant["declared_good"])
        market = loads(merchant["market_json"])
        market.extend(result.admitted)

        merchant_coins = int(merchant["coins"])
        sheriff_coins = int(sheriff["coins"])
        merchant_delta = 0
        sheriff_delta = 0
        if result.truthful:
            payment = min(result.sheriff_pays, sheriff_coins)
            merchant_delta += payment
            sheriff_delta -= payment
        else:
            payment = min(result.merchant_pays, merchant_coins)
            merchant_delta -= payment
            sheriff_delta += payment

        current_game = await self.game(game["id"])
        discard = loads(current_game["discard_json"])
        discard.extend(result.confiscated)

        await self.db.execute(
            """
            UPDATE game_players SET market_json=?, coins=coins+?, resolved=1
            WHERE game_id=? AND user_id=?
            """,
            (dumps(market), merchant_delta, game["id"], merchant_id),
        )
        await self.db.execute(
            "UPDATE game_players SET coins=coins+? WHERE game_id=? AND user_id=?",
            (sheriff_delta, game["id"], sheriff_id),
        )
        await self.db.execute(
            "UPDATE games SET discard_json=? WHERE id=?",
            (dumps(discard), game["id"]),
        )
        await self.db.execute(
            "UPDATE bribes SET status='rejected' WHERE game_id=? AND merchant_id=?",
            (game["id"], merchant_id),
        )

        await self._draw_to_hand(game["id"], merchant_id)
        advanced = await self._advance_if_ready(game["id"])
        return {
            "result": result,
            "bag": bag,
            "merchant_delta": merchant_delta,
            "sheriff_delta": sheriff_delta,
            "advanced": advanced,
        }

    async def _advance_if_ready(self, game_id: int) -> dict | None:
        game = await self.game(game_id)
        merchants = await self.merchant_rows(game_id)
        if not all(bool(m["resolved"]) for m in merchants):
            return None

        players = await self.players(game_id)
        max_rounds = len(players) * SHERIFF_TURNS_PER_PLAYER
        if int(game["round_no"]) >= max_rounds:
            await self.db.execute(
                "UPDATE games SET status='finished', phase='finished', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (game_id,),
            )
            return {"finished": True}

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
            "UPDATE games SET round_no=?, sheriff_seat=?, phase='packing' WHERE id=?",
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
        rows.sort(key=lambda r: (r["score"]["total"], r["score"]["coins"]), reverse=True)
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
            return "пусто"
        return ", ".join(f"{GOODS[key].emoji}×{count}" for key, count in counter.items())
