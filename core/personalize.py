"""NVIDIA-hosted personalization with SQLite caching and safe fallback."""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from core import db
from core.profile import profile_hash

MODEL = "meta/llama-3.3-70b-instruct"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fallback(deterministic_score: float, product: dict | None = None) -> dict:
    name = (product or {}).get("name") or "This product"
    score = round(float(deterministic_score), 2)
    return {
        "adjusted_score": score,
        "verdict": _verdict(score),
        "reason": f"{name} was scored with the deterministic nutrition rules. Add an NVIDIA API key for profile-specific guidance.",
        "serving": "Use the package serving size when available, and pair higher-sugar foods with protein or fibre.",
        "better_swap": "Choose a less processed option with more protein or fibre and less added sugar.",
    }


def _verdict(score: float) -> str:
    if score >= 7:
        return "Good choice"
    if score >= 5:
        return "Okay sometimes"
    return "Limit or avoid"


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


def _normalize_payload(payload: dict, deterministic_score: float) -> dict:
    base = float(deterministic_score)
    adjusted = float(payload.get("adjusted_score", base))
    adjusted = round(_clamp(adjusted, base - 1.5, base + 1.5), 2)
    adjusted = round(_clamp(adjusted, 1.0, 10.0), 2)
    return {
        "adjusted_score": adjusted,
        "verdict": str(payload.get("verdict") or _verdict(adjusted)),
        "reason": str(payload.get("reason") or "Scored from the nutrition profile and your PCOS profile."),
        "serving": str(payload.get("serving") or "Use the listed serving size when available."),
        "better_swap": str(payload.get("better_swap") or "Look for more protein or fibre and less added sugar."),
    }


def personalize(deterministic_score, breakdown, product, profile) -> dict:
    """Return profile-aware score guidance, falling back gracefully offline."""
    load_dotenv()
    product = product or {}
    barcode = str(product.get("barcode") or "")
    if not profile or not os.getenv("NVIDIA_API_KEY"):
        return _fallback(float(deterministic_score), product)

    p_hash = profile_hash(profile)
    if barcode:
        cached = db.get_cached_personalization(barcode, p_hash)
        if cached:
            return cached

    prompt = {
        "deterministic_score": deterministic_score,
        "breakdown": breakdown,
        "product": product,
        "profile": profile.to_dict() if hasattr(profile, "to_dict") else profile,
    }
    system = (
        "You personalize PCOS food-scanner results. Return only JSON with keys: "
        "adjusted_score, verdict, reason, serving, better_swap. Keep advice practical and concise."
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
        )
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, sort_keys=True)},
            ],
        )
        text = resp.choices[0].message.content or ""
        payload = _normalize_payload(_extract_json(text), float(deterministic_score))
        if barcode:
            db.save_cached_personalization(barcode, p_hash, payload)
        return payload
    except Exception:
        return _fallback(float(deterministic_score), product)
