"""SQLite layer for profile, saved foods, and personalization cache."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from core.profile import Profile, profile_from_dict

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pcos_scanner.db"
LIST_TYPES = {"safe", "sometimes", "avoid"}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own_conn = conn is None
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            pcos_type TEXT NOT NULL,
            insulin_resistance INTEGER NOT NULL,
            irregular_periods INTEGER NOT NULL,
            acne_or_hair INTEGER NOT NULL,
            inflammation_bloating INTEGER NOT NULL,
            cravings INTEGER NOT NULL,
            weight_loss_goal INTEGER NOT NULL,
            dietary_prefs TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_foods (
            barcode TEXT PRIMARY KEY,
            product_name TEXT,
            score REAL NOT NULL,
            verdict TEXT NOT NULL,
            scanned_at INTEGER NOT NULL,
            list_type TEXT NOT NULL CHECK (list_type IN ('safe', 'sometimes', 'avoid'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS personalization_cache (
            barcode TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (barcode, profile_hash)
        )
        """
    )
    conn.commit()
    if own_conn:
        conn.close()


def get_profile() -> Profile | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return profile_from_dict(dict(row)) if row else None


def save_profile(profile: Profile | dict) -> None:
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (
                id, pcos_type, insulin_resistance, irregular_periods, acne_or_hair,
                inflammation_bloating, cravings, weight_loss_goal, dietary_prefs
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                pcos_type = excluded.pcos_type,
                insulin_resistance = excluded.insulin_resistance,
                irregular_periods = excluded.irregular_periods,
                acne_or_hair = excluded.acne_or_hair,
                inflammation_bloating = excluded.inflammation_bloating,
                cravings = excluded.cravings,
                weight_loss_goal = excluded.weight_loss_goal,
                dietary_prefs = excluded.dietary_prefs
            """,
            (
                data["pcos_type"],
                int(bool(data["insulin_resistance"])),
                int(bool(data["irregular_periods"])),
                int(bool(data["acne_or_hair"])),
                int(bool(data["inflammation_bloating"])),
                int(bool(data["cravings"])),
                int(bool(data["weight_loss_goal"])),
                data.get("dietary_prefs") or "",
            ),
        )
        conn.commit()


def save_food(barcode: str, product_name: str, score: float, verdict: str, list_type: str) -> None:
    if list_type not in LIST_TYPES:
        raise ValueError("list_type must be one of: safe, sometimes, avoid")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO saved_foods (barcode, product_name, score, verdict, scanned_at, list_type)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(barcode) DO UPDATE SET
                product_name = excluded.product_name,
                score = excluded.score,
                verdict = excluded.verdict,
                scanned_at = excluded.scanned_at,
                list_type = excluded.list_type
            """,
            (barcode, product_name, float(score), verdict, int(time.time()), list_type),
        )
        conn.commit()


def list_saved_foods() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_foods ORDER BY list_type, scanned_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def remove_saved_food(barcode: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM saved_foods WHERE barcode = ?", (barcode,))
        conn.commit()


def get_cached_personalization(barcode: str, profile_hash: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT payload FROM personalization_cache WHERE barcode = ? AND profile_hash = ?",
            (barcode, profile_hash),
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def save_cached_personalization(barcode: str, profile_hash: str, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO personalization_cache (barcode, profile_hash, payload)
            VALUES (?, ?, ?)
            ON CONFLICT(barcode, profile_hash) DO UPDATE SET payload = excluded.payload
            """,
            (barcode, profile_hash, json.dumps(payload, sort_keys=True)),
        )
        conn.commit()
