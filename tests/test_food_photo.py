import io
import sys
from types import SimpleNamespace

from PIL import Image

from core.food_photo import MODEL, _extract_json, aggregate_meal, estimate_meal_from_photo


def test_aggregate_meal_single_item():
    meal = aggregate_meal(
        [
            {
                "name": "Rice",
                "est_grams": 150,
                "nova_group": 1,
                "nutriments_100g": {
                    "energy-kcal_100g": 130,
                    "proteins_100g": 2.7,
                    "fiber_100g": 0.4,
                },
            }
        ]
    )

    assert meal["items"] == [
        {
            "name": "Rice",
            "grams": 150.0,
            "kcal": 195.0,
            "proteins_g": 4.05,
            "fiber_g": 0.6,
            "sugars_g": 0.0,
            "added_sugars_g": 0.0,
            "saturated_fat_g": 0.0,
            "sodium_g": 0.0,
        }
    ]
    assert meal["totals"]["kcal"] == 195.0
    assert meal["nutriments_100g"]["energy-kcal_100g"] == 130.0
    assert meal["nutriments_100g"]["proteins_100g"] == 2.7
    assert meal["nova_group"] == 1


def test_aggregate_meal_multi_item():
    meal = aggregate_meal(
        [
            {
                "name": "Rice",
                "est_grams": 100,
                "nova_group": 1,
                "nutriments_100g": {"energy-kcal_100g": 130, "proteins_100g": 2},
            },
            {
                "name": "Chicken",
                "est_grams": 100,
                "nova_group": 3,
                "nutriments_100g": {"energy-kcal_100g": 200, "proteins_100g": 30},
            },
        ]
    )

    assert meal["totals"]["kcal"] == 330.0
    assert meal["totals"]["proteins_g"] == 32.0
    assert meal["nutriments_100g"]["energy-kcal_100g"] == 165.0
    assert meal["nutriments_100g"]["proteins_100g"] == 16.0
    assert meal["nova_group"] == 3


def test_aggregate_meal_gram_override():
    meal = aggregate_meal(
        [
            {
                "name": "Chicken",
                "est_grams": 100,
                "nova_group": 1,
                "nutriments_100g": {"energy-kcal_100g": 200, "proteins_100g": 30},
            }
        ],
        grams_by_index={0: 50},
    )

    assert meal["items"][0]["grams"] == 50.0
    assert meal["items"][0]["kcal"] == 100.0
    assert meal["totals"]["proteins_g"] == 15.0
    assert meal["nutriments_100g"]["proteins_100g"] == 30.0


def test_aggregate_meal_missing_fields():
    meal = aggregate_meal([{"name": "Mystery", "est_grams": 100, "nutriments_100g": {}}])

    assert meal["items"][0]["kcal"] == 0.0
    assert meal["totals"]["kcal"] == 0.0
    assert meal["nutriments_100g"]["energy-kcal_100g"] == 0.0
    assert meal["nova_group"] is None


def test_aggregate_meal_all_none_nutriments_degrades_to_zero_totals():
    meal = aggregate_meal(
        [
            {
                "name": "Toast",
                "est_grams": 50,
                "nova_group": 3,
                "nutriments_100g": {
                    "proteins_100g": None,
                    "fiber_100g": None,
                    "sugars_100g": None,
                    "added-sugars_100g": None,
                    "saturated-fat_100g": None,
                    "sodium_100g": None,
                    "energy-kcal_100g": None,
                },
            }
        ]
    )

    assert meal["items"][0]["kcal"] == 0.0
    assert meal["totals"] == {
        "kcal": 0.0,
        "proteins_g": 0.0,
        "fiber_g": 0.0,
        "sugars_g": 0.0,
        "added_sugars_g": 0.0,
        "saturated_fat_g": 0.0,
        "sodium_g": 0.0,
    }
    assert meal["nutriments_100g"]["energy-kcal_100g"] == 0.0
    assert meal["nova_group"] == 3


def test_estimate_meal_from_photo_uses_vision_then_usda_lookup(monkeypatch):
    image = Image.new("RGB", (1, 1), color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    calls = []
    clients = []
    usda_calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='[{"name":"Rice","est_grams":120,"nova_group":1}]')
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            clients.append(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    class FakeResponse:
        def json(self):
            return {
                "foods": [
                    {
                        "foodNutrients": [
                            {"nutrientNumber": "203", "value": 2.7},
                            {"nutrientNumber": "307", "value": 1.0},
                            {"nutrientNumber": "208", "value": 130},
                        ]
                    }
                ]
            }

    def fake_get(url, params, timeout):
        usda_calls.append((url, params, timeout))
        return FakeResponse()

    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("USDA_API_KEY", "usda-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr("core.food_photo.requests.get", fake_get)

    assert estimate_meal_from_photo(buffer.getvalue()) == [
        {
            "name": "Rice",
            "est_grams": 120.0,
            "nova_group": 1,
            "nutriments_100g": {
                "proteins_100g": 2.7,
                "fiber_100g": None,
                "sugars_100g": None,
                "added-sugars_100g": None,
                "saturated-fat_100g": None,
                "sodium_100g": 0.001,
                "energy-kcal_100g": 130,
            },
        }
    ]
    assert [client["timeout"] for client in clients] == [30]
    assert [client["max_retries"] for client in clients] == [1]
    assert [call["model"] for call in calls] == [MODEL]
    assert calls[0]["max_tokens"] <= 400
    assert calls[0]["messages"][0]["content"] == "Return JSON only, no prose."
    assert calls[0]["messages"][1]["content"][0]["text"] == (
        'Identify each food and estimate the realistic grams of the visible portion. Return JSON array only, example: [{"name":"rice","est_grams":150,"nova_group":1}]'
    )
    assert usda_calls == [
        (
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            {
                "query": "Rice",
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
                "api_key": "usda-key",
            },
            10,
        )
    ]

def test_estimate_meal_from_photo_invalid_image_returns_none():
    assert estimate_meal_from_photo(b"not an image") is None


def test_extract_json_parses_fenced_array():
    assert _extract_json('```json\n[{"name":"Rice","est_grams":120}]\n```') == [
        {"name": "Rice", "est_grams": 120}
    ]
