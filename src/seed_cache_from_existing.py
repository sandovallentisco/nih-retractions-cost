# =============================================================================
# CACHE SEEDING UTILITY
# =============================================================================
# One-shot helper that backfills the PubMed cache from a previously
# completed pipeline run, without making any new network requests.
#
# It reads the file produced by step 1 of the pipeline
# (``data/processed/retraction_watch_with_funding.csv``) and replays each
# row into :class:`src.pubmed_cache.PubMedCache`. Once the cache is on disk
# and committed to the repository, the first scheduled run on GitHub
# Actions starts with a hot cache and finishes step 1 in minutes instead
# of the ~1.5 hour cold-start cost.
#
# Usage::
#
#     python -m src.seed_cache_from_existing
#
# Filtering rules
# ---------------
# Rows with the following PubMed_ID values are intentionally not seeded so
# that the next real run will retry them:
#     * ``"Pending"``        - placeholder written by ``data_handler``
#     * ``"Error"``          - transient Entrez failure
#     * ``"No valid DOI ..."``- could not resolve the row at all
#     * Any ``Study_Design`` starting with ``"Error:"``
# =============================================================================
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.config import BASE_DIR
from src.pubmed_cache import (
    CACHE_FILE,
    PubMedCache,
    NON_CACHEABLE_PMIDS,
    make_cache_key,
)

INPUT_CSV = Path(BASE_DIR) / "data" / "processed" / "retraction_watch_with_funding.csv"

# Columns that the seeder needs to be present in the input CSV. If any are
# missing the script aborts cleanly with a descriptive message.
REQUIRED_COLS = {
    "OriginalPaperDOI", "OriginalPaperPubMedID",
    "PubMed_ID", "Study_Design", "Funding_Info",
}

# Sentinel values written by ``data_handler.load_and_filter_data`` for
# rows that have not yet been processed. Treated identically to the
# Entrez error markers and skipped during seeding.
PENDING_VALUES = {"Pending", "pending", "", "nan", "None"}


def _is_skippable(pmid, design) -> bool:
    """Return True when a row should NOT be inserted into the cache.

    Skipped categories:
        * ``Pending`` placeholder (row never reached PubMed in the prior run).
        * Sentinel error markers from :data:`NON_CACHEABLE_PMIDS`.
        * ``Study_Design`` strings beginning with ``"Error:"`` which encode
          a transient Entrez failure.
    """
    if pd.isna(pmid) or str(pmid).strip() in PENDING_VALUES:
        return True
    if str(pmid) in NON_CACHEABLE_PMIDS:
        return True
    if isinstance(design, str) and design.startswith("Error:"):
        return True
    return False


def seed_cache(input_csv: Path = INPUT_CSV,
               cache_path: Path = CACHE_FILE) -> int:
    """Populate the cache from ``input_csv``. Returns shell exit code."""
    if not input_csv.exists():
        print(f"[seed] ERROR: {input_csv} not found")
        print("[seed] Run the pipeline at least once before seeding the cache.")
        return 1

    print(f"[seed] Reading {input_csv}")
    # Match the lenient read settings used by ``funding_cleaner_linker``:
    # the file may use ',' or ';' as separator, and embedded delimiters
    # inside quoted fields are common (author lists with commas, etc.).
    # ``on_bad_lines='skip'`` tolerates the rare malformed row.
    df = pd.read_csv(
        input_csv,
        dtype=str,
        keep_default_na=False,
        sep=None,
        engine="python",
        on_bad_lines="skip",
        encoding="utf-8",
    )

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        print(f"[seed] ERROR: input CSV is missing required columns: {missing}")
        return 1

    print(f"[seed] {len(df)} rows in input")

    cache = PubMedCache.load(cache_path)
    pre = len(cache)

    n_seeded = 0
    n_skipped = 0
    n_no_key = 0
    for _, row in df.iterrows():
        doi = row.get("OriginalPaperDOI", "")
        pmid_in = row.get("OriginalPaperPubMedID", "")
        resolved_pmid = row.get("PubMed_ID", "")
        design = row.get("Study_Design", "")
        funding = row.get("Funding_Info", "")

        if make_cache_key(None, pmid_in) is None:
            n_no_key += 1
            continue

        if _is_skippable(resolved_pmid, design):
            n_skipped += 1
            continue

        cache.put(None, pmid_in, resolved_pmid, design, funding)
        n_seeded += 1

    cache.save()
    post = len(cache)

    print("-" * 60)
    print(f"[seed] Rows seeded:                  {n_seeded}")
    print(f"[seed] Rows skipped (Pending/Error): {n_skipped}")
    print(f"[seed] Rows without DOI or PMID:     {n_no_key}")
    print(f"[seed] Cache before:                 {pre} entries")
    print(f"[seed] Cache after:                  {post} entries (+{post - pre})")
    print(f"[seed] Cache file:                   {cache_path}")
    print("-" * 60)
    print("[seed] Done. Commit the cache so CI starts warm:")
    print('       git add data/processed/pubmed_cache.csv')
    print('       git commit -m "chore: seed PubMed cache from existing run"')
    print("       git push")
    return 0


if __name__ == "__main__":
    sys.exit(seed_cache())
