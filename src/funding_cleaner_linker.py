# =============================================================================
# STEP 4 - LINK PUBMED GRANTS TO NIH COSTS
# =============================================================================
# Joins the PubMed-derived grant list (column ``Funding_Info`` in
# ``retraction_watch_with_funding.csv``) against the per-grant total cost
# table produced by step 2 (``MASTER_NIH_Projects.csv``).
#
# The PubMed ``Funding_Info`` column is unstructured: a free-text
# concatenation of agency / grant ID pairs as stored in the PubMed XML.
# This module standardises every grant identifier into the canonical
# 8-character NIH core ID and looks up the corresponding aggregated cost.
#
# Output (data/processed/FINAL_Retractions_with_Costs.csv):
#     Funding_Info_cleaned        Cleaned, deduplicated, ordered grant list
#     Individual_NIH_Grant_Costs  Per-grant costs (parallel order)
#     Total_NIH_Funding_Cost      Sum of all matched grant costs for the row
# =============================================================================
import os
import re

import pandas as pd
from tqdm import tqdm

from src.config import BASE_DIR, OUTPUT_FILE

NIH_FILE = os.path.join(BASE_DIR, "data", "processed", "MASTER_NIH_Projects.csv")
FINAL_OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_with_Costs.csv")


def clean_and_extract_ids(funding_string):
    """Convert a raw PubMed funding string into ordered, unique NIH core IDs.

    PubMed grant IDs are dirty: missing dashes, OCR'd ``O`` for zero, mixed
    capitalisation, missing zero-padding, and frequent duplicates within a
    single paper (e.g. one grant cited under multiple grant numbers). This
    function applies the same cleaning rules used in :mod:`src.nih_merger`
    so that lookups against ``MASTER_NIH_Projects.csv`` succeed.

    Order is preserved as it appeared in the source string; duplicates are
    dropped using ``dict.fromkeys`` rather than ``set`` to keep the
    ordering stable.
    """
    if pd.isna(funding_string):
        return []

    matches = re.findall(r'([A-Z]{2})[- ]?([0-9O]{5,6})', str(funding_string).upper())
    ordered_ids = []

    for letters, digits in matches:
        digits = digits.replace('O', '0')
        if len(digits) == 5:
            digits = '0' + digits
        if len(digits) == 6:
            ordered_ids.append(f"{letters}{digits}")

    return list(dict.fromkeys(ordered_ids))


def link_funding_costs():
    """Top-level entrypoint executed by step 4 of the pipeline."""
    print("1. Loading aggregated NIH RePORTER database...")
    df_nih = pd.read_csv(NIH_FILE)

    # Build an in-memory dictionary for O(1) lookups: 'AG008179' -> 316160.0
    grant_costs = dict(zip(df_nih['Cleaned_ID'], df_nih['Final_Total_Cost']))
    print(f"   Loaded {len(grant_costs)} unique NIH grants into memory.")

    print("\n2. Loading PubMed dataset and matching funds...")
    df_pubmed = pd.read_csv(
        OUTPUT_FILE,
        sep=None,                # auto-detect ',' or ';'
        engine='python',         # required for sep=None
        on_bad_lines='skip',     # tolerate sporadically broken rows
        encoding='utf-8',
    )

    df_pubmed['Funding_Info_cleaned'] = ""
    df_pubmed['Individual_NIH_Grant_Costs'] = ""
    df_pubmed['Total_NIH_Funding_Cost'] = 0.0

    for index, row in tqdm(df_pubmed.iterrows(), total=len(df_pubmed), desc="Processing papers"):
        raw_funding = row.get('Funding_Info', '')

        cleaned_grants = clean_and_extract_ids(raw_funding)

        individual_costs = []
        total_paper_cost = 0.0

        for core_id in cleaned_grants:
            cost = grant_costs.get(core_id, 0.0)
            individual_costs.append(f"{cost:.2f}")
            total_paper_cost += cost

        df_pubmed.at[index, 'Funding_Info_cleaned'] = "; ".join(cleaned_grants)
        df_pubmed.at[index, 'Individual_NIH_Grant_Costs'] = "; ".join(individual_costs)
        df_pubmed.at[index, 'Total_NIH_Funding_Cost'] = round(total_paper_cost, 2)

    print(f"\n3. Saving final enriched dataset to: {FINAL_OUTPUT_FILE}")
    df_pubmed.to_csv(FINAL_OUTPUT_FILE, index=False)
    print("Step 4 complete.")


if __name__ == "__main__":
    link_funding_costs()
