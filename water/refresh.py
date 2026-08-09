from __future__ import annotations

from datetime import date
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_bytes
from helpers.build_water_ledger import build as rebuild_water_ledger
from water.eia_thermoelectric import load_raw_frame

ROOT = Path(__file__).resolve().parents[1]
WATER_PAGE_URL = "https://www.eia.gov/electricity/data/water/"
SUPPORTED_YEAR = 2024
RAW_EIA = ROOT / "data/water/raw/eia/Cooling_Boiler_Generator_Data_Summary_2024.xlsx"


def _latest_summary_url(html: str) -> tuple[int, str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        match = re.search(r"Cooling_Boiler_Generator_Data_Summary_(\d{4})\.xlsx", href, re.I)
        if match:
            candidates.append((int(match.group(1)), urljoin(WATER_PAGE_URL, href)))
    if not candidates:
        raise ValueError("EIA water page exposed no summary workbook link")
    return max(candidates, key=lambda item: item[0])


def refresh_water_sources(*, timeout: int = 90) -> dict:
    """Refresh the active EIA thermoelectric source and rebuild the water ledger."""
    if not repository_writes_enabled():
        return {
            "source_mode": "read_only",
            "error": "Water refresh is available only in developer mode.",
        }
    try:
        page = requests.get(
            WATER_PAGE_URL,
            timeout=30,
            headers={"User-Agent": "ai-macro-water-refresh/1.0"},
        )
        page.raise_for_status()
        year, workbook_url = _latest_summary_url(page.text)
        if year != SUPPORTED_YEAR:
            raise RuntimeError(
                f"EIA published a {year} workbook; parser review is required before replacing the validated {SUPPORTED_YEAR} contract"
            )
        response = requests.get(
            workbook_url,
            timeout=timeout,
            headers={"User-Agent": "ai-macro-water-refresh/1.0"},
        )
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(response.content)
        try:
            validated = load_raw_frame(temporary)
            if validated.empty:
                raise ValueError("EIA water workbook validated but contained no records")
        finally:
            temporary.unlink(missing_ok=True)
        atomic_write_bytes(response.content, RAW_EIA)
        summary = rebuild_water_ledger(
            quiet=True,
            eia_retrieval_date=date.today().isoformat(),
        )
        return {
            "source_mode": "live_refresh",
            "year": year,
            "workbook_url": workbook_url,
            "raw_rows": int(len(validated)),
            "observation_rows": int(summary.get("observation_rows", 0) or 0),
            "error": None,
        }
    except Exception as exc:
        return {
            "source_mode": "retained_fallback",
            "year": SUPPORTED_YEAR,
            "error": f"{type(exc).__name__}: {exc}",
        }
