"""Non-destructive live coverage probe for Water v2 local-context sources.

This helper reads the retained facility registry, queries the current U.S.
Drought Monitor county statistics and EPA public-water service-area layer, and
prints a compact coverage report. Provider results are kept in memory or in a
temporary cache; this probe does not modify ``data/`` or ``archive/``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.read_evidence import build_water_evidence  # noqa: E402
from analytics.spatial_context import attach_water_context  # noqa: E402
from analytics.water_local import local_water_constraint_summary  # noqa: E402
from loaders.infrastructure_loader import load_infrastructure_data  # noqa: E402
from loaders.water_loader import load_water_utilization_data  # noqa: E402
from water.epa_pws import refresh_facility_matches  # noqa: E402
from water.usdm_county import fetch_county_drought  # noqa: E402


def _number(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _bool(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype=bool)
    return frame[column].fillna(False).astype(bool)


def _text(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype=str)
    return frame[column].fillna("").astype(str).str.strip()


def _capacity(frame: pd.DataFrame) -> pd.Series:
    output = pd.Series(np.nan, index=frame.index, dtype=float)
    for column in (
        "Planned Data Center Capacity MW",
        "Published Capacity Estimate MW",
        "Published Capacity MW",
    ):
        if column in frame.columns:
            candidate = pd.to_numeric(frame[column], errors="coerce")
            output = output.where(output.notna(), candidate)
    return output.where(output > 0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(record) for record in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    if pd.isna(value) if not isinstance(value, (dict, list, tuple, str, bytes)) else False:
        return None
    return value


def _top_counties(frame: pd.DataFrame, *, limit: int = 15) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    work = frame.copy()
    work["County D2+ Area Percent"] = _number(work, "County D2+ Area Percent")
    work["Published Capacity MW"] = _capacity(work)
    work["_pws"] = _bool(work, "PWS Service Area Overlap")
    work["_authoritative"] = _bool(work, "PWS Authoritative Boundary Overlap")
    work["_direct"] = _bool(work, "Direct Water Evidence")
    work["_state"] = _text(work, "State")
    work["_county"] = _text(work, "County")
    work = work.loc[work["County D2+ Area Percent"].notna() & work["_state"].ne("") & work["_county"].ne("")]
    if work.empty:
        return []
    grouped = (
        work.groupby(["_state", "_county"], dropna=False)
        .agg(
            Facilities=("_county", "size"),
            **{
                "D2+ Area Percent": ("County D2+ Area Percent", "max"),
                "Published Capacity MW": ("Published Capacity MW", lambda values: values.sum(min_count=1)),
                "PWS Overlap Facilities": ("_pws", "sum"),
                "Authoritative PWS Overlap": ("_authoritative", "sum"),
                "Direct Water Evidence": ("_direct", "sum"),
            },
        )
        .reset_index()
        .rename(columns={"_state": "State", "_county": "County"})
    )
    grouped = grouped.sort_values(
        ["D2+ Area Percent", "Published Capacity MW", "Facilities"],
        ascending=[False, False, False],
        kind="stable",
    ).head(max(int(limit), 1))
    return _json_safe(grouped)


def _error_summary(errors: dict[str, str] | None, *, limit: int = 10) -> dict[str, Any]:
    payload = dict(errors or {})
    counts: dict[str, int] = {}
    for message in payload.values():
        category = str(message or "").split(":", 1)[0].strip() or "unknown"
        counts[category] = counts.get(category, 0) + 1
    return {
        "count": len(payload),
        "by_type": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples": [f"{key}: {value}" for key, value in list(payload.items())[: max(int(limit), 0)]],
    }


def build_report(*, workers: int = 6, max_points: int = 12) -> dict[str, Any]:
    infrastructure = load_infrastructure_data(
        refresh_token=0,
        force_construction_refresh=False,
        force_facility_refresh=False,
        force_compute_refresh=False,
        allow_construction_live=False,
        allow_facility_live=False,
        allow_compute_live=False,
    )
    facilities = infrastructure.get("facility_registry")
    if not isinstance(facilities, pd.DataFrame) or facilities.empty:
        raise RuntimeError("Retained facility registry is unavailable or empty.")
    facilities = facilities.copy()

    latitude = _number(facilities, "Latitude")
    longitude = _number(facilities, "Longitude")
    queryable = latitude.notna() & longitude.notna()
    requested_facilities = facilities.copy()
    if int(max_points) > 0:
        with_coordinates = facilities.loc[queryable].copy().head(int(max_points))
        without_coordinates = facilities.loc[~queryable].copy()
        requested_facilities = pd.concat([with_coordinates, without_coordinates], ignore_index=True, sort=False)

    states = sorted(set(_text(requested_facilities, "State").loc[lambda s: s.ne("")].str.upper()))
    print(f"[water-probe] facilities={len(requested_facilities):,} · states={len(states):,} · EPA queryable={int((_number(requested_facilities, 'Latitude').notna() & _number(requested_facilities, 'Longitude').notna()).sum()):,}", flush=True)
    print("[water-probe] fetching U.S. Drought Monitor county statistics", flush=True)
    county_drought, usdm_report = fetch_county_drought(states)
    print(f"[water-probe] USDM rows={len(county_drought):,} · errors={len((usdm_report or {}).get('errors') or {})}", flush=True)

    print("[water-probe] querying EPA community-water service-area boundaries", flush=True)
    with tempfile.TemporaryDirectory(prefix="ai_macro_water_probe_") as temporary:
        pws_matches, pws_report = refresh_facility_matches(
            requested_facilities,
            cache_path=Path(temporary) / "epa_pws_probe.csv.gz",
            max_workers=max(1, min(int(workers), 12)),
            persist=False,
        )
    print(f"[water-probe] EPA resolved={int((pws_report or {}).get('resolved_points', 0) or 0):,} · matched={int((pws_report or {}).get('matched_points', 0) or 0):,} · errors={len((pws_report or {}).get('errors') or {})}", flush=True)

    water = load_water_utilization_data(force_refresh=False, refresh_token=0, allow_live=False)
    water = dict(water or {})
    water["usdm_county_drought"] = county_drought
    water["epa_pws_matches"] = pws_matches
    water["local_context_refresh_requested"] = False

    infrastructure = dict(infrastructure)
    infrastructure["facility_registry"] = requested_facilities
    infrastructure, water = attach_water_context(infrastructure, water)
    context = water.get("facility_context")
    if not isinstance(context, pd.DataFrame):
        context = pd.DataFrame()

    summary = local_water_constraint_summary(context)
    packet = build_water_evidence(
        DashboardContext(infrastructure_data=infrastructure, water_data=water)
    ).to_model_dict()

    queryable_count = int((_number(requested_facilities, "Latitude").notna() & _number(requested_facilities, "Longitude").notna()).sum())
    resolved_pws = int(summary.get("service_area_query_resolved", 0) or 0)
    matched_pws = int(summary.get("service_area_overlap", 0) or 0)
    county_resolved = int(summary.get("county_drought_resolved", 0) or 0)

    feature_type_counts: dict[str, int] = {}
    boundary_basis_counts: dict[str, int] = {}
    model_method_counts: dict[str, int] = {}
    if isinstance(pws_matches, pd.DataFrame) and not pws_matches.empty:
        matched = pws_matches.loc[pws_matches.get("Query Status", "").astype(str).eq("matched")].copy()
        if "Feature Type" in matched.columns:
            values = matched["Feature Type"].fillna("").astype(str).str.strip().replace("", "(blank)")
            feature_type_counts = {str(key): int(value) for key, value in values.value_counts().to_dict().items()}
        if "Boundary Basis" in matched.columns:
            values = matched["Boundary Basis"].fillna("").astype(str).str.strip().replace("", "(blank)")
            boundary_basis_counts = {str(key): int(value) for key, value in values.value_counts().to_dict().items()}
        if "Model Method" in matched.columns:
            values = matched["Model Method"].fillna("").astype(str).str.strip().replace("", "(blank)")
            model_method_counts = {str(key): int(value) for key, value in values.value_counts().to_dict().items()}

    report = {
        "probe_version": "water-live-coverage-v1.2",
        "destructive": False,
        "registry": {
            "mapped_facilities": int(len(requested_facilities)),
            "full_registry_facilities": int(len(facilities)),
            "queryable_coordinate_points": queryable_count,
            "coordinate_coverage_share": queryable_count / len(requested_facilities) if len(requested_facilities) else None,
            "states": int(_text(requested_facilities, "State").replace("", np.nan).nunique()),
            "sample_limit": int(max_points) if int(max_points) > 0 else None,
        },
        "usdm": {
            **dict(usdm_report or {}),
            "errors_summary": _error_summary((usdm_report or {}).get("errors")),
            "facility_county_resolution": county_resolved,
            "facility_county_resolution_share": county_resolved / len(context) if len(context) else None,
        },
        "epa_pws": {
            **{key: value for key, value in dict(pws_report or {}).items() if key != "errors"},
            "errors_summary": _error_summary((pws_report or {}).get("errors")),
            "resolved_queryable_share": resolved_pws / queryable_count if queryable_count else None,
            "matched_queryable_share": matched_pws / queryable_count if queryable_count else None,
            "feature_type_counts_on_matches": feature_type_counts,
            "boundary_basis_counts_on_matches": boundary_basis_counts,
            "model_method_counts_on_matches": model_method_counts,
        },
        "local_constraint_summary": summary,
        "top_counties_by_current_d2": _top_counties(context),
        "model_water_packet": packet,
    }
    return _json_safe(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6, help="Concurrent EPA point queries (1-12).")
    parser.add_argument(
        "--max-points",
        type=int,
        default=12,
        help="Coordinate-point cap for a provider smoke run. Defaults to 12.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Query every coordinate-bearing facility instead of the sample cap.",
    )
    args = parser.parse_args(argv)

    report = build_report(workers=args.workers, max_points=0 if args.full else args.max_points)
    print("\n=== AI MACRO WATER V2 LIVE COVERAGE REPORT ===")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("=== END WATER V2 LIVE COVERAGE REPORT ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
