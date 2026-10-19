"""Local-owner refresh of Finance's independently sourced PE observations.

The ordinary Finance render always reads retained data. This function is invoked
only by the explicit Developer Tools Finance domain refresh; automation keeps
using the same underlying publisher parsers and retained files.
"""
from __future__ import annotations

from config.deployment import repository_writes_enabled
from loaders.pe_us_liquidity_retained import PRODUCTION, refresh as refresh_liquidity
from loaders.pe_us_returns_retained import refresh as refresh_returns
from automation.refresh_graph import load_refresh_graph_state, save_refresh_graph_state
from config.market_clock import utc_now


def _record_successful_retrievals(results: list[dict], *, node: str) -> None:
    """Advance the already-used retrieval timestamp, not source observation dates."""
    if not any(row.get("status") in {"updated", "unchanged"} for row in results):
        return
    state = load_refresh_graph_state()
    nodes = state.setdefault("nodes", {})
    record = nodes.setdefault(node, {})
    record["last_retrieval_at_utc"] = utc_now().isoformat()
    save_refresh_graph_state(state)


def refresh_finance_pe_sources() -> dict:
    if not repository_writes_enabled():
        raise PermissionError("Finance PE retrieval requires an authorized developer runtime")

    # Reuse the production candidate parser, validators and retained publisher,
    # without calling the automation-only run() entry point from local mode.
    industry: list[dict] = []
    try:
        from loaders.pe_industry_pipeline import source_candidate, validate_observations, persist_source
    except ImportError as exc:
        industry = [{"source": name, "status": "unavailable", "error": f"Industry loader missing: {exc}"}
                    for name in ("sec", "acg")]
    else:
        for name in ("sec", "acg"):
            path = PRODUCTION / f"pe_industry_{name}.csv"
            try:
                observations, warnings = source_candidate(name)
                frame = validate_observations(observations, name)
                record = persist_source(name, frame, path)
                record["unparsed_releases"] = len(warnings)
                record["sample_issues"] = warnings[:3]
            except Exception as exc:
                record = {"source": name, "status": "retained_on_failure" if path.exists() else "unavailable",
                          "error": f"{type(exc).__name__}: {exc}"}
            industry.append(record)
    _record_successful_retrievals(industry, node="pe_industry")

    liquidity = refresh_liquidity(out_dir=PRODUCTION)
    returns = refresh_returns(out_dir=PRODUCTION)
    cash = [*liquidity, returns]
    _record_successful_retrievals(cash, node="pe_us_liquidity")
    all_rows = [*industry, *cash]
    errors = {row["source"]: row.get("error", "Source unavailable")
              for row in all_rows if row.get("status") not in {"updated", "unchanged"}}
    succeeded = any(row.get("status") in {"updated", "unchanged"} for row in all_rows)
    mode = "live_refresh" if not errors else "partial_refresh" if succeeded else "retained_fallback"
    return {"source_mode": mode,
            "industry": industry, "liquidity": cash, "errors": errors}
