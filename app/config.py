from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    database_path: Path


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and add the token.")

    db_path = Path(os.getenv("DATABASE_PATH", "data/nottingham.sqlite3"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return Settings(bot_token=token, database_path=db_path)
