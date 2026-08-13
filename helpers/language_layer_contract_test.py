"""Stop-the-line contract for the compiled AI Macro language layer."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.language_layer import (  # noqa: E402
    LanguageLayerError,
    language_layer_identity,
    language_layer_payload,
    load_language_layer,
    validate_language_layer,
)
from analytics.read_evidence import DOMAIN_ORDER  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    check = subprocess.run(
        [sys.executable, str(ROOT / "tooling" / "compile_language_layer.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    require(check.returncode == 0, check.stdout + check.stderr)

    layer = load_language_layer()
    identity = language_layer_identity()
    profiles = layer["payload"]["profiles"]
    require(tuple(profiles) == tuple(DOMAIN_ORDER), "Layer domain order diverges from deterministic evidence order.")
    require(len(profiles) == 11, "Layer does not contain exactly 11 domain profiles.")
    corpus_backed = [domain for domain, profile in profiles.items() if profile["source_state"] == "CORPUS_BACKED"]
    platform_native = [domain for domain, profile in profiles.items() if profile["source_state"] == "PLATFORM_NATIVE"]
    require(corpus_backed == list(DOMAIN_ORDER), "Corpus-backed profile set is wrong.")
    require(platform_native == [], "A platform-native profile survived corpus completion.")
    require(len(layer["corpus_manifest"]) == 8, "Layer corpus manifest is incomplete.")
    require(
        profiles["power"]["corpus_sources"][0]["filename"] == "AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json",
        "Power profile does not use the completed combined corpus.",
    )
    require(
        profiles["grid_storage"]["corpus_sources"][0]["filename"] == "AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json",
        "Grid & Storage profile does not use the completed combined corpus.",
    )
    require(
        profiles["water"]["corpus_sources"][0]["filename"] == "AI_MACRO_WATER_CORPUS_COMPLETE_v1.0.json",
        "Water profile does not use the completed Water corpus.",
    )
    for domain in ("adoption", "workforce", "economic_impact"):
        require(
            profiles[domain]["corpus_sources"][0]["filename"] == "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_COMPLETE_v1.0.json",
            f"{domain} profile does not use the completed diffusion and economic-transmission corpus.",
        )
    bonus = layer["payload"]["systems_dynamics_bonus"]
    require(bonus["status"] == "FULLY_INGESTED", "Neuroscience systems-dynamics layer is not fully ingested.")
    require(bonus["audit"]["sources_fully_reviewed"] == 16, "Neuroscience source audit was not carried forward.")
    require(len(bonus["system_families"]) == 22, "Neuroscience canonical family set was truncated.")
    require(len(bonus["mathematical_motifs"]) == 14, "Neuroscience mathematical motif set was truncated.")
    require("never factual evidence" in bonus["hard_boundary"], "Neuroscience analogy boundary was weakened.")
    require(len(identity["payload_sha256"]) == 64, "Layer identity has no full payload digest.")

    domain_payload = language_layer_payload(phase="domain")
    macro_payload = language_layer_payload(phase="macro")
    require(tuple(domain_payload["guidance"]["profiles"]) == tuple(DOMAIN_ORDER), "Domain prompt payload lost a profile.")
    require(tuple(macro_payload["guidance"]["profiles"]) == tuple(DOMAIN_ORDER), "Macro prompt payload lost a profile.")
    require("not factual evidence" in domain_payload["contract"], "Domain prompt does not state the evidence boundary.")
    require("not factual evidence" in macro_payload["contract"], "Macro prompt does not state the evidence boundary.")
    model_payload_blob = json.dumps({"domain": domain_payload, "macro": macro_payload}, ensure_ascii=False)
    require("Operating cash covers current capital spending at covered companies" not in model_payload_blob, "Recorded failure prose leaked into the model prompt as an answer pattern.")
    require("generalized_failure_lessons" in domain_payload["guidance"] and "editorial_failure_memory" not in domain_payload["guidance"], "Domain prompt exposes failure cases instead of general lessons.")
    require(len(domain_payload["guidance"]["systems_dynamics_bonus"]["system_families"]) == 22, "Domain prompt lost the neuroscience systems layer.")
    require(len(macro_payload["guidance"]["systems_dynamics_bonus"]["system_families"]) == 22, "Macro prompt lost the neuroscience systems layer.")
    require(domain_payload["guidance"] == macro_payload["guidance"], "The two calls do not receive the same complete language layer.")
    require(len(domain_payload["guidance"]["architecture_library"]) >= 10, "Architecture inventory is too narrow.")
    calibration = macro_payload["guidance"].get("reader_calibration") or {}
    require("highly intelligent" in str(calibration.get("audience") or ""), "Sophisticated non-specialist audience is missing.")
    require(len(calibration.get("contextual_sufficiency") or []) == 4, "Contextual-sufficiency rules are incomplete.")
    require(len(calibration.get("neutral_scope") or []) == 4, "Neutral-scope and proportional-language rules are incomplete.")
    require(
        any("counted population" in item for item in calibration.get("neutral_scope") or []),
        "Ambiguous proportional construction was not generalized into a subject rule.",
    )
    require(len(calibration.get("explanatory_restraint") or []) == 5, "Anti-pedantry rules are incomplete.")
    require(len(calibration.get("paragraph_guidance") or []) == 4, "Macro paragraph calibration is incomplete.")
    require("reader_pedagogy" not in macro_payload["guidance"], "Novice teaching layer survived recalibration.")
    require(any(item.get("id") == "voice.sound" for item in macro_payload["guidance"]["universal_guidance"]), "Alliteration guidance is missing.")
    require(any(item.get("id") == "voice.neutral_scope" for item in macro_payload["guidance"]["universal_guidance"]), "Neutral editorial scope is missing.")

    copied = json.loads(json.dumps(layer))
    copied["payload"]["profiles"]["market"]["objective"] = "tampered"
    try:
        validate_language_layer(copied)
    except LanguageLayerError:
        pass
    else:
        raise AssertionError("Engine accepted a payload whose checksum no longer matched.")

    with tempfile.TemporaryDirectory() as temp_dir:
        malformed = Path(temp_dir) / "layer.json"
        malformed.write_text("{not-json", encoding="utf-8")
        load_language_layer.cache_clear()
        try:
            load_language_layer(malformed)
        except LanguageLayerError:
            pass
        else:
            raise AssertionError("Engine did not fail closed on malformed JSON.")
        finally:
            load_language_layer.cache_clear()

    print(
        "PASS AI Macro language layer contract · "
        f"{identity['layer_version']} · 11 domains · 11 corpus-backed · digest {identity['payload_sha256'][:16]}"
    )


if __name__ == "__main__":
    main()
