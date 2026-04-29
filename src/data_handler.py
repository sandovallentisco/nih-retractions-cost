# =============================================================================
# DATA HANDLING - INPUT FILTERING AND OUTPUT EXPORT
# =============================================================================
# Loads the Retraction Watch CSV produced by :mod:`src.downloader`,
# applies the project's three filtering rules to keep only the rows that
# are in scope for the analysis, and provides a small symmetric helper
# for writing the final dataframe back to disk.
# =============================================================================
import re

import pandas as pd

# Reasons that, in isolation, indicate a publisher-side mistake rather
# than a research-integrity issue. Rows whose ``Reason`` field consists
# *exclusively* of values from this set are discarded.
_PUBLISHER_ERROR_REASONS = {
    "Error by Journal/Publisher",
    "Duplicate Publication through Error by Journal/Publisher",
    "Withdrawn (out of date)",
}


def _is_valid_reason(reason_str):
    """Return False when every reason in ``reason_str`` is a publisher error.

    NaN is considered valid (we keep rows with no reason listed).
    """
    if pd.isna(reason_str):
        return True

    # Reasons inside Retraction Watch are joined with ';' or '+'. We split
    # on either, strip whitespace, and discard empties.
    current_reasons = {
        r.strip() for r in re.split(r'[;+]', str(reason_str)) if r.strip()
    }

    # Discard the row only when EVERY reason is a publisher error.
    return not current_reasons.issubset(_PUBLISHER_ERROR_REASONS)


def load_and_filter_data(input_file):
    """Load Retraction Watch and apply the three project-level filters.

    1. Country contains "United States" (case-insensitive substring match).
    2. ``RetractionNature`` equals exactly ``"Retraction"``.
    3. ``Reason`` is not exclusively a set of publisher errors.

    Three output columns are initialised to ``"Pending"`` so that the
    downstream pipeline can detect rows that have not yet been processed.
    """
    print("1. Loading and filtering dataset...")

    df = pd.read_csv(input_file)

    # 1. Country filter (case-insensitive substring).
    us_studies = df[
        df['Country'].astype(str).str.contains(
            "United States", case=False, na=False,
        )
    ].copy()

    # 2. Keep only retractions (drop expressions of concern, corrections, etc.).
    us_studies = us_studies[us_studies['RetractionNature'] == 'Retraction']

    # 3. Drop rows whose only retraction reasons are publisher mistakes.
    us_studies = us_studies[us_studies['Reason'].apply(_is_valid_reason)]

    print(
        f"   Isolated {len(us_studies)} valid retraction records "
        "affiliated with the United States."
    )

    # Sentinel placeholders so step 1 (PubMed fetch) can detect unprocessed rows.
    us_studies['PubMed_ID'] = "Pending"
    us_studies['Study_Design'] = "Pending"
    us_studies['Funding_Info'] = "Pending"

    return us_studies


def save_data(df, output_file):
    """Write the enriched dataframe to ``output_file`` without the index."""
    print(f"\n3. Exporting processed DataFrame to {output_file}...")
    df.to_csv(output_file, index=False)
