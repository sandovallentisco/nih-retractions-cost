# =============================================================================
# STEP 2 - NIH RePORTER MERGER & AGGREGATOR
# =============================================================================
# Reads every annual NIH ExPORTER project CSV, normalises the grant
# identifiers, sums total cost per grant across all fiscal years and emits
# ``data/processed/MASTER_NIH_Projects.csv`` - one row per unique grant
# core ID with its full historical funding total and a per-year breakdown.
#
# The merger is memory-safe: it reads every annual file in 100k-row chunks
# and streams the partial results to a temporary CSV, then performs the
# final aggregation in a single pandas ``groupby`` over that intermediate
# file. This keeps peak RAM bounded regardless of the full ExPORTER size.
#
# For fiscal years 1985-1999 the project CSVs do not contain ``TOTAL_COST``,
# so a parallel pass over the corresponding ``RePORTER_PRJFUNDING_C_FY*.csv``
# files is used to backfill historical funding amounts where available.
# =============================================================================
import glob
import os
import re

import pandas as pd
from tqdm import tqdm

from src.config import BASE_DIR

# Columns we need to retain when streaming each annual project CSV.
# Anything outside this set is discarded at read time to keep the chunks
# small.
TARGET_COLUMNS = {
    "AWARD_NOTICE_DATE",
    "BUDGET_START",
    "BUDGET_END",
    "CORE_PROJECT_NUM",
    "PROJECT_NUM",
    "SUPPORT_YEAR",
    "TOTAL_COST",
    "TOTAL_COST_SUB_PROJECT",
}


def extract_core_id(x):
    """Vectorised cleaner that extracts the canonical 8-character NIH core ID.

    Examples::

        "5R01AG008179-05" -> "AG008179"
        "1R01CA0001-01"   -> "CA000001"  (zero-padded)
        "5R01AGOO8179-05" -> "AG008179"  (OCR 'O' fixed)

    Returns ``None`` for inputs that do not contain a recognisable core ID.
    """
    if pd.isna(x):
        return None

    match = re.search(r'([A-Z]{2})[- ]?([0-9O]{5,6})', str(x).upper())
    if match:
        letters = match.group(1)
        digits = match.group(2).replace('O', '0')
        if len(digits) == 5:
            digits = '0' + digits
        if len(digits) == 6:
            return f"{letters}{digits}"
    return None


def build_funding_dictionary(funding_filepath):
    """Map ``Match_ID -> total cost`` from a historical PRJFUNDING file.

    Used only for fiscal years 1985-1999, where the project CSV does not
    expose ``TOTAL_COST`` directly. The resulting dictionary is consumed by
    :func:`merge_nih_csvs` to backfill funding rows whose project CSV row
    reports zero cost.
    """
    funding_dict = {}
    chunk_iterator = pd.read_csv(
        funding_filepath, chunksize=100000,
        usecols=['FULL_PROJECT_NUM', 'TOTAL_COST'],
        encoding='latin1', low_memory=False,
    )
    for chunk in chunk_iterator:
        chunk = chunk.dropna(subset=['FULL_PROJECT_NUM', 'TOTAL_COST']).copy()
        chunk['TOTAL_COST'] = pd.to_numeric(
            chunk['TOTAL_COST'].astype(str).str.replace(',', ''),
            errors='coerce',
        ).fillna(0)

        chunk['Match_ID'] = chunk['FULL_PROJECT_NUM'].apply(extract_core_id)
        chunk = chunk.dropna(subset=['Match_ID'])

        grouped = chunk.groupby('Match_ID')['TOTAL_COST'].sum().to_dict()
        for match_id, cost in grouped.items():
            funding_dict[match_id] = funding_dict.get(match_id, 0) + cost
    return funding_dict


def merge_nih_csvs(
        input_folder=os.path.join(BASE_DIR, "data", "raw", "nih_reporter"),
        output_file=os.path.join(BASE_DIR, "data", "processed", "MASTER_NIH_Projects.csv"),
):
    """Merge all annual NIH project CSVs into a single per-grant table."""
    temp_file = os.path.join(BASE_DIR, "data", "processed", "TEMP_NIH_Merged.csv")
    print("PHASE 1: Memory-safe merge, ID standardisation, and cost summation...")

    search_pattern = os.path.join(input_folder, "RePORTER_PRJ_C_FY*.csv")
    prj_files = sorted(glob.glob(search_pattern))

    if not prj_files:
        print("[!] No PRJ CSV files found. Make sure the ZIPs were extracted.")
        return

    first_file = True

    for prj_file in tqdm(prj_files, desc="Processing FY files"):
        # Pull the fiscal year out of the filename. Defaults to 0 if the
        # regex fails so the historical-funding fallback below stays inert.
        match = re.search(r'FY(\d{4})', os.path.basename(prj_file))
        fiscal_year = int(match.group(1)) if match else 0
        funding_dict = {}

        # Backfill table for historical years that lack TOTAL_COST.
        if 1985 <= fiscal_year <= 1999:
            funding_file = os.path.join(
                input_folder,
                f"RePORTER_PRJFUNDING_C_FY{fiscal_year}.csv",
            )
            if os.path.exists(funding_file):
                funding_dict = build_funding_dictionary(funding_file)

        chunk_container = pd.read_csv(
            prj_file, chunksize=100000, encoding='latin1', low_memory=False,
            usecols=lambda c: c in TARGET_COLUMNS,
        )

        for chunk in chunk_container:
            id_col = 'CORE_PROJECT_NUM' if 'CORE_PROJECT_NUM' in chunk.columns else 'PROJECT_NUM'
            if id_col not in chunk.columns:
                continue

            chunk = chunk.dropna(subset=[id_col]).copy()
            chunk['Fiscal_Year'] = fiscal_year

            chunk['Cleaned_ID'] = chunk[id_col].apply(extract_core_id)
            chunk = chunk.dropna(subset=['Cleaned_ID'])

            # Coerce TOTAL_COST to a numeric column. Strings with commas
            # and missing values are normalised to floats with NaN -> 0.
            if 'TOTAL_COST' not in chunk.columns:
                chunk['TOTAL_COST'] = 0.0
            else:
                chunk['TOTAL_COST'] = pd.to_numeric(
                    chunk['TOTAL_COST'].astype(str).str.replace(',', ''),
                    errors='coerce',
                ).fillna(0.0)

            # Same treatment for the sub-project cost column.
            if 'TOTAL_COST_SUB_PROJECT' not in chunk.columns:
                chunk['TOTAL_COST_SUB_PROJECT'] = 0.0
            else:
                chunk['TOTAL_COST_SUB_PROJECT'] = pd.to_numeric(
                    chunk['TOTAL_COST_SUB_PROJECT'].astype(str).str.replace(',', ''),
                    errors='coerce',
                ).fillna(0.0)

            # Single combined cost column we will aggregate on later.
            chunk['COMBINED_COST'] = chunk['TOTAL_COST'] + chunk['TOTAL_COST_SUB_PROJECT']

            # Inject historical (1985-1999) funding for rows that report zero.
            if funding_dict:
                mask = chunk['COMBINED_COST'] == 0
                chunk.loc[mask, 'COMBINED_COST'] = (
                    chunk.loc[mask, 'Cleaned_ID'].map(funding_dict).fillna(0)
                )

            # Append only the columns we need downstream to the temp file.
            final_chunk = chunk[['Cleaned_ID', 'Fiscal_Year', 'COMBINED_COST']]
            final_chunk.to_csv(temp_file, mode='a', index=False, header=first_file)
            first_file = False

    print("\nPHASE 2: Aggregating grants into unique rows...")
    df = pd.read_csv(temp_file, low_memory=False)

    # Build a "FY1995: 123456.78; FY1996: ..." string for human inspection.
    df['Year_Cost_Str'] = (
        "FY" + df['Fiscal_Year'].astype(str) + ": " + df['COMBINED_COST'].astype(str)
    )

    print(" -> Grouping and summing total historical costs...")
    aggregated_df = df.groupby('Cleaned_ID').agg(
        Yearly_Funding_Breakdown=('Year_Cost_Str', lambda x: '; '.join(x)),
        Final_Total_Cost=('COMBINED_COST', 'sum'),
    ).reset_index()

    aggregated_df.to_csv(output_file, index=False)

    if os.path.exists(temp_file):
        os.remove(temp_file)

    print(f"\nDone. Aggregated master dataset written to: {output_file}")


if __name__ == "__main__":
    merge_nih_csvs()
