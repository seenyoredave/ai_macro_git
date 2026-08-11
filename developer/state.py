"""Developer-tool state and refresh commands.

The dashboard rebuild consumes these requests.  This module owns intent only;
``LoadPolicy`` remains the authorization boundary for provider access.
"""

from __future__ import annotations

from typing import MutableMapping, Any

from config.market_clock import utc_now

DOMAIN_REFRESH_LABELS = {
    "current_context": "Current Context",
    "compute": "Compute",
    "data_centers": "Data Centers",
    "connectivity": "Connectivity",
    "power": "Power",
    "grid_storage": "Grid & Storage",
    "water": "Water",
    "adoption": "Adoption",
    "workforce": "Workforce",
    "economic_outcomes": "Economic Outcomes",
}
ALL_DOMAIN_REFRESH = "__all_domains__"

SOURCE_REFRESH_LABELS = {
    "yfinance": "YFinance",
    "edgar": "EDGAR",
    "fred": "FRED",
    "nyfed": "NY Fed",
}
SOURCE_REFRESH_STATE = {
    "yfinance": ("force_yfinance_refresh", "yfinance_refresh_token"),
    "edgar": ("force_edgar_refresh", "edgar_refresh_token"),
    "fred": ("force_fred_refresh", "fred_refresh_token"),
    "nyfed": ("force_nyfed_refresh", "nyfed_refresh_token"),
}


def initialize_developer_state(state: MutableMapping[str, Any]) -> None:
    state.setdefault("developer_workspace", "Operations")
    state.setdefault("developer_canvas_view", "Dashboard")
    state.setdefault("developer_last_operation", None)
    state.setdefault("developer_last_ai_result", None)
    state.setdefault("domain_refresh_request", None)
    state.setdefault("domain_refresh_tokens", {key: 0 for key in DOMAIN_REFRESH_LABELS})
    state.setdefault("last_domain_refresh", None)
    for force_key, token_key in SOURCE_REFRESH_STATE.values():
        state.setdefault(force_key, False)
        state.setdefault(token_key, 0)


def _mark_operation(state: MutableMapping[str, Any], *, kind: str, label: str, status: str = "requested") -> None:
    state["developer_last_operation"] = {
        "kind": kind,
        "label": label,
        "status": status,
        "at_utc": utc_now().isoformat(),
    }


def request_domain_refresh(state: MutableMapping[str, Any], domain: str) -> None:
    if domain not in DOMAIN_REFRESH_LABELS:
        raise KeyError(f"Unknown domain refresh: {domain}")
    tokens = dict(state.get("domain_refresh_tokens", {}) or {})
    tokens[domain] = int(tokens.get(domain, 0) or 0) + 1
    state["domain_refresh_tokens"] = tokens
    state["domain_refresh_request"] = domain
    state["force_rebuild"] = True
    _mark_operation(state, kind="domain_refresh", label=DOMAIN_REFRESH_LABELS[domain])


def request_all_domain_refreshes(state: MutableMapping[str, Any]) -> None:
    tokens = dict(state.get("domain_refresh_tokens", {}) or {})
    for domain in DOMAIN_REFRESH_LABELS:
        tokens[domain] = int(tokens.get(domain, 0) or 0) + 1
    state["domain_refresh_tokens"] = tokens
    state["domain_refresh_request"] = ALL_DOMAIN_REFRESH
    state["force_rebuild"] = True
    _mark_operation(state, kind="domain_refresh", label="All domains")


def request_source_refresh(state: MutableMapping[str, Any], source: str) -> None:
    if source not in SOURCE_REFRESH_STATE:
        raise KeyError(f"Unknown source refresh: {source}")
    force_key, token_key = SOURCE_REFRESH_STATE[source]
    state[token_key] = int(state.get(token_key, 0) or 0) + 1
    state[force_key] = True
    state["force_rebuild"] = True
    _mark_operation(state, kind="source_refresh", label=SOURCE_REFRESH_LABELS[source])


def request_all_source_refreshes(state: MutableMapping[str, Any]) -> None:
    for force_key, token_key in SOURCE_REFRESH_STATE.values():
        state[token_key] = int(state.get(token_key, 0) or 0) + 1
        state[force_key] = True
    state["force_rebuild"] = True
    _mark_operation(state, kind="source_refresh", label="All sources")


def refresh_errors(payload: Any) -> list[str]:
    messages: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            error = value.get("error")
            if error:
                messages.append(str(error))
            errors = value.get("errors")
            if isinstance(errors, dict):
                messages.extend(str(message) for message in errors.values() if message)
            for key, nested in value.items():
                if key not in {"error", "errors"} and isinstance(nested, (dict, list, tuple)):
                    visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)

    visit(payload)
    return list(dict.fromkeys(messages))


def record_domain_refresh(state: MutableMapping[str, Any], domain: str, report: dict | None) -> None:
    payload = dict(report or {})
    mode = str(payload.get("source_mode") or payload.get("refresh_status") or "completed")
    label = "All domains" if domain == ALL_DOMAIN_REFRESH else DOMAIN_REFRESH_LABELS.get(domain, domain)
    errors = refresh_errors(payload)
    state["last_domain_refresh"] = {
        "domain": domain,
        "label": label,
        "source_mode": mode,
        "completed_at_utc": utc_now().isoformat(),
        "errors": errors,
    }
    state["developer_last_operation"] = {
        "kind": "domain_refresh",
        "label": label,
        "status": "completed" if not errors else "completed_with_warnings",
        "at_utc": utc_now().isoformat(),
        "errors": errors,
    }
