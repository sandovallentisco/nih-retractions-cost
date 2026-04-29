# =============================================================================
# AUTOMATED RAW-DATA DOWNLOADER
# =============================================================================
# Downloads the three external sources the project depends on, with no user
# interaction:
#
#   1) retraction_watch.csv                    (Retraction Watch DB on GitLab)
#   2) RePORTER_PRJ_C_FY{year}.zip             (NIH ExPORTER, annual project data)
#   3) RePORTER_PRJFUNDING_C_FY1985_1999.zip   (NIH ExPORTER, historical funding)
#
# This module is the entrypoint that allows the entire pipeline to run in a
# fully unattended environment such as the GitHub Actions cron defined in
# ``.github/workflows/quarterly_update.yml``.
#
# Usage::
#
#     python -m src.downloader              # incremental mode (default)
#     python -m src.downloader --full       # full setup, all years from 1985
#     python -m src.downloader --rw-only    # only Retraction Watch
#     python -m src.downloader --nih-only   # only NIH ExPORTER
# =============================================================================
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import List, Optional

import requests

from src.config import BASE_DIR

# ---------------------------------------------------------------------------
# Configurable URLs. Override via environment variables when the canonical
# upstream paths change without requiring a code edit.
# ---------------------------------------------------------------------------
# Retraction Watch on GitLab (Crossref). Right-click the file in the GitLab
# UI and choose "Raw" to obtain this exact URL.
RW_GITLAB_RAW_URL = os.environ.get(
    "RW_GITLAB_RAW_URL",
    "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv",
)

# NIH ExPORTER, annual project ZIPs. ``{year}`` is substituted with the
# integer fiscal year.
NIH_EXPORTER_PRJ_TMPL = os.environ.get(
    "NIH_EXPORTER_URL_TMPL",
    "https://reporter.nih.gov/exporter/RePORTER_PRJ_C_FY{year}.zip",
)

# NIH ExPORTER, historical funding/DUNS archive. A single ZIP that bundles
# the 15 yearly CSVs covering FY 1985-1999.
NIH_EXPORTER_FUNDING_URL = os.environ.get(
    "NIH_EXPORTER_FUNDING_URL",
    "https://reporter.nih.gov/exporter/RePORTER_PRJFUNDING_C_FY1985_1999.zip",
)

# Optional Personal Access Token for private GitLab repositories.
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "").strip()

# Earliest fiscal year published by NIH ExPORTER.
FIRST_FISCAL_YEAR = 1985

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
RW_DIR = Path(BASE_DIR) / "data" / "raw" / "retraction_watch"
RW_FILE = RW_DIR / "retraction_watch.csv"
NIH_DIR = Path(BASE_DIR) / "data" / "raw" / "nih_reporter"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _current_fiscal_year(today: Optional[dt.date] = None) -> int:
    """Return the current NIH fiscal year.

    NIH fiscal years roll over on October 1st, so any date in October,
    November or December belongs to the *next* calendar year's FY.
    """
    today = today or dt.date.today()
    return today.year + 1 if today.month >= 10 else today.year


def _extract_zip_to_nih_dir(zip_bytes: bytes) -> List[Path]:
    """Extract every CSV inside ``zip_bytes`` into ``data/raw/nih_reporter/``.

    Returns the list of files written. Non-CSV entries (READMEs, etc.) are
    silently ignored.
    """
    NIH_DIR.mkdir(parents=True, exist_ok=True)
    out: List[Path] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            target = NIH_DIR / Path(name).name
            with zf.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(target)
            print(f"[downloader]   extracted {target.name}")
    return out


def _http_get(url: str, timeout: int = 600) -> Optional[bytes]:
    """GET helper that logs failures instead of raising.

    Returning ``None`` on failure lets the caller decide whether to abort or
    continue with the remaining downloads.
    """
    print(f"[downloader] GET {url}")
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.HTTPError as exc:
        print(f"[downloader]   HTTP error: {exc}")
    except requests.RequestException as exc:
        print(f"[downloader]   network error: {exc}")
    return None


# ---------------------------------------------------------------------------
# Retraction Watch
# ---------------------------------------------------------------------------
def download_retraction_watch(url: str = RW_GITLAB_RAW_URL,
                              dest: Path = RW_FILE) -> Path:
    """Download ``retraction_watch.csv`` from GitLab and write it to ``dest``.

    For private GitLab repositories, set the environment variable
    ``GITLAB_TOKEN`` to a Personal Access Token; it is forwarded as the
    ``PRIVATE-TOKEN`` HTTP header.
    """
    headers = {}
    if GITLAB_TOKEN:
        headers["PRIVATE-TOKEN"] = GITLAB_TOKEN

    print(f"[downloader] GET {url}")
    response = requests.get(url, headers=headers, timeout=180)
    response.raise_for_status()

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    size_mb = dest.stat().st_size / (1024 * 1024)
    print(f"[downloader] Saved {dest} ({size_mb:.2f} MB)")
    return dest


# ---------------------------------------------------------------------------
# NIH ExPORTER - annual project data
# ---------------------------------------------------------------------------
def _prj_csv_path(year: int) -> Path:
    return NIH_DIR / f"RePORTER_PRJ_C_FY{year}.csv"


def download_nih_year(year: int, force: bool = False) -> Optional[Path]:
    """Download and unzip the annual ExPORTER project data for ``year``.

    By default the function is idempotent: if the destination CSV already
    exists, the download is skipped. Set ``force=True`` to re-download
    (typically for the current FY, which NIH refreshes quarterly).
    """
    out_csv = _prj_csv_path(year)
    if out_csv.exists() and not force:
        print(f"[downloader] FY{year}: already on disk, skipping")
        return out_csv

    url = NIH_EXPORTER_PRJ_TMPL.format(year=year)
    payload = _http_get(url)
    if payload is None:
        return None

    extracted = _extract_zip_to_nih_dir(payload)
    return extracted[0] if extracted else None


def download_all_nih_years(first_year: int = FIRST_FISCAL_YEAR,
                           force_current: bool = True) -> List[Path]:
    """Download every fiscal year from ``first_year`` through the current FY.

    Years already present locally are skipped, except the current FY when
    ``force_current`` is true (so quarterly upstream updates are picked up).
    Designed for a one-shot initial setup.
    """
    fy_now = _current_fiscal_year()
    out: List[Path] = []
    for year in range(first_year, fy_now + 1):
        force = force_current and year == fy_now
        path = download_nih_year(year, force=force)
        if path is not None:
            out.append(path)
    return out


def download_recent_nih_years(n_back: int = 2,
                              force_current: bool = True) -> List[Path]:
    """Download the current fiscal year plus ``n_back`` previous years.

    Designed for the recurring quarterly cron: only the moving window of
    recent years is refreshed because older NIH data does not change.
    """
    fy_now = _current_fiscal_year()
    out: List[Path] = []
    for offset in range(0, n_back + 1):
        year = fy_now - offset
        force = force_current and offset == 0
        path = download_nih_year(year, force=force)
        if path is not None:
            out.append(path)
    return out


# ---------------------------------------------------------------------------
# NIH ExPORTER - historical funding/DUNS (1985-1999)
# ---------------------------------------------------------------------------
def download_funding_history(force: bool = False) -> List[Path]:
    """Download the historical funding/DUNS ZIP if any of its 15 CSVs is missing.

    The archive bundles ``RePORTER_PRJFUNDING_C_FY1985.csv`` through
    ``..._FY1999.csv``. Because NIH does not modify these historical files
    after publication, the function is a no-op once the local set is
    complete (override with ``force=True`` if needed).
    """
    needed_years = range(1985, 2000)
    missing = [
        y for y in needed_years
        if not (NIH_DIR / f"RePORTER_PRJFUNDING_C_FY{y}.csv").exists()
    ]
    if not missing and not force:
        print("[downloader] Funding history (1985-1999): already complete, skipping")
        return []

    payload = _http_get(NIH_EXPORTER_FUNDING_URL)
    if payload is None:
        return []
    return _extract_zip_to_nih_dir(payload)


# ---------------------------------------------------------------------------
# Orchestration + CLI
# ---------------------------------------------------------------------------
def run(mode: str = "incremental",
        rw: bool = True,
        nih: bool = True,
        n_back: int = 2) -> int:
    """Programmatic entry point.

    Parameters
    ----------
    mode:
        ``"incremental"`` -> current FY plus ``n_back`` previous years
        (used by the quarterly cron). ``"full"`` -> every year from
        1985 onwards plus the historical funding archive (initial setup).
    rw, nih:
        Toggle Retraction Watch and NIH downloads independently. Used by
        the ``--rw-only`` and ``--nih-only`` CLI flags.
    n_back:
        Number of previous fiscal years to refresh in incremental mode.
    """
    print("=" * 70)
    print(f"AUTOMATED DOWNLOADER ({mode})".center(70))
    print("=" * 70)
    try:
        if rw:
            download_retraction_watch()
        if nih:
            if mode == "full":
                download_all_nih_years(force_current=True)
                download_funding_history(force=False)
            else:  # incremental
                download_recent_nih_years(n_back=n_back, force_current=True)
                # In case a previous setup did not complete the historical archive.
                download_funding_history(force=False)
    except Exception as exc:
        print(f"[downloader] ERROR: {exc}")
        return 1
    print("[downloader] Done.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Retraction Watch (GitLab) and NIH ExPORTER raw files.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Initial setup: download every fiscal year from 1985 plus historical funding archive.",
    )
    mode_group.add_argument(
        "--incremental",
        action="store_true",
        help="(Default) current FY plus N previous years. Designed for the quarterly cron.",
    )
    parser.add_argument("--rw-only", action="store_true",
                        help="Download Retraction Watch only.")
    parser.add_argument("--nih-only", action="store_true",
                        help="Download NIH ExPORTER only.")
    parser.add_argument("--n-back", type=int, default=2,
                        help="Number of previous fiscal years to refresh in incremental mode.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    mode = "full" if args.full else "incremental"
    rw = not args.nih_only
    nih = not args.rw_only
    return run(mode=mode, rw=rw, nih=nih, n_back=args.n_back)


if __name__ == "__main__":
    sys.exit(main())
