from core.scoring import score_food


def test_high_protein_low_sugar_scores_at_least_seven():
    result = score_food(
        {
            "proteins_100g": 18,
            "fiber_100g": 3,
            "added-sugars_100g": 2,
            "saturated-fat_100g": 1,
            "sodium_100g": 0.1,
        },
        nova_group=1,
    )

    assert result["score"] >= 7
    assert 1 <= result["score"] <= 10


def test_sugary_cereal_scores_at_most_five():
    result = score_food(
        {
            "proteins_100g": 5,
            "fiber_100g": 2,
            "sugars_100g": 24,
            "saturated-fat_100g": 1,
            "sodium_100g": 0.3,
        },
        nova_group=4,
    )

    assert result["score"] <= 5
    assert 1 <= result["score"] <= 10


def test_ultra_processed_nova_four_penalty_applied():
    result = score_food({}, nova_group=4)

    assert {item["rule"]: item["delta"] for item in result["breakdown"]}["Ultra-processed (NOVA 4)"] == -1.5
    assert result["score"] == 3.5


def test_whole_food_nova_one_bonus_applied():
    result = score_food({}, nova_group=1)

    assert {item["rule"]: item["delta"] for item in result["breakdown"]}["Whole-food (NOVA 1)"] == 1.0
    assert result["score"] == 6.0


def test_missing_fields_do_not_crash_or_penalize():
    result = score_food({"proteins_100g": None}, nova_group=None)

    assert result == {"score": 5.0, "breakdown": []}


def test_outputs_are_clamped_to_one_and_ten():
    high = score_food(
        {
            "proteins_100g": 40,
            "fiber_100g": 20,
            "added-sugars_100g": 0,
            "saturated-fat_100g": 0,
            "sodium_100g": 0,
        },
        nova_group=1,
    )
    low = score_food(
        {
            "proteins_100g": 0,
            "fiber_100g": 0,
            "added-sugars_100g": 100,
            "saturated-fat_100g": 30,
            "sodium_100g": 2.0,
        },
        nova_group=4,
    )

    assert high["score"] == 8.5
    assert low["score"] == 1.0
    assert all(1 <= result["score"] <= 10 for result in (high, low))


def test_sodium_uses_openfoodfacts_grams_not_milligrams():
    low_sodium = score_food({"sodium_100g": 0.59}, nova_group=None)
    high_sodium = score_food({"sodium_100g": 0.6}, nova_group=None)

    assert low_sodium["score"] == 5.0
    assert high_sodium["score"] == 4.0
