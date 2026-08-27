"""NVIDIA-hosted personalization with SQLite caching and safe fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from core import db
from core.profile import profile_hash

# meta/llama-3.3-70b-instruct reached end of life on 2026-08-26 and now returns
# HTTP 410.
#
# Measured on this NVIDIA free tier (same prompt, 6 runs each):
#   gpt-oss-20b @ low reasoning -> 2-8s, 6/6 valid JSON
#   gemma-4-31b-it              -> 7-66s, then a hard timeout past 120s
# Consistency matters more than parameter count here: a slow model fails twice,
# once as a spinner and again as a fallback with no personalization at all.
MODEL = "openai/gpt-oss-20b"

# Required, not cosmetic. At default reasoning effort this model spends the
# entire token budget on hidden thinking and returns no JSON at all.
REASONING_EFFORT = "low"

# Measured completions run 415-600 characters; the previous 500-token cap
# truncated them mid-string and the JSON failed to parse.
MAX_TOKENS = 800
REQUEST_TIMEOUT = 30

_NO_KEY_NOTE = "Add an NVIDIA API key for profile-specific guidance."
_NO_PROFILE_NOTE = "Fill in your PCOS profile for guidance tailored to you."
_UNAVAILABLE_NOTE = "Personalized guidance is temporarily unavailable, so this is the nutrition score alone."

_KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "pcos_guidelines.md"
try:
    _KNOWLEDGE = _KB_PATH.read_text(encoding="utf-8")
except OSError:
    _KNOWLEDGE = ""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _fallback(deterministic_score: float, product: dict | None = None, note: str = _NO_KEY_NOTE) -> dict:
    name = (product or {}).get("name") or "This product"
    score = round(float(deterministic_score), 2)
    return {
        "adjusted_score": score,
        "verdict": _verdict(score),
        "reason": f"{name} was scored with the deterministic nutrition rules. {note}",
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
    if not profile:
        return _fallback(float(deterministic_score), product, _NO_PROFILE_NOTE)
    if not os.getenv("NVIDIA_API_KEY"):
        return _fallback(float(deterministic_score), product, _NO_KEY_NOTE)

    p_hash = profile_hash(profile)
    if barcode:
        # A paused or unreachable Supabase must not take scoring down with it.
        try:
            cached = db.get_cached_personalization(barcode, p_hash)
        except Exception as exc:
            print(f"Warning: personalization cache read failed: {exc}")
            cached = None
        if cached:
            return cached

    prompt = {
        "deterministic_score": deterministic_score,
        "breakdown": breakdown,
        "product": product,
        "profile": profile.to_dict() if hasattr(profile, "to_dict") else profile,
    }
    system_base = (
        "You personalize PCOS food-scanner results. Keep advice practical and concise."
    )
    json_instruction = (
        "Return only JSON with keys: adjusted_score, verdict, reason, serving, better_swap."
    )
    system = f"{system_base}\n\nReference (use when relevant):\n{_KNOWLEDGE}\n\n{json_instruction}"

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
            timeout=REQUEST_TIMEOUT,
            max_retries=1,
        )
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            max_tokens=MAX_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, sort_keys=True)},
            ],
        )
        text = resp.choices[0].message.content or ""
        payload = _normalize_payload(_extract_json(text), float(deterministic_score))
    except Exception as exc:
        # Never blame the API key here: a retired model, a timeout, or malformed
        # JSON all land in this branch and the key may be perfectly valid.
        print(f"Warning: personalization via {MODEL} failed: {type(exc).__name__}: {exc}")
        return _fallback(float(deterministic_score), product, _UNAVAILABLE_NOTE)

    if barcode:
        # A cache write failure must not discard guidance we already have.
        try:
            db.save_cached_personalization(barcode, p_hash, payload)
        except Exception as exc:
            print(f"Warning: personalization cache write failed: {exc}")
    return payload
