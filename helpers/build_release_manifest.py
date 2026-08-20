"""Build one compact fingerprint for a publication-ready retained-data release."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.regime_engine import (  # noqa: E402
    AEI_VERSION,
    ADI_VERSION,
    BORROWER_STRAIN_VERSION,
    EVG_VERSION,
    LENDER_STRAIN_VERSION,
    POWER_STRESS_VERSION,
    PRESSURE_VERSION,
)
from config.benchmark_config import (  # noqa: E402
    BENCHMARK_VERSION,
    QQQ_WEIGHTS_EFFECTIVE_DATE,
)
from helpers.atomic_io import atomic_write_json  # noqa: E402

OUTPUT = PROJECT_ROOT / "data" / "release_manifest.json"
RELEASE_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "config/sector_config.py",
    "config/factor_config.py",
    "config/benchmark_config.py",
    "config/deployment.py",
    "config/load_policy.py",
    "config/current_context_policy.py",
    "automation/__init__.py",
    "automation/config.py",
    "automation/ledger.py",
    "automation/budget.py",
    "automation/research_refresh.py",
    "automation/runner.py",
    "automation/status.py",
    "automation/retained_state.py",
    "automation/git_transport.py",
    "tooling/__init__.py",
    "tooling/repository_policy.py",
    "tooling/git_guard.py",
    "benchmarks/benchmark_service.py",
    "archive/archive.py",
    "analytics/regime_engine.py",
    "analytics/trend_engine.py",
    "analytics/spatial_context.py",
    "analytics/data_center_metrics.py",
    "analytics/domain_state.py",
    "analytics/adoption_depth.py",
    "analytics/water_campus.py",
    "analytics/water_competition.py",
    "analytics/water_local.py",
    "analytics/read_evidence.py",
    "analytics/read_capsules.py",
    "analytics/read_materiality.py",
    "analytics/language_layer.py",
    "analytics/editorial_quality.py",
    "analytics/read_models.py",
    "analytics/read_prompts.py",
    "analytics/read_generation.py",
    "analytics/read_validation.py",
    "analytics/read_context.py",
    "analytics/read_store.py",
    "analytics/read_service.py",
    "language/AI_MACRO_LANGUAGE_LAYER_SOURCE_v1.0.json",
    "language/AI_MACRO_LANGUAGE_LAYER_v1.0.json",
    "language/AI_MACRO_EDITORIAL_CONSTITUTION_v1.0.json",
    "language/editorial_regression_cases.json",
    "language/AI_MACRO_MARKET_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_FINANCE_CORPUS_COMPLETE_v1.1.json",
    "language/AI_MACRO_COMPUTE_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_DATA_CENTER_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_CONNECTIVITY_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_POWER_GRID_STORAGE_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_WATER_CORPUS_COMPLETE_v1.0.json",
    "language/AI_MACRO_DIFFUSION_ECONOMIC_TRANSMISSION_CORPUS_COMPLETE_v1.0.json",
    "tooling/compile_power_grid_storage_corpus.jq",
    "tooling/compile_water_corpus.jq",
    "tooling/compile_diffusion_economic_transmission_corpus.jq",
    "tooling/compile_language_layer.py",
    "developer/state.py",
    "developer/reports.py",
    "developer/load_report.py",
    "developer/panel.py",
    "config/openai_config.py",
    "analytics/reader_snapshot.py",
    "analytics/capital_commitments.py",
    "analytics/deployment_funding_mix.py",
    "config/metric_definitions.py",
    "helpers/atomic_io.py",
    "helpers/build_release_manifest.py",
    "helpers/build_capital_commitment_ledger.py",
    "helpers/build_water_ledger.py",
    "helpers/build_universal_data_center_registry.py",
    "water/schema.py",
    "water/sources.py",
    "water/refresh.py",
    "water/usdm_county.py",
    "water/epa_pws.py",
    "water/local_context.py",
    "loaders/snapshot_writer.py",
    "loaders/benchmark_loader.py",
    "loaders/fred_loader.py",
    "loaders/nfci_loader.py",
    "loaders/debt_markets_loader.py",
    "loaders/energy_loader.py",
    "loaders/energy_market_loader.py",
    "loaders/construction_loader.py",
    "loaders/infrastructure_loader.py",
    "loaders/data_center_registry.py",
    "loaders/compute_manufacturing_loader.py",
    "loaders/connectivity_loader.py",
    "loaders/water_loader.py",
    "loaders/adoption_loader.py",
    "loaders/adoption_depth_loader.py",
    "loaders/workforce_loader.py",
    "loaders/economic_impact_loader.py",
    "loaders/edgar_client.py",
    "loaders/edgar_loader.py",
    "loaders/market_loader.py",
    "loaders/borrower_finance_refresh.py",
    "loaders/market_valuation_loader.py",
    "loaders/official_series_refresh.py",
    "loaders/current_context_news.py",
    "loaders/current_context_discovery.py",
    "loaders/current_context_grounding.py",
    "loaders/current_context_daily.py",
    "loaders/current_context_registry.py",
    "loaders/current_context_loader.py",
    "loaders/commercialization_loader.py",
    "rendering/components.py",
    "rendering/layout_contracts.py",
    "rendering/dashboard.py",
    "rendering/macro.py",
    "rendering/visual_system.py",
    "rendering/dataframe.py",
    "rendering/common.py",
    "rendering/charts_common.py",
    "rendering/charts_adoption.py",
    "rendering/adoption.py",
    "rendering/charts_data_center.py",
    "rendering/data_center.py",
    "rendering/spatial.py",
    "rendering/map_geometry.py",
    "rendering/charts_water.py",
    "rendering/water.py",
    "assets/geo/us_counties.geojson",
    "assets/geo/us_states.geojson",
    "rendering/read_markup.py",
    "rendering/evidence.py",
    "rendering/market.py",
    "rendering/finance.py",
    "rendering/power.py",
    "rendering/theme.css",
    "ai_macro.py",
    "docs/RUNTIME_DATA_CONTRACT.md",
    "docs/UNIVERSAL_DATA_CENTER_REGISTRY.md",
    "docs/LANGUAGE_LAYER.md",
    "docs/AUTOMATION_ARCHITECTURE.md",
    "docs/EDITORIAL_STYLE.md",
    "archive/yf_history.csv",
    "archive/benchmark_history.csv",
    "archive/sector_history.csv",
    "archive/macro_history.csv",
    "archive/edgar_history.csv",
    "archive/fred_history.csv",
    "data/capital_commitment_components.csv",
    "data/capital_commitments.csv",
    "data/borrower_strain_fundamentals_history.csv",
    "data/debt_financing_observations.csv",
    "data/market_valuation_context.csv",
    "data/weekly_context_events.csv",
    "data/retained_state_manifest.json",
    "data/infrastructure/curated/data_center_identity_decisions.csv",
    "data/infrastructure/curated/data_center_primary_evidence.csv",
    "data/infrastructure/derived/universal_data_center_entities.csv",
    "data/infrastructure/derived/universal_data_center_observations.csv",
    "data/infrastructure/derived/universal_data_center_membership.csv",
    "data/infrastructure/derived/universal_data_center_unresolved.csv",
    "data/infrastructure/derived/universal_data_center_registry.json",
    "data/infrastructure/source_manifest.csv",
    "data/infrastructure/derived/compute_manufacturing_history.csv",
    "data/infrastructure/derived/compute_m3_history.csv",
    "data/energy_interconnection_queue.csv",
    "data/energy_interconnection_queue_summary.csv",
)
DATE_COLUMNS = (
    "Date",
    "Market Data Date",
    "Observation Date",
    "Period End",
    "Filed",
    "Retrieved",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv_metadata(path: Path) -> dict:
    frame = pd.read_csv(path, low_memory=False)
    metadata: dict[str, object] = {"rows": int(len(frame))}
    for column in DATE_COLUMNS:
        if column not in frame.columns:
            continue
        dates = pd.to_datetime(frame[column], errors="coerce", format="mixed").dropna()
        if dates.empty:
            continue
        metadata.update(
            {
                "date_column": column,
                "date_min": dates.min().date().isoformat(),
                "date_max": dates.max().date().isoformat(),
            }
        )
        break
    return metadata


def build_manifest() -> dict:
    files: dict[str, dict] = {}
    # Paid/generated OpenAI artifacts are runtime state, not source-release
    # inputs.  They live under openai_artifacts/ and are intentionally excluded
    # from ordinary release fingerprints and update packages.
    release_files = list(RELEASE_FILES)
    for relative in release_files:
        path = PROJECT_ROOT / relative
        if not path.exists():
            raise FileNotFoundError(f"Release input is missing: {relative}")
        item = {"sha256": _sha256(path), "bytes": int(path.stat().st_size)}
        if path.suffix.casefold() == ".csv":
            item.update(_csv_metadata(path))
        files[relative] = item

    release_material = "\n".join(
        f"{relative}:{item['sha256']}" for relative, item in sorted(files.items())
    )
    release_id = hashlib.sha256(release_material.encode("utf-8")).hexdigest()[:20]
    return {
        "manifest_version": "1.0",
        "release_id": release_id,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scope": "Critical retained archives, analytical contracts, and identity decisions",
        "benchmark_contract": {
            "version": BENCHMARK_VERSION,
            "weight_effective_date": QQQ_WEIGHTS_EFFECTIVE_DATE,
        },
        "metric_versions": {
            "aei": AEI_VERSION,
            "adi": ADI_VERSION,
            "economic_validation_gap": EVG_VERSION,
            "power_stress": POWER_STRESS_VERSION,
            "borrower_strain": BORROWER_STRAIN_VERSION,
            "lender_strain": LENDER_STRAIN_VERSION,
            "trading_pressure": PRESSURE_VERSION,
        },
        "files": files,
    }


def main() -> None:
    manifest = build_manifest()
    atomic_write_json(manifest, OUTPUT)
    print(
        f"Wrote release {manifest['release_id']} with "
        f"{len(manifest['files'])} critical files."
    )


if __name__ == "__main__":
    main()
