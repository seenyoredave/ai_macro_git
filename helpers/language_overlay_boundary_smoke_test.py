"""Stop-the-line contract for the OpenAI language overlay boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub

install_streamlit_stub()

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.domain_state import DOMAIN_ORDER, DomainState  # noqa: E402
from analytics import read_service  # noqa: E402
from analytics.read_evidence import build_evidence_packets  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_adapter_import_boundary() -> None:
    path = ROOT / "analytics" / "read_evidence.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    allowed_analytics = {
        "analytics.dashboard_context",
        "analytics.domain_state",
    }
    forbidden_modules = {"pandas", "numpy"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                _check(root not in forbidden_modules, f"Language evidence imported analytical dependency: {alias.name}")
                if alias.name.startswith("analytics."):
                    _check(alias.name in allowed_analytics, f"Language evidence imported analytical engine: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            root = module.split(".", 1)[0]
            _check(root not in forbidden_modules, f"Language evidence imported analytical dependency: {module}")
            if module.startswith("analytics."):
                _check(module in allowed_analytics, f"Language evidence imported analytical engine: {module}")



def _check_core_does_not_depend_on_language() -> None:
    path = ROOT / "analytics" / "domain_state.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_fragments = ("read_", "language", "openai")
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(str(node.module or ""))
        for module in modules:
            lowered = module.casefold()
            _check(
                not any(fragment in lowered for fragment in forbidden_fragments),
                f"Deterministic domain state depends on language/OpenAI code: {module}",
            )

def _check_fail_closed_without_state() -> None:
    try:
        build_evidence_packets(DashboardContext())
    except ValueError as exc:
        _check("canonical deterministic domain state" in str(exc), "Missing-state failure lost the canonical-state boundary.")
    else:
        raise AssertionError("Language evidence reconstructed analytical state instead of failing closed.")


def _check_finished_state_is_sufficient() -> None:
    states = {domain: DomainState() for domain in DOMAIN_ORDER}
    packets = build_evidence_packets(DashboardContext(domain_states=states))
    _check(tuple(packets) == DOMAIN_ORDER, "Finished deterministic state no longer maps one-to-one to evidence domains.")
    _check(all(not packet.facts for packet in packets.values()), "Empty finished state unexpectedly created analytical facts.")


def _check_normal_reader_does_not_rebuild_evidence() -> None:
    artifact = {
        "status": "validated",
        "service_version": read_service.READ_SERVICE_VERSION,
        "validation": {"passed": True},
        "evidence_snapshot_id": "stored-evidence-snapshot",
        "evidence_packets": {},
        "reads": {},
    }
    original = read_service.build_evidence_packets

    def forbidden(_context):
        raise AssertionError("Normal Reader rendering rebuilt language evidence.")

    read_service.build_evidence_packets = forbidden
    try:
        _reads, status = read_service.build_platform_reads(DashboardContext(), artifact=artifact)
    finally:
        read_service.build_evidence_packets = original

    _check(status.get("artifact_publishable") is True, "Fixture did not exercise the publishable Reader path.")
    _check(status.get("evidence_snapshot_id") == "stored-evidence-snapshot", "Reader lost the stored evidence identity.")


def main() -> int:
    _check_adapter_import_boundary()
    _check_core_does_not_depend_on_language()
    _check_fail_closed_without_state()
    _check_finished_state_is_sufficient()
    _check_normal_reader_does_not_rebuild_evidence()
    print("PASS  language overlay boundary · core independent · no analytical engines in adapter · canonical state required · normal Reader does not rebuild evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
