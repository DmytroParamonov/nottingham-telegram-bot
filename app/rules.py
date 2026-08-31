from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .game_data import GOODS, LEGAL_GOODS


@dataclass(frozen=True, slots=True)
class InspectionResult:
    truthful: bool
    merchant_pays: int
    sheriff_pays: int
    admitted: tuple[str, ...]
    confiscated: tuple[str, ...]


def inspect_bag(bag: Iterable[str], declared_good: str) -> InspectionResult:
    cards = tuple(bag)
    if declared_good not in LEGAL_GOODS:
        raise ValueError("Declaration must name a legal good")

    wrong = tuple(card for card in cards if card != declared_good)
    if not wrong:
        compensation = sum(GOODS[card].penalty for card in cards)
        return InspectionResult(
            truthful=True,
            merchant_pays=0,
            sheriff_pays=compensation,
            admitted=cards,
            confiscated=(),
        )

    fine = sum(GOODS[card].penalty for card in wrong)
    admitted = tuple(card for card in cards if card == declared_good)
    return InspectionResult(
        truthful=False,
        merchant_pays=fine,
        sheriff_pays=0,
        admitted=admitted,
        confiscated=wrong,
    )


def market_value(cards: Iterable[str]) -> int:
    return sum(GOODS[card].value for card in cards)


def goods_count(cards: Iterable[str]) -> Counter[str]:
    return Counter(cards)


def majority_bonuses(markets: dict[int, Iterable[str]]) -> dict[int, int]:
    """Return king/queen bonuses for legal goods.

    Ties split the combined occupied bonuses for that rank using integer division.
    This keeps scoring deterministic for a Telegram game without extra tie dialogs.
    """
    bonuses = {player_id: 0 for player_id in markets}
    counters = {pid: goods_count(cards) for pid, cards in markets.items()}

    for good_key in LEGAL_GOODS:
        good = GOODS[good_key]
        ranked = sorted(
            ((counter[good_key], pid) for pid, counter in counters.items()),
            reverse=True,
        )
        ranked = [(count, pid) for count, pid in ranked if count > 0]
        if not ranked:
            continue

        king_count = ranked[0][0]
        kings = [pid for count, pid in ranked if count == king_count]
        remaining = [(count, pid) for count, pid in ranked if count < king_count]

        if len(kings) > 1:
            shared = (good.king_bonus + good.queen_bonus) // len(kings)
            for pid in kings:
                bonuses[pid] += shared
            continue

        bonuses[kings[0]] += good.king_bonus
        if not remaining:
            continue

        queen_count = remaining[0][0]
        queens = [pid for count, pid in remaining if count == queen_count]
        shared = good.queen_bonus // len(queens)
        for pid in queens:
            bonuses[pid] += shared

    return bonuses


def final_scores(players: dict[int, dict]) -> dict[int, dict[str, int]]:
    markets = {pid: data["market"] for pid, data in players.items()}
    bonuses = majority_bonuses(markets)
    result: dict[int, dict[str, int]] = {}

    for pid, data in players.items():
        value = market_value(data["market"])
        total = int(data["coins"]) + value + bonuses[pid]
        result[pid] = {
            "coins": int(data["coins"]),
            "goods": value,
            "bonus": bonuses[pid],
            "total": total,
        }
    return result
