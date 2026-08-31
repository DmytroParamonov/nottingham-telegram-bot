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


# Базові товари Sheriff of Nottingham: 2nd Edition.
# Назви відповідають українській локалізації Games7Days.
GOODS: dict[str, Good] = {
    "apple": Good("apple", "Яблука", "🍎", True, 2, 2, 48, 20, 10),
    "cheese": Good("cheese", "Сир", "🧀", True, 3, 2, 36, 15, 10),
    "bread": Good("bread", "Хліб", "🍞", True, 3, 2, 36, 15, 10),
    "chicken": Good("chicken", "Курка", "🍗", True, 4, 2, 24, 10, 5),
    "pepper": Good("pepper", "Перець", "🌶️", False, 6, 4, 22),
    "mead": Good("mead", "Медовуха", "🍺", False, 7, 4, 21),
    "silk": Good("silk", "Шовк", "🧵", False, 8, 4, 12),
    "crossbow": Good("crossbow", "Арбалет", "🏹", False, 9, 4, 5),
}

LEGAL_GOODS = tuple(key for key, good in GOODS.items() if good.legal)
HAND_SIZE = 6
BAG_MIN = 1
BAG_MAX = 5
STARTING_COINS = 50
MIN_PLAYERS = 3

# Стандартний режим другої редакції: 3–5 гравців.
# Для 6 гравців офіційно використовується окреме правило двох заступників,
# тому його не можна коректно підміняти звичайним одним шерифом.
MAX_PLAYERS = 5

# У грі втрьох прибираються всі картки з позначкою 4+.
THREE_PLAYER_COUNTS: dict[str, int] = {
    "apple": 48,
    "cheese": 36,
    "bread": 0,
    "chicken": 24,
    "pepper": 18,
    "mead": 16,
    "silk": 9,
    "crossbow": 5,
}


def deck_counts_for_players(player_count: int) -> dict[str, int]:
    if player_count == 3:
        return dict(THREE_PLAYER_COUNTS)
    return {key: good.count for key, good in GOODS.items()}


def sheriff_turns_for_players(player_count: int) -> int:
    return 3 if player_count == 3 else 2
