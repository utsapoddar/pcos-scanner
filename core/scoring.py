"""Deterministic PCOS food scoring."""


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _add(breakdown, score, rule, delta):
    breakdown.append({"rule": rule, "delta": delta})
    return score + delta


def score_food(nutriments_100g: dict, nova_group: int | None) -> dict:
    """Score a food from 1-10 using the plan rubric.

    Open Food Facts provides sodium_100g in grams; the rubric threshold is 600mg.
    Missing or non-numeric fields are ignored.
    """
    nutriments_100g = nutriments_100g or {}
    score = 5.0
    breakdown = []

    protein = _number(nutriments_100g.get("proteins_100g"))
    if protein is not None:
        if protein >= 15:
            score = _add(breakdown, score, "Protein >= 15g", 1.5)
        elif protein >= 8:
            score = _add(breakdown, score, "Protein >= 8g", 0.75)

    fiber = _number(nutriments_100g.get("fiber_100g"))
    if fiber is not None:
        if fiber >= 6:
            score = _add(breakdown, score, "Fibre >= 6g", 1.0)
        elif fiber >= 3:
            score = _add(breakdown, score, "Fibre >= 3g", 0.5)

    added_sugar = _number(nutriments_100g.get("added-sugars_100g"))
    if added_sugar is None:
        added_sugar = _number(nutriments_100g.get("sugars_100g"))
    if added_sugar is not None:
        if added_sugar >= 15:
            score = _add(breakdown, score, "Added sugar >= 15g", -2.0)
        elif added_sugar >= 8:
            score = _add(breakdown, score, "Added sugar >= 8g", -1.0)

    saturated_fat = _number(nutriments_100g.get("saturated-fat_100g"))
    if saturated_fat is not None and saturated_fat >= 5:
        score = _add(breakdown, score, "Saturated fat >= 5g", -1.0)

    sodium_g = _number(nutriments_100g.get("sodium_100g"))
    if sodium_g is not None and sodium_g * 1000 >= 600:
        score = _add(breakdown, score, "Sodium >= 600mg", -1.0)

    if nova_group == 4:
        score = _add(breakdown, score, "Ultra-processed (NOVA 4)", -1.5)
    elif nova_group == 1:
        score = _add(breakdown, score, "Whole-food (NOVA 1)", 1.0)

    score = max(1.0, min(10.0, score))
    return {"score": round(score, 2), "breakdown": breakdown}
