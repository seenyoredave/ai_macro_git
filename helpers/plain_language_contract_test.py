from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

# Build the blocked fragments without spelling them in this source file.
BLOCKED = (("cano" + "n").casefold(), ("chi" + "ld").casefold())
TEXT_SUFFIXES = {".py", ".md", ".css", ".json", ".jsonl", ".csv", ".toml", ".yml", ".yaml", ".txt"}

ACTIVE_ROOTS = [
    ROOT / "README.md",
    ROOT / "ai_macro.py",
    ROOT / "analytics",
    ROOT / "automation",
    ROOT / "config",
    ROOT / "docs",
    ROOT / "helpers",
    ROOT / "loaders",
    ROOT / "rendering",
    ROOT / "tooling",
    ROOT / "water",
]

LIVE_LANGUAGE_FILES = [
    "AI_MACRO_LANGUAGE_LAYER_SOURCE_v1.0.json",
    "AI_MACRO_LANGUAGE_LAYER_v1.0.json",
    "AI_MACRO_MARKET_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_FINANCE_CORPUS_COMPLETE_v1.1.json",
    "AI_MACRO_COMPUTE_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_DATA_CENTER_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_CONNECTIVITY_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_WATER_CORPUS_COMPLETE_v1.0.json",
    "AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_COMPLETE_v1.0.json",
]

GENERATED_FILES = [
    ROOT / "data" / "grid_storage" / "source_manifest.csv",
    ROOT / "data" / "infrastructure" / "source_manifest.csv",
    ROOT / "data" / "water" / "field_dictionary.csv",
    ROOT / "data" / "water" / "source_manifest.csv",
    ROOT / "data" / "infrastructure" / "derived" / "universal_data_center_entities.csv",
    ROOT / "data" / "infrastructure" / "derived" / "universal_data_center_membership.csv",
    ROOT / "data" / "infrastructure" / "derived" / "universal_data_center_registry.json",
]


def _files() -> list[Path]:
    output: list[Path] = []
    for root in ACTIVE_ROOTS:
        if root.is_file():
            output.append(root)
            continue
        if root.exists():
            output.extend(
                path for path in root.rglob("*")
                if path.is_file() and path.suffix.casefold() in TEXT_SUFFIXES and "__pycache__" not in path.parts
            )
    output.extend(ROOT / "language" / name for name in LIVE_LANGUAGE_FILES)
    output.extend(path for path in GENERATED_FILES if path.exists())
    return sorted(set(path for path in output if path.exists()))


def main() -> int:
    failures: list[str] = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.casefold()
        patterns = (
            re.compile(r"\b" + re.escape(BLOCKED[0]) + r"[a-z_]*\b"),
            re.compile(r"\b(?:" + re.escape(BLOCKED[1]) + r"|" + re.escape(BLOCKED[1] + "ren") + r")\b"),
        )
        for pattern in patterns:
            match = pattern.search(lowered)
            if match:
                line = lowered.count("\n", 0, match.start()) + 1
                failures.append(f"{path.relative_to(ROOT)}:{line}")

    old_pipeline = ROOT / "data" / ("energy_natural_gas_pipeline_" + BLOCKED[0] + "ical.csv")
    if old_pipeline.exists():
        failures.append(str(old_pipeline.relative_to(ROOT)))

    if failures:
        print("FAIL  plain-language vocabulary remains in active project surfaces")
        for item in failures[:50]:
            print(f"  {item}")
        return 1

    print("PASS  plain-language vocabulary · active code, UI, docs, tests, live language layer, and registry outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
