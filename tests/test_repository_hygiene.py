from pathlib import Path
import ast

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".csv"}
RETIRED_TERMS = (
    "borrower " + "financial condition",
    "borrower_" + "financial_condition",
    "borrower " + "condition",
    "borrower_" + "condition",
    "credit " + "stress",
    "credit_" + "stress",
    "credit " + "intermediation " + "stress",
    "credit " + "intermediation " + "strain",
    "intermediation_" + "stress",
    "intermediation_" + "strain",
    "capital " + "stress",
    "capital_" + "stress",
    "debt capacity " + "stress",
    "trip" + "wire",
)


def _authored_text():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__", ".cache", ".venv"} for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {".gitignore", "requirements.txt"}:
            continue
        yield path, path.read_text(encoding="utf-8", errors="ignore").lower()


def test_retired_product_names_are_absent():
    violations = []
    for path, text in _authored_text():
        for term in RETIRED_TERMS:
            if term in text:
                violations.append(f"{path.relative_to(ROOT)}: {term}")
    assert not violations, "Retired terminology found:\n" + "\n".join(violations)


def test_current_build_label_is_exact():
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "v4.09"' in app
    assert app.count("APP_VERSION =") == 1


def test_archives_use_current_credit_condition_schema():
    macro = pd.read_csv(ROOT / "archive" / "macro_history.csv", nrows=0)
    columns = set(macro.columns)
    assert "Borrower Strain" in columns
    assert "Lender Strain" in columns
    assert "Borrower Strain Version" in columns
    assert "Lender Strain Version" in columns
    assert ("Borrower " + "Financial Condition") not in columns
    assert ("Credit " + "Intermediation " + "Strain") not in columns
    assert "Borrower Book Leverage" not in columns


def test_latest_archive_sector_names_match_current_configuration():
    from config.sector_config import SECTOR_CONFIG

    allowed = set(SECTOR_CONFIG)
    for name in ("sector_history.csv", "yf_history.csv"):
        frame = pd.read_csv(ROOT / "archive" / name)
        dates = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
        latest = frame.loc[dates.eq(dates.max())]
        assert set(latest["Sector"].dropna().astype(str)).issubset(allowed)


def test_every_plotly_chart_has_an_explicit_key():
    violations = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__", ".cache", ".venv"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "plotly_chart"
            ):
                continue
            if not any(keyword.arg == "key" for keyword in node.keywords):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not violations, "Plotly charts without explicit keys:\n" + "\n".join(violations)
