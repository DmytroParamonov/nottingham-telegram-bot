from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'lobby',
    round_no INTEGER NOT NULL DEFAULT 0,
    sheriff_seat INTEGER NOT NULL DEFAULT 0,
    market_start_seat INTEGER,
    phase TEXT NOT NULL DEFAULT 'lobby',
    deck_json TEXT NOT NULL DEFAULT '[]',
    discard_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_one_active_game_per_chat
ON games(chat_id)
WHERE status IN ('lobby', 'playing');

CREATE TABLE IF NOT EXISTS game_players (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL,
    coins INTEGER NOT NULL DEFAULT 50,
    hand_json TEXT NOT NULL DEFAULT '[]',
    market_json TEXT NOT NULL DEFAULT '[]',
    bag_json TEXT NOT NULL DEFAULT '[]',
    declared_good TEXT,
    bag_locked INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (game_id, user_id),
    UNIQUE (game_id, seat)
);

CREATE TABLE IF NOT EXISTS bribes (
    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    merchant_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    sheriff_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    coins INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'offered',
    PRIMARY KEY (game_id, merchant_id)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as db:
            await db.executescript(SCHEMA)

            # Невелика міграція для баз, створених ранніми версіями бота.
            cur = await db.execute("PRAGMA table_info(games)")
            columns = {row[1] for row in await cur.fetchall()}
            if "market_start_seat" not in columns:
                await db.execute("ALTER TABLE games ADD COLUMN market_start_seat INTEGER")

            await db.commit()

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        async with self.connection() as db:
            cur = await db.execute(query, params)
            await db.commit()
            return cur.lastrowid

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> dict | None:
        async with self.connection() as db:
            cur = await db.execute(query, params)
            row = await cur.fetchone()
            return dict(row) if row else None

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict]:
        async with self.connection() as db:
            cur = await db.execute(query, params)
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return [] if default is None else default
    return json.loads(value)
