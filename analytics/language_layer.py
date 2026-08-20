"""Fail-closed access to the portable AI Macro language layer."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from analytics.read_evidence import DOMAIN_ORDER

LAYER_PATH = Path(__file__).resolve().parents[1] / "language" / "AI_MACRO_LANGUAGE_LAYER_v1.0.json"
EDITORIAL_CONSTITUTION_PATH = (
    Path(__file__).resolve().parents[1]
    / "language"
    / "AI_MACRO_EDITORIAL_CONSTITUTION_v1.0.json"
)
LAYER_SCHEMA_VERSION = "1.0"
EDITORIAL_CONSTITUTION_SCHEMA_VERSION = "1.0"


class LanguageLayerError(RuntimeError):
    """Raised before generation when the compiled editorial layer is invalid."""


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_language_layer(layer: Any) -> dict[str, Any]:
    if not isinstance(layer, dict):
        raise LanguageLayerError("Compiled language layer must be a JSON object.")
    if str(layer.get("schema_version")) != LAYER_SCHEMA_VERSION:
        raise LanguageLayerError("Compiled language layer schema is incompatible.")
    payload = layer.get("payload")
    expected = str(layer.get("payload_sha256") or "")
    actual = hashlib.sha256(_stable_json(payload)).hexdigest()
    if not expected or actual != expected:
        raise LanguageLayerError("Compiled language layer payload checksum failed.")
    profiles = (payload or {}).get("profiles")
    if not isinstance(profiles, dict) or tuple(profiles) != tuple(DOMAIN_ORDER):
        raise LanguageLayerError("Compiled language layer does not contain the 11-domain profile set.")
    for domain, profile in profiles.items():
        for field in ("objective", "relationship_chain", "preferred_architectures", "anti_patterns", "evidence_rules"):
            if not profile.get(field):
                raise LanguageLayerError(f"Compiled language layer profile {domain!r} lacks {field!r}.")
    for field in ("runtime_contract", "architecture_library", "read_set_composition", "sentence_craft", "uncertainty_calibration"):
        if not (payload or {}).get(field):
            raise LanguageLayerError(f"Compiled language layer lacks {field!r}.")
    if not layer.get("layer_version"):
        raise LanguageLayerError("Compiled language layer has no version.")
    return layer


@lru_cache(maxsize=1)
def load_language_layer(path: str | Path = LAYER_PATH) -> dict[str, Any]:
    candidate = Path(path)
    try:
        layer = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LanguageLayerError(f"Compiled language layer cannot be loaded: {exc}") from exc
    return validate_language_layer(layer)


def language_layer_identity() -> dict[str, str]:
    layer = load_language_layer()
    return {
        "schema_version": str(layer["schema_version"]),
        "layer_version": str(layer["layer_version"]),
        "payload_sha256": str(layer["payload_sha256"]),
    }


@lru_cache(maxsize=1)
def load_editorial_constitution(
    path: str | Path = EDITORIAL_CONSTITUTION_PATH,
) -> dict[str, Any]:
    """Load the compact runtime constitution derived from the audited layer."""
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LanguageLayerError(f"Editorial constitution cannot be loaded: {exc}") from exc
    if not isinstance(payload, dict):
        raise LanguageLayerError("Editorial constitution must be a JSON object.")
    if str(payload.get("schema_version") or "") != EDITORIAL_CONSTITUTION_SCHEMA_VERSION:
        raise LanguageLayerError("Editorial constitution schema is incompatible.")
    for field in (
        "constitution_version",
        "evidence_contract",
        "editorial_contract",
        "incremental_contract",
        "systems_reasoning",
        "prose",
    ):
        if not payload.get(field):
            raise LanguageLayerError(f"Editorial constitution lacks {field!r}.")
    return payload


def editorial_constitution_identity() -> dict[str, str]:
    constitution = load_editorial_constitution()
    return {
        "schema_version": str(constitution["schema_version"]),
        "constitution_version": str(constitution["constitution_version"]),
        "sha256": hashlib.sha256(_stable_json(constitution)).hexdigest(),
        "source_language_layer_sha256": language_layer_identity()["payload_sha256"],
    }


def editorial_constitution_payload() -> dict[str, Any]:
    """Return only the compact production guidance sent to the single call."""
    constitution = load_editorial_constitution()
    identity = editorial_constitution_identity()
    return {
        "contract": "Editorial guidance only; signal capsules are the exclusive factual record.",
        "constitution_version": identity["constitution_version"],
        "constitution_sha256": identity["sha256"],
        "guidance": constitution,
    }
