"""Supabase layer for profile, saved foods, and personalization cache."""

from __future__ import annotations

import os
import time

from typing import Any

from core.profile import Profile, profile_from_dict

LIST_TYPES = {"safe", "sometimes", "avoid"}
_SUPABASE_CLIENT: Any | None = None


def _client() -> Any:
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is None:
        from supabase import create_client

        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_ANON_KEY"]
        _SUPABASE_CLIENT = create_client(url, key)
    return _SUPABASE_CLIENT


def get_profile() -> Profile | None:
    response = _client().table("profile").select("*").eq("id", 1).execute()
    row = response.data[0] if response.data else None
    return profile_from_dict(row) if row else None


def save_profile(profile: Profile | dict) -> None:
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
    _client().table("profile").upsert(
        {
            "id": 1,
            "pcos_type": data["pcos_type"],
            "insulin_resistance": bool(data["insulin_resistance"]),
            "irregular_periods": bool(data["irregular_periods"]),
            "acne_or_hair": bool(data["acne_or_hair"]),
            "inflammation_bloating": bool(data["inflammation_bloating"]),
            "cravings": bool(data["cravings"]),
            "weight_loss_goal": bool(data["weight_loss_goal"]),
            "dietary_prefs": data.get("dietary_prefs") or "",
        },
        on_conflict="id",
    ).execute()


def save_food(barcode: str, product_name: str, score: float, verdict: str, list_type: str) -> None:
    if list_type not in LIST_TYPES:
        raise ValueError("list_type must be one of: safe, sometimes, avoid")
    _client().table("saved_foods").upsert(
        {
            "barcode": barcode,
            "product_name": product_name,
            "score": float(score),
            "verdict": verdict,
            "scanned_at": int(time.time()),
            "list_type": list_type,
        },
        on_conflict="barcode",
    ).execute()


def list_saved_foods() -> list[dict]:
    response = _client().table("saved_foods").select("*").order("scanned_at", desc=True).execute()
    return list(response.data or [])


def remove_saved_food(barcode: str) -> None:
    _client().table("saved_foods").delete().eq("barcode", barcode).execute()


def get_cached_personalization(barcode: str, profile_hash: str) -> dict | None:
    response = (
        _client()
        .table("personalization_cache")
        .select("payload")
        .eq("barcode", barcode)
        .eq("profile_hash", profile_hash)
        .execute()
    )
    row = response.data[0] if response.data else None
    return row["payload"] if row else None


def save_cached_personalization(barcode: str, profile_hash: str, payload: dict) -> None:
    _client().table("personalization_cache").upsert(
        {"barcode": barcode, "profile_hash": profile_hash, "payload": payload},
        on_conflict="barcode,profile_hash",
    ).execute()
