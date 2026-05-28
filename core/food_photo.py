"""Meal-photo estimation with NVIDIA vision models."""

from __future__ import annotations

import base64
import io
import json
import os

import requests
from dotenv import load_dotenv
from PIL import Image

MODEL = "meta/llama-3.2-11b-vision-instruct"
NUTRIMENT_KEYS = (
    "proteins_100g",
    "fiber_100g",
    "sugars_100g",
    "added-sugars_100g",
    "saturated-fat_100g",
    "sodium_100g",
    "energy-kcal_100g",
)
TOTAL_KEYS = (
    "kcal",
    "proteins_g",
    "fiber_g",
    "sugars_g",
    "added_sugars_g",
    "saturated_fat_g",
    "sodium_g",
)
TOTAL_KEY_BY_NUTRIMENT = {
    "proteins_100g": "proteins_g",
    "fiber_100g": "fiber_g",
    "sugars_100g": "sugars_g",
    "added-sugars_100g": "added_sugars_g",
    "saturated-fat_100g": "saturated_fat_g",
    "sodium_100g": "sodium_g",
    "energy-kcal_100g": "kcal",
}
USDA_NUTRIENT_KEYS = {
    "203": "proteins_100g",
    "291": "fiber_100g",
    "269": "sugars_100g",
    "539": "added-sugars_100g",
    "606": "saturated-fat_100g",
    "307": "sodium_100g",
    "208": "energy-kcal_100g",
}


def _empty_nutriments() -> dict:
    return {key: None for key in NUTRIMENT_KEYS}


def _image_mime(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    image.verify()
    fmt = (image.format or "jpeg").lower()
    if fmt == "jpg":
        fmt = "jpeg"
    return f"image/{fmt}"


def _extract_json(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON array found in model response")
    return json.loads(text[start : end + 1])


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_items(payload: list) -> list[dict]:
    items = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        nutriments = item.get("nutriments_100g") or {}
        items.append(
            {
                "name": item.get("name") or None,
                "est_grams": _number(item.get("est_grams")),
                "nova_group": item.get("nova_group"),
                "nutriments_100g": {key: nutriments.get(key) for key in NUTRIMENT_KEYS},
            }
        )
    return items


def fetch_nutriments_usda(name: str) -> dict:
    try:
        resp = requests.get(
            "https://api.nal.usda.gov/fdc/v1/foods/search",
            params={
                "query": name,
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
                "api_key": os.getenv("USDA_API_KEY") or "DEMO_KEY",
            },
            timeout=10,
        )
        food = (resp.json().get("foods") or [])[0]
    except Exception:
        return _empty_nutriments()

    nutriments = _empty_nutriments()
    for nutrient in food.get("foodNutrients") or []:
        key = USDA_NUTRIENT_KEYS.get(str(nutrient.get("nutrientNumber")))
        if not key:
            continue
        value = _number(nutrient.get("value"))
        nutriments[key] = value / 1000.0 if key == "sodium_100g" and value is not None else value
    return nutriments


def estimate_meal_from_photo(image_bytes: bytes) -> list[dict] | None:
    try:
        load_dotenv()
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            return None

        mime = _image_mime(image_bytes)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        from openai import OpenAI

        vision_client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
            timeout=30,
            max_retries=1,
        )
        resp = vision_client.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=400,
            messages=[
                {
                    "role": "system",
                    "content": "Return JSON only, no prose.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": 'Identify each food and estimate the realistic grams of the visible portion. Return JSON array only, example: [{"name":"rice","est_grams":150,"nova_group":1}]',
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        text = resp.choices[0].message.content or ""
        items = _normalize_items(_extract_json(text))
        if not items:
            return []
        for item in items:
            item["nutriments_100g"] = fetch_nutriments_usda(item.get("name") or "")
        return items
    except Exception:
        return None


def aggregate_meal(items, grams_by_index=None) -> dict:
    grams_by_index = grams_by_index or {}
    rows = []
    totals = {key: 0.0 for key in TOTAL_KEYS}
    nutriment_totals = {key: 0.0 for key in NUTRIMENT_KEYS}
    total_grams = 0.0
    nova_group = None

    for index, item in enumerate(items or []):
        nutriments = (item or {}).get("nutriments_100g") or {}
        grams = _number(grams_by_index.get(index))
        if grams is None:
            grams = _number((item or {}).get("est_grams")) or 0.0
        grams = max(0.0, grams)
        total_grams += grams

        row = {
            "name": (item or {}).get("name") or "Unknown item",
            "grams": round(grams, 2),
        }
        for nutriment_key, total_key in TOTAL_KEY_BY_NUTRIMENT.items():
            value = _number(nutriments.get(nutriment_key)) or 0.0
            amount = value * grams / 100.0
            row[total_key] = round(amount, 2)
            totals[total_key] += amount
            nutriment_totals[nutriment_key] += amount

        item_nova = _number((item or {}).get("nova_group"))
        if item_nova is not None:
            item_nova = int(item_nova)
            nova_group = item_nova if nova_group is None else max(nova_group, item_nova)
        rows.append(row)

    meal_nutriments = {}
    for key, amount in nutriment_totals.items():
        meal_nutriments[key] = round(amount / total_grams * 100.0, 2) if total_grams else None

    return {
        "items": rows,
        "totals": {key: round(value, 2) for key, value in totals.items()},
        "nutriments_100g": meal_nutriments,
        "nova_group": nova_group,
    }
