"""Import the complete public rendering graph under a minimal Streamlit shim."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def cache_resource(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules["streamlit"] = _FakeStreamlit()


def main() -> None:
    module = importlib.import_module("rendering.dashboard")
    renderer = getattr(module, "render_research_dashboard", None)
    if not callable(renderer):
        raise AssertionError("Dashboard renderer did not import cleanly.")

    evidence = importlib.import_module("rendering.evidence")
    payload = getattr(evidence, "_water_evidence_payload", None)
    if not callable(payload) or payload(None) != {}:
        raise AssertionError("Evidence Water payload normalization is unavailable.")

    print("PASS  complete rendering import graph")


if __name__ == "__main__":
    main()
