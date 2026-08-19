"""Compile the auditable corpus source into the portable OpenAI language layer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "language" / "AI_MACRO_LANGUAGE_LAYER_SOURCE_v1.0.json"
OUTPUT = ROOT / "language" / "AI_MACRO_LANGUAGE_LAYER_v1.0.json"
DOMAIN_ORDER = (
    "market", "finance", "compute", "data_center", "connectivity", "power",
    "grid_storage", "water", "adoption", "workforce", "economic_impact",
)
REQUIRED_PROFILE_FIELDS = (
    "label", "source_state", "corpus_sources", "provenance_refs", "objective",
    "relationship_chain", "preferred_architectures", "vocabulary", "anti_patterns",
    "evidence_rules",
)


def _stable_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load language-engine input {path}: {exc}") from exc


def _require_text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
        raise ValueError(f"{field} must be a nonempty list of text values")
    return list(dict.fromkeys(str(item).strip() for item in value))


def _scalar_values(value: Any) -> set[str]:
    """Collect exact scalar values so provenance is structural, not substring based."""
    if isinstance(value, dict):
        values: set[str] = set()
        for key, item in value.items():
            values.add(str(key))
            values.update(_scalar_values(item))
        return values
    if isinstance(value, list):
        values = set()
        for item in value:
            values.update(_scalar_values(item))
        return values
    if value is None:
        return set()
    return {str(value)}


def compile_layer(source_path: Path = SOURCE) -> dict[str, Any]:
    source = _load_json(source_path)
    if str(source.get("schema_version")) != "1.0":
        raise ValueError("Unsupported language-layer source schema")
    profiles = source.get("profiles")
    if not isinstance(profiles, dict) or tuple(profiles) != DOMAIN_ORDER:
        raise ValueError(f"Profiles must contain all domains in defined order: {DOMAIN_ORDER}")

    compiled_profiles: dict[str, Any] = {}
    corpus_manifest: dict[str, Any] = {}
    for domain in DOMAIN_ORDER:
        profile = profiles[domain]
        missing = [field for field in REQUIRED_PROFILE_FIELDS if field not in profile]
        if missing:
            raise ValueError(f"{domain} profile missing fields: {missing}")
        state = str(profile["source_state"])
        if state not in {"CORPUS_BACKED", "PLATFORM_NATIVE"}:
            raise ValueError(f"{domain} has invalid source_state {state!r}")
        sources = list(profile["corpus_sources"])
        refs = list(profile["provenance_refs"])
        if state == "CORPUS_BACKED" and (not sources or not refs):
            raise ValueError(f"{domain} is corpus-backed but lacks source files or provenance refs")
        if state == "PLATFORM_NATIVE" and (sources or refs):
            raise ValueError(f"{domain} is platform-native but claims corpus provenance")
        source_records = []
        for filename in sources:
            path = source_path.parent / str(filename)
            corpus = _load_json(path)
            corpus_values = _scalar_values(corpus)
            missing_refs = [ref for ref in refs if str(ref) not in corpus_values]
            if missing_refs:
                raise ValueError(f"{domain} provenance refs absent from {filename}: {missing_refs}")
            record = {
                "filename": str(filename),
                "sha256": _sha256_bytes(path.read_bytes()),
                "bytes": path.stat().st_size,
                "corpus_version": str(corpus.get("corpus_version") or corpus.get("version") or ""),
            }
            source_records.append(record)
            corpus_manifest[str(filename)] = record
        compiled_profiles[domain] = {
            "label": str(profile["label"]).strip(),
            "source_state": state,
            "objective": str(profile["objective"]).strip(),
            "relationship_chain": _require_text_list(profile["relationship_chain"], f"{domain}.relationship_chain"),
            "preferred_architectures": _require_text_list(profile["preferred_architectures"], f"{domain}.preferred_architectures"),
            "vocabulary": _require_text_list(profile["vocabulary"], f"{domain}.vocabulary"),
            "anti_patterns": _require_text_list(profile["anti_patterns"], f"{domain}.anti_patterns"),
            "evidence_rules": _require_text_list(profile["evidence_rules"], f"{domain}.evidence_rules"),
            "provenance_refs": [str(item) for item in refs],
            "corpus_sources": source_records,
        }

    bonus_config = source.get("systems_dynamics_bonus")
    if not isinstance(bonus_config, dict):
        raise ValueError("Systems-dynamics bonus configuration is missing")
    bonus_path = source_path.parent / str(bonus_config.get("source_file") or "")
    bonus_corpus = _load_json(bonus_path)
    bonus = bonus_corpus.get(str(bonus_config.get("source_object") or ""))
    if not isinstance(bonus, dict) or str(bonus.get("status")) != str(bonus_config.get("required_status")):
        raise ValueError("Systems-dynamics bonus is absent or not fully ingested")
    audit = bonus.get("ingestion_audit") or {}
    for field, expected in (bonus_config.get("required_audit") or {}).items():
        if int(audit.get(field, -1)) != int(expected):
            raise ValueError(f"Systems-dynamics audit mismatch for {field}: expected {expected}, found {audit.get(field)}")
    families = bonus.get("system_families") or []
    motifs = bonus.get("mathematical_motif_registry") or []
    transfers = bonus.get("finance_transfer_candidates") or []
    if len(families) != 22 or len(motifs) != 14 or len(transfers) != 12:
        raise ValueError("Systems-dynamics synthesis is incomplete")
    systems_dynamics_bonus = {
        "name": str(bonus.get("name") or ""),
        "status": str(bonus.get("status") or ""),
        "audit": {field: audit[field] for field in bonus_config["required_audit"]},
        "hard_boundary": str(bonus_config.get("hard_boundary") or ""),
        "system_families": [
            {
                "id": str(item.get("bonus_family_id") or ""),
                "name": str(item.get("name") or ""),
                "reasoning_pattern": str(item.get("learned_pattern") or ""),
            }
            for item in families
        ],
        "mathematical_motifs": [
            {"motif": str(item.get("motif") or ""), "analytical_use": str(item.get("analytical_use") or "")}
            for item in motifs
        ],
        "application_guardrails": [
            str(item.get("finance_application") or "") for item in transfers if item.get("finance_application")
        ],
        "source": {
            "filename": bonus_path.name,
            "sha256": _sha256_bytes(bonus_path.read_bytes()),
        },
    }

    architectures = source.get("architecture_library")
    if not isinstance(architectures, list) or len(architectures) < 10:
        raise ValueError("Architecture library is incomplete")
    architecture_ids = {str(item.get("id") or "") for item in architectures if isinstance(item, dict)}
    if len(architecture_ids) != len(architectures) or "" in architecture_ids:
        raise ValueError("Architecture IDs must be nonempty and unique")
    for domain, profile in compiled_profiles.items():
        affinities = set(profile["preferred_architectures"])
        if len(affinities) < 5 or not affinities.issubset(architecture_ids):
            raise ValueError(f"{domain} architecture affinities are incomplete or unknown")

    payload = {
        "runtime_contract": source.get("runtime_contract"),
        "hard_boundaries": _require_text_list(source.get("hard_boundaries"), "hard_boundaries"),
        "universal_guidance": source.get("universal_guidance"),
        "read_set_composition": _require_text_list(source.get("read_set_composition"), "read_set_composition"),
        "architecture_library": architectures,
        "sentence_craft": _require_text_list(source.get("sentence_craft"), "sentence_craft"),
        "uncertainty_calibration": _require_text_list(source.get("uncertainty_calibration"), "uncertainty_calibration"),
        "evidence_conditioned_expression": source.get("evidence_conditioned_expression"),
        "reader_calibration": source.get("reader_calibration"),
        "macro_guidance": _require_text_list(source.get("macro_guidance"), "macro_guidance"),
        "systems_dynamics_bonus": systems_dynamics_bonus,
        "generalized_failure_lessons": _require_text_list(source.get("generalized_failure_lessons"), "generalized_failure_lessons"),
        "profiles": compiled_profiles,
    }
    if not isinstance(payload["universal_guidance"], list) or len(payload["universal_guidance"]) < 6:
        raise ValueError("Universal guidance is incomplete")
    if not isinstance(payload["evidence_conditioned_expression"], list) or len(payload["evidence_conditioned_expression"]) < 4:
        raise ValueError("Evidence-conditioned expression rules are incomplete")
    calibration = payload["reader_calibration"]
    if not isinstance(calibration, dict):
        raise ValueError("Reader calibration is missing")
    for field in ("audience", "stance", "contextual_sufficiency", "neutral_scope", "explanatory_restraint", "paragraph_guidance"):
        if not calibration.get(field):
            raise ValueError(f"Reader calibration is missing {field}")

    return {
        "schema_version": "1.0",
        "layer_version": str(source.get("layer_version") or "").strip(),
        "effective_date": str(source.get("effective_date") or "").strip(),
        "purpose": str(source.get("purpose") or "").strip(),
        "source_sha256": _sha256_bytes(_stable_json(source)),
        "payload_sha256": _sha256_bytes(_stable_json(payload)),
        "corpus_manifest": corpus_manifest,
        "payload": payload,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if the compiled artifact is absent or stale")
    args = parser.parse_args()
    compiled = compile_layer()
    rendered = json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Compiled language layer is missing or stale. Run tooling/compile_language_layer.py.")
        print(f"PASS {compiled['layer_version']} {compiled['payload_sha256'][:16]} 11 domains")
        return
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"WROTE {OUTPUT.relative_to(ROOT)} {compiled['payload_sha256'][:16]}")


if __name__ == "__main__":
    main()
