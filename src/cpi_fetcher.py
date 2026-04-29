# =============================================================================
# FRED CPI FETCHER
# =============================================================================
# Downloads the Consumer Price Index for All Urban Consumers (CPIAUCSL) series
# from the Federal Reserve Bank of St. Louis (FRED) and writes a compact
# annual aggregate to ``data/processed/annual_cpi.csv``.
#
# Rationale:
#     The Shiny dashboard (``app.R``) historically pulled this series at
#     startup via ``quantmod::getSymbols``. That call is a hard dependency
#     on outbound network access from shinyapps.io and adds 1-3 seconds to
#     every cold start. Persisting the series as part of the quarterly
#     pipeline removes that dependency: the app simply reads a small CSV
#     committed alongside the rest of ``data/processed``.
#
# Output schema (annual_cpi.csv):
#     Fiscal_Year           int    Calendar year aggregated as fiscal year
#     CPI                   float  Annual mean of monthly CPIAUCSL values
#     Inflation_Multiplier  float  Ratio current_CPI / CPI for that year
#     fetched_at            str    ISO-8601 UTC timestamp of the download
#
# Usage:
#     python -m src.cpi_fetcher
# =============================================================================
from __future__ import annotations

import datetime as dt
import io
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from src.config import BASE_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Public CSV endpoint. Requires no API key. Returns the full monthly history
# of CPIAUCSL with two columns: ``observation_date`` and ``CPIAUCSL``.
FRED_CPI_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
)

OUTPUT_PATH = Path(BASE_DIR) / "data" / "processed" / "annual_cpi.csv"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def _download_monthly_series(url: str = FRED_CPI_URL) -> pd.DataFrame:
    """Fetch the raw monthly CPIAUCSL series from FRED.

    Returns a DataFrame with two columns: ``observation_date`` (datetime) and
    ``CPIAUCSL`` (float). Raises ``requests.HTTPError`` on non-2xx responses.
    """
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    df = pd.read_csv(io.BytesIO(response.content))

    # FRED has shipped column names in two variants over time:
    # ``observation_date`` (current) or ``DATE`` (legacy). Normalize.
    rename_map = {}
    for original in df.columns:
        normalized = original.strip().lower()
        if normalized in {"date", "observation_date"}:
            rename_map[original] = "observation_date"
        elif normalized == "cpiaucsl":
            rename_map[original] = "CPIAUCSL"
    df = df.rename(columns=rename_map)

    if "observation_date" not in df.columns or "CPIAUCSL" not in df.columns:
        raise ValueError(
            f"Unexpected FRED schema; got columns {list(df.columns)}"
        )

    df["observation_date"] = pd.to_datetime(df["observation_date"])
    df["CPIAUCSL"] = pd.to_numeric(df["CPIAUCSL"], errors="coerce")
    df = df.dropna(subset=["CPIAUCSL"])
    return df


def _aggregate_to_annual(monthly: pd.DataFrame) -> pd.DataFrame:
    """Collapse the monthly series into an annual mean and compute the
    inflation multiplier relative to the most recent annual CPI."""
    annual = (
        monthly
        .assign(Fiscal_Year=monthly["observation_date"].dt.year)
        .groupby("Fiscal_Year", as_index=False)["CPIAUCSL"]
        .mean()
        .rename(columns={"CPIAUCSL": "CPI"})
    )

    current_cpi = annual["CPI"].max()
    annual["Inflation_Multiplier"] = current_cpi / annual["CPI"]
    return annual


def fetch_cpi(output_path: Path = OUTPUT_PATH,
              url: str = FRED_CPI_URL) -> Optional[Path]:
    """Top-level pipeline step. Returns the output path on success, ``None``
    on failure (errors are logged, not raised, so the rest of the pipeline
    can continue even if FRED is temporarily unreachable)."""
    print(f"[cpi] GET {url}")
    try:
        monthly = _download_monthly_series(url)
    except Exception as exc:
        print(f"[cpi] ERROR: could not download FRED series ({exc})")
        if output_path.exists():
            print(f"[cpi] Keeping previous {output_path.name} on disk.")
        return None

    annual = _aggregate_to_annual(monthly)
    # Use a timezone-aware UTC datetime; ``utcnow`` is deprecated since
    # Python 3.12 in favour of ``now(tz=UTC)``.
    annual["fetched_at"] = (
        dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    annual.to_csv(output_path, index=False)
    print(
        f"[cpi] Wrote {len(annual)} annual rows to {output_path} "
        f"(latest fiscal year: {int(annual['Fiscal_Year'].max())})"
    )
    return output_path


def main() -> int:
    return 0 if fetch_cpi() is not None else 1


if __name__ == "__main__":
    sys.exit(main())
