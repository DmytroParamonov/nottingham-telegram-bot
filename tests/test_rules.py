from collections import Counter

from app.game_data import THREE_PLAYER_COUNTS, deck_counts_for_players, sheriff_turns_for_players
from app.rules import final_scores, inspect_bag, majority_bonuses, settle_debt


def test_truthful_bag_makes_sheriff_pay_for_every_card():
    result = inspect_bag(["apple", "apple", "apple"], "apple")
    assert result.truthful is True
    assert result.sheriff_pays == 6
    assert result.confiscated == ()
    assert result.admitted == ("apple", "apple", "apple")


def test_liar_pays_only_for_undeclared_goods():
    result = inspect_bag(["apple", "pepper", "silk"], "apple")
    assert result.truthful is False
    assert result.merchant_pays == 8
    assert result.admitted == ("apple",)
    assert result.confiscated == ("pepper", "silk")


def test_three_player_deck_removes_all_4_plus_cards():
    counts = deck_counts_for_players(3)
    assert counts == THREE_PLAYER_COUNTS
    assert counts["bread"] == 0
    assert counts["pepper"] == 18
    assert counts["mead"] == 16
    assert counts["silk"] == 9
    assert sum(counts.values()) == 156


def test_sheriff_turn_count_depends_on_player_count():
    assert sheriff_turns_for_players(3) == 3
    assert sheriff_turns_for_players(4) == 2
    assert sheriff_turns_for_players(5) == 2


def test_majority_bonus_normal_ranking():
    markets = {
        1: ["apple"] * 5,
        2: ["apple"] * 3,
        3: ["apple"],
    }
    bonuses = majority_bonuses(markets)
    assert bonuses[1] == 20
    assert bonuses[2] == 10
    assert bonuses[3] == 0


def test_tied_kings_split_king_and_queen_bonus_rounding_down():
    markets = {
        1: ["apple"] * 5,
        2: ["apple"] * 5,
        3: ["apple"] * 2,
    }
    bonuses = majority_bonuses(markets)
    assert bonuses[1] == 15
    assert bonuses[2] == 15
    assert bonuses[3] == 0


def test_debt_uses_gold_then_legal_goods_before_contraband():
    settlement = settle_debt(
        payer_coins=1,
        payer_market=["apple", "cheese", "pepper"],
        receiver_market=[],
        amount=6,
    )
    assert settlement.cash_paid == 1
    assert Counter(settlement.goods_paid) == Counter(["apple", "cheese"])
    assert settlement.forgiven == 0
    assert settlement.payer_market == ("pepper",)
    assert Counter(settlement.receiver_market) == Counter(["apple", "cheese"])


def test_debt_uses_contraband_only_after_all_legal_goods_are_insufficient():
    settlement = settle_debt(
        payer_coins=0,
        payer_market=["apple", "pepper"],
        receiver_market=[],
        amount=5,
    )
    assert settlement.goods_paid == ("apple", "pepper")
    assert settlement.payer_market == ()
    assert settlement.forgiven == 0


def test_unpayable_remainder_is_forgiven():
    settlement = settle_debt(
        payer_coins=1,
        payer_market=["apple"],
        receiver_market=[],
        amount=10,
    )
    assert settlement.cash_paid == 1
    assert settlement.goods_paid == ("apple",)
    assert settlement.forgiven == 7


def test_final_score_contains_official_tiebreak_counts():
    scores = final_scores({
        1: {"coins": 50, "market": ["apple", "apple", "pepper"]},
        2: {"coins": 45, "market": ["apple"]},
    })
    assert scores[1]["goods"] == 10
    assert scores[1]["bonus"] == 20
    assert scores[1]["legal_count"] == 2
    assert scores[1]["contraband_count"] == 1
    assert scores[1]["total"] == 80
