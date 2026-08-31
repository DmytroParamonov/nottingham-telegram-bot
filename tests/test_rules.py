from app.rules import final_scores, inspect_bag, majority_bonuses


def test_truthful_bag_makes_sheriff_pay():
    result = inspect_bag(["apple", "apple", "apple"], "apple")
    assert result.truthful is True
    assert result.sheriff_pays == 6
    assert result.confiscated == ()
    assert result.admitted == ("apple", "apple", "apple")


def test_liar_pays_only_for_misdeclared_goods():
    result = inspect_bag(["apple", "pepper", "silk"], "apple")
    assert result.truthful is False
    assert result.merchant_pays == 8
    assert result.admitted == ("apple",)
    assert result.confiscated == ("pepper", "silk")


def test_majority_bonus():
    markets = {
        1: ["apple"] * 5,
        2: ["apple"] * 3,
        3: ["apple"] * 1,
    }
    bonuses = majority_bonuses(markets)
    assert bonuses[1] == 20
    assert bonuses[2] == 10
    assert bonuses[3] == 0


def test_final_score_includes_coins_goods_and_bonus():
    scores = final_scores({
        1: {"coins": 50, "market": ["apple"] * 3},
        2: {"coins": 45, "market": ["apple"]},
    })
    assert scores[1]["goods"] == 6
    assert scores[1]["bonus"] == 20
    assert scores[1]["total"] == 76
