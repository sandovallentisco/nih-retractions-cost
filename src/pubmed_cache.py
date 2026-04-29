# =============================================================================
# PUBMED METADATA CACHE
# =============================================================================
# Persistent cache of ``get_pubmed_metadata`` results so that subsequent
# pipeline runs only need to hit the NCBI Entrez API for DOIs/PMIDs that
# have not been resolved before. With a populated cache the cold-start cost
# of step 1 (~1.5 hours on a fresh checkout) collapses to a few minutes.
#
# Cache schema (data/processed/pubmed_cache.csv):
#
#   cache_key      str   Canonical identifier; "doi:<doi>" or "pmid:<pmid>"
#   query_doi      str   Normalised DOI as it appeared in the input row
#   query_pmid     str   Normalised PMID as it appeared in the input row
#   PubMed_ID      str   Resolved PMID (or error marker)
#   Study_Design   str   Semicolon-joined publication types
#   Funding_Info   str   "Agency (GrantID); ..." (matches the final CSV)
#   fetched_at     str   ISO-8601 UTC timestamp of the original fetch
# =============================================================================
from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.config import BASE_DIR

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
CACHE_FILE = Path(BASE_DIR) / "data" / "processed" / "pubmed_cache.csv"

CACHE_COLUMNS = [
    "cache_key", "query_doi", "query_pmid",
    "PubMed_ID", "Study_Design", "Funding_Info",
    "fetched_at",
]

# Marker values that indicate a transient or unresolvable failure rather
# than a genuine PubMed record. Such results are never written to the cache
# so that the next run will retry the call.
NON_CACHEABLE_PMIDS = {"No valid DOI or PMID", "Error", ""}


# ---------------------------------------------------------------------------
# Identifier normalisation
# ---------------------------------------------------------------------------
def _norm_doi(doi) -> str:
    """Return a canonical lowercased DOI, or empty string if not usable."""
    if doi is None:
        return ""
    if isinstance(doi, float) and pd.isna(doi):
        return ""
    s = str(doi).strip().lower()
    return "" if s in {"", "nan", "none"} else s


def _norm_pmid(pmid) -> str:
    """Return a canonical PMID string (digits only), or empty if not usable."""
    if pmid is None:
        return ""
    if isinstance(pmid, float) and pd.isna(pmid):
        return ""
    # Pandas often loads PMIDs as floats (e.g. "12345.0"); strip the suffix.
    s = str(pmid).split(".")[0].strip()
    return "" if s in {"", "0", "nan", "none"} else s


def make_cache_key(doi, pmid) -> Optional[str]:
    """Build the canonical cache key for a (doi, pmid) pair.

    DOIs are preferred because they are globally unique and immutable;
    PMIDs are used only as a fallback. Returns ``None`` when neither
    identifier is usable, in which case the row should not be cached.
    """
    d = _norm_doi(doi)
    if d:
        return f"doi:{d}"
    p = _norm_pmid(pmid)
    if p:
        return f"pmid:{p}"
    return None


# ---------------------------------------------------------------------------
# In-memory cache backed by a CSV
# ---------------------------------------------------------------------------
class PubMedCache:
    """Thread-safe lookup table for PubMed responses.

    Thread safety is more than is strictly required by the current
    single-threaded pipeline, but it keeps the API future-proof for any
    parallelisation work and removes a class of subtle bugs.

    Typical usage::

        cache = PubMedCache.load()
        hit = cache.get(doi, pmid)
        if hit is None:
            pmid_resolved, design, funding = get_pubmed_metadata(doi, pmid)
            cache.put(doi, pmid, pmid_resolved, design, funding_str)
        cache.save()
    """

    def __init__(self, path: Path = CACHE_FILE):
        self.path = path
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, str]] = {}
        self._dirty_since_save = 0

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = CACHE_FILE) -> "PubMedCache":
        """Load the cache from disk, or return an empty cache if no file exists."""
        instance = cls(path)
        if path.exists():
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            for col in CACHE_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            for _, row in df.iterrows():
                key = row["cache_key"]
                if key:
                    instance._rows[key] = {col: row[col] for col in CACHE_COLUMNS}
            print(f"[cache] Loaded {len(instance._rows)} entries from {path}")
        else:
            print(f"[cache] No cache at {path}; starting fresh")
        return instance

    def save(self) -> None:
        """Write the entire cache to disk atomically."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(list(self._rows.values()), columns=CACHE_COLUMNS)
            df.to_csv(self.path, index=False)
            self._dirty_since_save = 0
            print(f"[cache] Saved {len(df)} entries to {self.path}")

    def maybe_autosave(self, every: int = 200) -> None:
        """Persist the cache after every ``every`` writes.

        Provides cheap insurance against losing progress to a crash or a
        Ctrl+C in the middle of the long step 1 run.
        """
        if self._dirty_since_save >= every:
            self.save()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, doi, pmid) -> Optional[Dict[str, str]]:
        """Return the cached row for a (doi, pmid) pair, or ``None`` on miss."""
        key = make_cache_key(doi, pmid)
        if key is None:
            return None
        with self._lock:
            return self._rows.get(key)

    def put(self, doi, pmid_input, resolved_pmid: str,
            study_design: str, funding_info: str) -> None:
        """Insert a successful PubMed response into the cache.

        Transient failures are intentionally not cached so that the next run
        gets another opportunity to resolve them. The two cases skipped are
        sentinel PMIDs in :data:`NON_CACHEABLE_PMIDS` and study-design
        strings that begin with the marker ``"Error:"``.
        """
        if resolved_pmid in NON_CACHEABLE_PMIDS:
            return
        if isinstance(study_design, str) and study_design.startswith("Error:"):
            return

        key = make_cache_key(doi, pmid_input)
        if key is None:
            return

        with self._lock:
            self._rows[key] = {
                "cache_key": key,
                "query_doi": _norm_doi(doi),
                "query_pmid": _norm_pmid(pmid_input),
                "PubMed_ID": str(resolved_pmid),
                "Study_Design": str(study_design),
                "Funding_Info": str(funding_info),
                "fetched_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            self._dirty_since_save += 1

    def __len__(self) -> int:
        return len(self._rows)
