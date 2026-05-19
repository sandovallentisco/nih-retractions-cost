# =============================================================================
# STEP 1 - PUBMED METADATA FETCHER (PIPELINE STAGE)
# =============================================================================
# Iterates the filtered Retraction Watch dataframe and asks PubMed for the
# study design and grant list of every paper. The original implementation
# called Entrez for every row on every run; this version checks an on-disk
# cache (:mod:`src.pubmed_cache`) first so that subsequent runs only query
# the API for DOIs/PMIDs that were not previously resolved.
#
# Practical impact
# ----------------
# * Cold cache (first run, or after a manual cache wipe): ~1.5 hours.
# * Warm cache (every quarterly cron after the first): a few minutes -
#   exactly proportional to the number of new retractions added by
#   Retraction Watch since the previous run.
# =============================================================================
from __future__ import annotations

import time

from tqdm import tqdm

from src.config import INPUT_FILE, OUTPUT_FILE
from src.data_handler import load_and_filter_data, save_data
from src.entrez_client import get_pubmed_metadata
from src.pubmed_cache import PubMedCache

# Approximate rate limit applied between *real* PubMed calls, ~3 req/s.
# Cache hits skip the sleep entirely.
NCBI_SLEEP_SECONDS = 0.35

# Persist the cache to disk every N successful new fetches so that an
# unexpected crash or Ctrl+C cannot lose all the work.
AUTOSAVE_EVERY = 200


def _format_funding(fund_list) -> str:
    """Render the list of grant dictionaries into the canonical string used
    in the final CSV: ``"Agency (GrantID); Agency (GrantID); ..."``."""
    return "; ".join(
        f"{f.get('Agency', 'Unknown Agency')} ({f.get('GrantID', 'No ID')})"
        for f in fund_list
    )


def run_pipeline() -> None:
    """Execute step 1.

    The function is wrapped in a ``try/finally`` block so that the cache
    and the in-progress dataframe are always flushed to disk, even if the
    user aborts with Ctrl+C or an unhandled exception is raised inside the
    Entrez call.
    """
    # ------------------------------------------------------------------
    # Load and filter the source CSV. ``load_and_filter_data`` keeps only
    # USA-affiliated retractions and drops publisher-error-only rows.
    # ------------------------------------------------------------------
    us_studies = load_and_filter_data(INPUT_FILE)

    # Load the persistent cache (empty on the very first run).
    cache = PubMedCache.load()

    print("2. Querying PubMed (Ctrl+C performs a safe shutdown)...")

    n_hits = 0
    n_misses = 0

    try:
        for index, row in tqdm(us_studies.iterrows(),
                               total=len(us_studies),
                               desc="Fetching"):

            doi = row.get("OriginalPaperDOI", None)
            provided_pmid = row.get("OriginalPaperPubMedID", None)

            # --------------------------------------------------------------
            # Fast path: cache hit. No network call, no sleep.
            # --------------------------------------------------------------
            cached = cache.get(None, provided_pmid)
            if cached is not None:
                us_studies.at[index, "PubMed_ID"] = cached["PubMed_ID"]
                us_studies.at[index, "Study_Design"] = cached["Study_Design"]
                us_studies.at[index, "Funding_Info"] = cached["Funding_Info"]
                n_hits += 1
                continue

            # --------------------------------------------------------------
            # Slow path: query PubMed and update both the dataframe and
            # the cache.
            # --------------------------------------------------------------
            pmid, design, fund_list = get_pubmed_metadata(provided_pmid)
            funding_str = _format_funding(fund_list)

            tqdm.write(
                f"Retrieved -> PMID: {pmid} | "
                f"Info: {str(design)[:40]}... | Funding: {funding_str[:40]}..."
            )

            us_studies.at[index, "PubMed_ID"] = pmid
            us_studies.at[index, "Study_Design"] = design
            us_studies.at[index, "Funding_Info"] = funding_str

            # The cache layer transparently rejects transient errors so we
            # do not pollute the cache with failures that should be retried.
            cache.put(None, provided_pmid, pmid, design, funding_str)
            n_misses += 1

            cache.maybe_autosave(every=AUTOSAVE_EVERY)
            time.sleep(NCBI_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\n\n[!] Interrupted by user. Persisting partial state...")

    except Exception as exc:
        print(f"\n\n[!] Unhandled exception: {exc}. Persisting partial state...")

    finally:
        # Always flush both artefacts: the cache (so the next run is fast)
        # and the partially-filled dataframe (so we never lose progress).
        cache.save()
        save_data(us_studies, OUTPUT_FILE)
        print(
            f"[pipeline] cache hits: {n_hits} | "
            f"new fetches: {n_misses} | total cache size: {len(cache)}"
        )
        print("Pipeline execution finished.")
