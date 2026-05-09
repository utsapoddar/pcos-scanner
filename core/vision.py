"""Nutrition-label extraction with NVIDIA vision models."""

from __future__ import annotations

import base64
import io
import json
import os

from dotenv import load_dotenv
from PIL import Image

MODEL = "meta/llama-3.2-90b-vision-instruct"
NUTRIMENT_KEYS = (
    "proteins_100g",
    "fiber_100g",
    "sugars_100g",
    "added-sugars_100g",
    "saturated-fat_100g",
    "sodium_100g",
    "energy-kcal_100g",
)


def _image_mime(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))
    image.verify()
    fmt = (image.format or "jpeg").lower()
    if fmt == "jpg":
        fmt = "jpeg"
    return f"image/{fmt}"


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


def _normalize_product(payload: dict) -> dict:
    nutriments = payload.get("nutriments_100g") or {}
    return {
        "barcode": "",
        "name": payload.get("name") or None,
        "brands": payload.get("brands") or None,
        "nova_group": payload.get("nova_group"),
        "serving_size": payload.get("serving_size") or None,
        "nutriments_100g": {key: nutriments.get(key) for key in NUTRIMENT_KEYS},
    }


def extract_product_from_label(image_bytes: bytes) -> dict | None:
    try:
        load_dotenv()
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            return None

        mime = _image_mime(image_bytes)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        instruction = """
Extract the product nutrition facts from this label image. Return JSON only using this schema:
{
  "name": "string or null",
  "brands": "string or null",
  "nova_group": "integer 1-4 or null (estimate from ingredients)",
  "serving_size": "string or null",
  "nutriments_100g": {
    "proteins_100g": "number or null (grams)",
    "fiber_100g": "number or null (grams)",
    "sugars_100g": "number or null (grams)",
    "added-sugars_100g": "number or null (grams)",
    "saturated-fat_100g": "number or null (grams)",
    "sodium_100g": "number or null (grams, NOT mg — convert if label is mg)",
    "energy-kcal_100g": "number or null (kcal)"
  }
}
If the label gives values per serving, convert them to per 100g when serving mass is available; otherwise use null.
""".strip()

        from openai import OpenAI

        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=700,
            messages=[
                {
                    "role": "system",
                    "content": "Extract nutrition facts from the food label image. Return JSON only, no prose.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        text = resp.choices[0].message.content or ""
        return _normalize_product(_extract_json(text))
    except Exception:
        return None
