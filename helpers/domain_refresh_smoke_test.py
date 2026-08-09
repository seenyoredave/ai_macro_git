"""Small regression for the v6.5.8 selective domain-refresh contracts."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import types

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules.setdefault("streamlit", _FakeStreamlit())

from loaders import adaptation_loader  # noqa: E402
from loaders import energy_market_loader  # noqa: E402
from loaders import official_series_refresh  # noqa: E402
from water.refresh import _latest_summary_url  # noqa: E402


def check_partial_series_refresh() -> None:
    retained = pd.DataFrame(
        [
            {"Date": "2025-01-01", "Value": 1.0, "Series ID": "GOOD", "Series": "Good", "Metric": "Level", "Unit": "index", "Source": "Official"},
            {"Date": "2025-01-01", "Value": 2.0, "Series ID": "FAIL", "Series": "Fail", "Metric": "Level", "Unit": "index", "Source": "Official"},
        ]
    )
    original_fetch = official_series_refresh.fetch_fred_series
    original_writes = official_series_refresh.repository_writes_enabled
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "history.csv"
        retained.to_csv(path, index=False)

        def fake_fetch(series_id: str, **kwargs):
            if series_id == "FAIL":
                raise RuntimeError("fixture failure")
            return pd.DataFrame(
                {"Date": pd.to_datetime(["2026-01-01", "2026-02-01"]), "Value": [10.0, 11.0]}
            )

        try:
            official_series_refresh.fetch_fred_series = fake_fetch
            official_series_refresh.repository_writes_enabled = lambda: True
            frame, report = official_series_refresh.refresh_templated_history(
                path,
                required_columns=("Series", "Metric", "Unit", "Source"),
            )
        finally:
            official_series_refresh.fetch_fred_series = original_fetch
            official_series_refresh.repository_writes_enabled = original_writes

        if report["source_mode"] != "partial_refresh":
            raise AssertionError(f"Partial refresh mode changed: {report}")
        good = frame.loc[frame["Series ID"].eq("GOOD")]
        fail = frame.loc[frame["Series ID"].eq("FAIL")]
        if good["Value"].tolist() != [10.0, 11.0]:
            raise AssertionError("Successful series did not replace its retained chronology.")
        if fail["Value"].tolist() != [2.0]:
            raise AssertionError("Failed series did not preserve its retained fallback.")
        persisted = pd.read_csv(path)
        if len(persisted) != 3:
            raise AssertionError("Atomic partial refresh did not persist the expected rows.")

        single_path = Path(directory) / "single.csv"
        pd.DataFrame({"Date": ["2025-01-01"], "CPI": [100.0]}).to_csv(single_path, index=False)
        try:
            official_series_refresh.fetch_fred_series = lambda *args, **kwargs: pd.DataFrame(
                columns=["Date", "Value"]
            )
            official_series_refresh.repository_writes_enabled = lambda: True
            single, single_report = official_series_refresh.refresh_single_series(
                single_path,
                series_id="EMPTY",
                output_date_column="Date",
                output_value_column="CPI",
            )
        finally:
            official_series_refresh.fetch_fred_series = original_fetch
            official_series_refresh.repository_writes_enabled = original_writes
        if single_report["source_mode"] != "retained_fallback" or single["CPI"].tolist() != [100.0]:
            raise AssertionError("An empty live series overwrote its retained fallback.")
        if pd.read_csv(single_path)["CPI"].tolist() != [100.0]:
            raise AssertionError("An empty live series changed the retained file.")


def check_grid_scope_routing() -> None:
    module = energy_market_loader
    originals = {
        name: getattr(module, name)
        for name in (
            "_load_local",
            "_get",
            "_write",
            "_latest_generator_url",
            "_latest_queue_url",
            "_parse_generators",
            "_parse_capacity_changes",
            "_parse_queue",
        )
    }
    calls: list[str] = []
    blank = pd.DataFrame({"value": [1]})

    try:
        module._load_local = lambda: {name: pd.DataFrame() for name in module.PATHS}
        module._get = lambda url: calls.append(str(url)) or b"fixture"
        module._write = lambda frame, path: None
        module._latest_generator_url = lambda: "https://official.test/generator.xlsx"
        module._latest_queue_url = lambda: "https://official.test/queue.xlsx"
        module._parse_generators = lambda content: {
            "operating_generators": blank,
            "capacity_snapshot": blank,
            "generator_pipeline": blank,
        }
        module._parse_capacity_changes = lambda additions, retirements: blank
        module._parse_queue = lambda content: {
            "interconnection_queue": blank,
            "interconnection_queue_summary": blank,
        }
        _, errors, refreshed, resolved = module._refresh("grid_storage")
    finally:
        for name, value in originals.items():
            setattr(module, name, value)

    if errors:
        raise AssertionError(f"Grid fixture produced errors: {errors}")
    if any(token in " ".join(calls) for token in ("sales_revenue", "table_1_01", "naturalgas")):
        raise AssertionError("Grid refresh crossed into Power-only sources.")
    expected = {
        "operating_generators",
        "capacity_snapshot",
        "generator_pipeline",
        "capacity_changes",
        "interconnection_queue",
        "interconnection_queue_summary",
    }
    if set(refreshed) != expected:
        raise AssertionError(f"Grid refresh datasets changed: {refreshed}")
    if set(resolved) != {"generators", "capacity_additions", "capacity_retirements", "interconnection_queue"}:
        raise AssertionError(f"Grid URL resolution changed: {resolved}")


def check_release_discovery() -> None:
    original_get = energy_market_loader.requests.get

    class Response:
        text = """
        <a href='/downloads/latest_generator2026.xlsx'>wrong</a>
        <a href='/electricity/data/eia860m/xls/june_generator2026.xlsx'>June 2026</a>
        <a href='/electricity/data/eia860m/xls/may_generator2026.xlsx'>May 2026</a>
        """

        @staticmethod
        def raise_for_status():
            return None

    try:
        energy_market_loader.requests.get = lambda *args, **kwargs: Response()
        url = energy_market_loader._discover_download_url(
            "https://www.eia.gov/electricity/data/eia860m/",
            r"/eia860m/xls/[a-z]+_generator\d{4}\.xlsx(?:$|\?)",
        )
    finally:
        energy_market_loader.requests.get = original_get
    if not url.endswith("june_generator2026.xlsx"):
        raise AssertionError(f"Newest release link was not selected: {url}")


def check_btos_sector_boundary() -> None:
    estimates = pd.DataFrame(
        [
            {"Sector": "11", "Question ID": 7, "Answer": "Yes", "202601": "10%"},
            {"Sector": "11", "Question ID": 24, "Answer": "Yes", "202601": "12%"},
            {"Sector": "Source: Census footnote", "Question ID": 7, "Answer": "Yes", "202601": ""},
        ]
    )
    errors = estimates.copy()
    errors["202601"] = "1%"
    original_read_excel = adaptation_loader.pd.read_excel
    original_cycle_dates = adaptation_loader._cycle_dates

    def fake_read_excel(content, *, sheet_name, **kwargs):
        return estimates.copy() if sheet_name == "Response Estimates" else errors.copy()

    try:
        adaptation_loader.pd.read_excel = fake_read_excel
        adaptation_loader._cycle_dates = lambda content: {"202601": pd.Timestamp("2026-01-15")}
        result = adaptation_loader.parse_btos_sector_workbook(b"fixture")
    finally:
        adaptation_loader.pd.read_excel = original_read_excel
        adaptation_loader._cycle_dates = original_cycle_dates

    if result["Sector Code"].tolist() != ["11"]:
        raise AssertionError("BTOS footnote or unknown sector leaked into the sector snapshot.")


def check_water_release_gate() -> None:
    html = """
    <a href='xls/Cooling_Boiler_Generator_Data_Summary_2023.xlsx'>2023</a>
    <a href='xls/Cooling_Boiler_Generator_Data_Summary_2025.xlsx'>2025</a>
    <a href='xls/Cooling_Boiler_Generator_Data_Summary_2024.xlsx'>2024</a>
    """
    year, url = _latest_summary_url(html)
    if year != 2025 or not url.endswith("2025.xlsx"):
        raise AssertionError("Water release discovery did not select the newest annual workbook.")


def check_sidebar_contract() -> None:
    source = (PROJECT_ROOT / "ai_macro.py").read_text(encoding="utf-8")
    expected = (
        "Current Context",
        "Compute",
        "Data Centers",
        "Connectivity",
        "Power",
        "Grid & Storage",
        "Water",
        "Adoption",
        "Workforce",
        "Economic Outcomes",
    )
    for label in expected:
        if f'"{label}"' not in source:
            raise AssertionError(f"Domain refresh label is missing: {label}")
    if "force_energy_market_refresh" in source:
        raise AssertionError("The retired global energy refresh flag returned.")
    if 'st.markdown("**Refresh data sources**")' not in source or 'st.markdown("**Refresh domains**")' not in source:
        raise AssertionError("Source and domain refresh controls are not separated.")
    if '"Refresh All Sources"' not in source:
        raise AssertionError("Refresh All Sources control is missing.")
    if 'on_click=request_all_source_refreshes' not in source:
        raise AssertionError("Refresh All Sources is not armed through a pre-rerun callback.")
    if 'on_click=request_source_refresh' not in source or 'args=("yfinance",)' not in source:
        raise AssertionError("YFinance refresh is not armed through a pre-rerun callback.")
    if source.rfind('render_developer_load_report(st.session_state.get("market_universe_load_report"))') < source.find('if st.session_state.force_rebuild:'):
        raise AssertionError("Developer load report renders before the rebuild completes.")
    if 'if st.button("Refresh YFinance"' in source:
        raise AssertionError("YFinance refresh reverted to the fragile nested-button rerun pattern.")
    if 'st.button("Refresh All Domains"' not in source:
        raise AssertionError("Refresh All Domains control is missing.")
    if "Rebuild and cache clearing stay offline" in source:
        raise AssertionError("Retired developer-tool instruction returned.")
    if 'or load_policy.allows_live(RefreshSource.GRID_STORAGE)' not in source:
        raise AssertionError("Grid & Storage refresh is not authorized through the load policy.")
    if 'st.caption("Evidence updates with the source domains above.")' not in source:
        raise AssertionError("Evidence refresh ownership is not explained.")


def main() -> None:
    checks = (
        ("Partial official-series fallback", check_partial_series_refresh),
        ("Grid refresh scope", check_grid_scope_routing),
        ("Rolling release discovery", check_release_discovery),
        ("BTOS sector boundary", check_btos_sector_boundary),
        ("Water annual-release gate", check_water_release_gate),
        ("Sidebar domain routing", check_sidebar_contract),
    )
    for label, function in checks:
        function()
        print(f"PASS  {label}")
    print(f"PASS  {len(checks)} selective domain-refresh contracts")


if __name__ == "__main__":
    main()
