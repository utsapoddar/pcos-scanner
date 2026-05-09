"""User PCOS profile and stable hashing."""

from dataclasses import asdict, dataclass
import hashlib
import json


PCOS_TYPES = {"insulin_resistant", "inflammatory", "adrenal", "post_pill", "unknown"}
SYMPTOM_FIELDS = (
    "insulin_resistance",
    "irregular_periods",
    "acne_or_hair",
    "inflammation_bloating",
    "cravings",
    "weight_loss_goal",
)


@dataclass
class Profile:
    pcos_type: str = "unknown"
    insulin_resistance: bool = False
    irregular_periods: bool = False
    acne_or_hair: bool = False
    inflammation_bloating: bool = False
    cravings: bool = False
    weight_loss_goal: bool = False
    dietary_prefs: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


PROFILE_DEFAULT = Profile()


def profile_from_dict(data: dict | None) -> Profile | None:
    if data is None:
        return None
    values = PROFILE_DEFAULT.to_dict()
    values.update({key: data.get(key, values[key]) for key in values})
    if values["pcos_type"] not in PCOS_TYPES:
        values["pcos_type"] = "unknown"
    for field in SYMPTOM_FIELDS:
        values[field] = bool(values[field])
    values["dietary_prefs"] = values.get("dietary_prefs") or ""
    return Profile(**values)


def canonical_profile_json(profile: Profile | dict) -> str:
    data = profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def profile_hash(profile: Profile | dict) -> str:
    return hashlib.sha256(canonical_profile_json(profile).encode("utf-8")).hexdigest()
