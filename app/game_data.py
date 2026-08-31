from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Good:
    key: str
    name: str
    emoji: str
    legal: bool
    value: int
    penalty: int
    count: int
    king_bonus: int = 0
    queen_bonus: int = 0

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}"


GOODS: dict[str, Good] = {
    "apple": Good("apple", "Яблоки", "🍎", True, 2, 2, 48, 20, 10),
    "cheese": Good("cheese", "Сыр", "🧀", True, 3, 2, 36, 15, 10),
    "bread": Good("bread", "Хлеб", "🍞", True, 3, 2, 36, 15, 10),
    "chicken": Good("chicken", "Курица", "🍗", True, 4, 2, 24, 10, 5),
    "pepper": Good("pepper", "Перец", "🌶️", False, 6, 4, 22),
    "mead": Good("mead", "Мёд", "🍯", False, 7, 4, 21),
    "silk": Good("silk", "Шёлк", "🧵", False, 8, 4, 12),
    "crossbow": Good("crossbow", "Арбалет", "🏹", False, 9, 4, 5),
}

LEGAL_GOODS = tuple(key for key, good in GOODS.items() if good.legal)
HAND_SIZE = 6
BAG_MIN = 1
BAG_MAX = 5
STARTING_COINS = 50
MIN_PLAYERS = 3
MAX_PLAYERS = 8
SHERIFF_TURNS_PER_PLAYER = 2
