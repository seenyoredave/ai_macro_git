#!/usr/bin/env python3
"""Retained Water cache must invalidate when any retained Water file changes."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("streamlit")

    class _CacheData:
        def __call__(self, *args, **kwargs):
            def decorate(fn):
                fn.clear = lambda: None
                return fn
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return decorate(args[0])
            return decorate

    stub.cache_data = _CacheData()
    sys.modules["streamlit"] = stub

import loaders.water_loader as water_loader  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        retained = Path(tmp) / "retained.csv"
        retained.write_text("x\n1\n", encoding="utf-8")

        original_files = water_loader.RETAINED_WATER_FILES
        original_cached = water_loader._load_water_utilization_data_cached
        calls: list[tuple[tuple[str, int, int], ...]] = []

        def fake_cached(force_refresh, refresh_token, allow_live, retained_fingerprint):
            del force_refresh, refresh_token, allow_live
            calls.append(retained_fingerprint)
            return {"fingerprint": retained_fingerprint}

        try:
            water_loader.RETAINED_WATER_FILES = (retained,)
            water_loader._load_water_utilization_data_cached = fake_cached

            first = water_loader.load_water_utilization_data()
            time.sleep(0.002)
            retained.write_text("x\n1\n2\n", encoding="utf-8")
            second = water_loader.load_water_utilization_data()
        finally:
            water_loader.RETAINED_WATER_FILES = original_files
            water_loader._load_water_utilization_data_cached = original_cached

        if len(calls) != 2:
            raise AssertionError("Water loader did not recompute its retained bundle fingerprint")
        if first["fingerprint"] == second["fingerprint"]:
            raise AssertionError("Water retained cache key did not change after a retained file changed")

    source = (ROOT / "loaders" / "water_loader.py").read_text(encoding="utf-8")
    if "retained_water_fingerprint()" not in source:
        raise AssertionError("Water loader does not bind retained file state into the Streamlit cache key")
    if "load_water_utilization_data.clear = _clear_water_loader_cache" not in source:
        raise AssertionError("Water loader lost explicit cache-clear compatibility")

    print("PASS  Water retained cache · file changes invalidate cached loader payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
