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


@dataclass(frozen=True, slots=True)
class DebtSettlement:
    cash_paid: int
    goods_paid: tuple[str, ...]
    forgiven: int
    payer_coins: int
    payer_market: tuple[str, ...]
    receiver_market: tuple[str, ...]


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


def _best_subset_at_least(cards: list[str], target: int) -> list[str]:
    """Pick a subset with the smallest value >= target; tie-break on fewer cards."""
    if target <= 0:
        return []
    states: dict[int, list[str]] = {0: []}
    for card in cards:
        value = GOODS[card].value
        for total, chosen in list(states.items())[::-1]:
            new_total = total + value
            candidate = chosen + [card]
            previous = states.get(new_total)
            if previous is None or len(candidate) < len(previous):
                states[new_total] = candidate
    candidates = [(total, chosen) for total, chosen in states.items() if total >= target]
    if not candidates:
        return list(cards)
    _, chosen = min(candidates, key=lambda item: (item[0], len(item[1])))
    return chosen


def settle_debt(
    payer_coins: int,
    payer_market: Iterable[str],
    receiver_market: Iterable[str],
    amount: int,
) -> DebtSettlement:
    """Settle a penalty using Gold, then Legal Goods, then Contraband.

    The physical game lets the payer choose the exact cards. For the bot we choose a
    minimum-overpayment subset automatically while preserving the official priority:
    Legal Goods before Contraband. Any debt left after all assets are exhausted is forgiven.
    """
    amount = max(0, int(amount))
    payer = list(payer_market)
    receiver = list(receiver_market)
    cash_paid = min(max(0, int(payer_coins)), amount)
    remaining = amount - cash_paid
    goods_paid: list[str] = []

    if remaining > 0:
        legal = [card for card in payer if GOODS[card].legal]
        legal_total = market_value(legal)
        if legal_total >= remaining:
            chosen = _best_subset_at_least(legal, remaining)
            goods_paid.extend(chosen)
            remaining = max(0, remaining - market_value(chosen))
        else:
            goods_paid.extend(legal)
            remaining -= legal_total
            contraband = [card for card in payer if not GOODS[card].legal]
            if contraband:
                chosen = _best_subset_at_least(contraband, remaining)
                goods_paid.extend(chosen)
                remaining = max(0, remaining - market_value(chosen))

    for card in goods_paid:
        payer.remove(card)
        receiver.append(card)

    return DebtSettlement(
        cash_paid=cash_paid,
        goods_paid=tuple(goods_paid),
        forgiven=max(0, remaining),
        payer_coins=max(0, int(payer_coins) - cash_paid),
        payer_market=tuple(payer),
        receiver_market=tuple(receiver),
    )


def majority_bonuses(markets: dict[int, Iterable[str]]) -> dict[int, int]:
    """Return official King/Queen bonuses, including tie splitting (rounded down)."""
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
        cards = list(data["market"])
        value = market_value(cards)
        legal_count = sum(1 for card in cards if GOODS[card].legal)
        contraband_count = len(cards) - legal_count
        total = int(data["coins"]) + value + bonuses[pid]
        result[pid] = {
            "coins": int(data["coins"]),
            "goods": value,
            "bonus": bonuses[pid],
            "legal_count": legal_count,
            "contraband_count": contraband_count,
            "total": total,
        }
    return result
