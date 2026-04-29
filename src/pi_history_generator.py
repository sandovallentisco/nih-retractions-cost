# =============================================================================
# STEP 3 - PI HISTORY GENERATOR
# =============================================================================
# Builds a per-author, per-year ledger of NIH funding by streaming every
# annual project CSV in ``data/raw/nih_reporter/`` and exploding the
# ``PI_NAMES`` column (which encodes one or more co-PIs separated by
# semicolons) into individual rows.
#
# A canonical match key (``LAST_FIRST_MIDDLEINITIAL``) is then computed
# for each row so that step 6 (``author_funding_matcher``) can join this
# ledger against retracted authors using strict, capitalisation-safe
# string matching.
#
# Output columns (data/processed/MASTER_PI_History.csv):
#     Match_Key       str    Canonical "LAST_FIRST_MI" key
#     PI_NAME         str    Original PI name (uppercased, comma-separated)
#     Grant_ID        str    Full project number as found in the CSV
#     Fiscal_Year     int    Fiscal year of the grant slice
#     Funding_Amount  float  Combined TOTAL_COST + TOTAL_COST_SUB_PROJECT
# =============================================================================
import glob
import os
import re

import pandas as pd
from tqdm import tqdm

from src.config import BASE_DIR

# Acceptable column names in upper case. The CSVs use slightly different
# names across fiscal years, so we accept any of the listed aliases.
TARGET_COLUMNS_UPPER = {
    "CORE_PROJECT_NUM", "PROJECT_NUM", "FULL_PROJECT_NUM",
    "TOTAL_COST", "TOTAL_COST_SUB_PROJECT",
    "PI_NAMES", "PI_NAME", "PRINCIPAL_INVESTIGATORS", "CONTACT_PI_PROJECT_LEADER",
}


def extract_core_id(x):
    """Extract the canonical 8-character NIH grant core ID from any project
    number variant. Mirrors the logic in :mod:`src.nih_merger` so that the
    two tables can be joined later on a stable key."""
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
    """Sum total cost per cleaned grant ID from a historical PRJFUNDING CSV.

    Used to backfill 1985-1999 rows whose project CSV does not include a
    cost column. See :func:`src.nih_merger.build_funding_dictionary` for
    the equivalent logic in step 2.
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


def generate_pi_history(
        input_folder=os.path.join(BASE_DIR, "data", "raw", "nih_reporter"),
        output_file=os.path.join(BASE_DIR, "data", "processed", "MASTER_PI_History.csv"),
):
    """Generate ``MASTER_PI_History.csv`` from the raw ExPORTER files."""
    print("Generating MASTER_PI_History from raw ExPORTER files...")

    search_pattern = os.path.join(input_folder, "RePORTER_PRJ_C_FY*.csv")
    prj_files = sorted(glob.glob(search_pattern))

    if not prj_files:
        print("[!] No raw files found in data/raw/nih_reporter.")
        return

    if os.path.exists(output_file):
        os.remove(output_file)

    first_file = True

    for prj_file in tqdm(prj_files, desc="Processing fiscal years"):
        match = re.search(r'FY(\d{4})', os.path.basename(prj_file))
        fiscal_year = int(match.group(1)) if match else 0
        funding_dict = {}

        if 1985 <= fiscal_year <= 1999:
            funding_file = os.path.join(
                input_folder,
                f"RePORTER_PRJFUNDING_C_FY{fiscal_year}.csv",
            )
            if os.path.exists(funding_file):
                funding_dict = build_funding_dictionary(funding_file)

        chunk_container = pd.read_csv(
            prj_file, chunksize=100000, encoding='latin1', low_memory=False,
            usecols=lambda c: c.strip().upper() in TARGET_COLUMNS_UPPER,
        )

        for chunk in chunk_container:
            chunk.columns = chunk.columns.str.strip()
            id_col = next(
                (c for c in chunk.columns
                 if c.upper() in ['FULL_PROJECT_NUM', 'PROJECT_NUM', 'CORE_PROJECT_NUM']),
                None,
            )
            pi_col = next(
                (c for c in chunk.columns
                 if c.upper() in ['PI_NAMES', 'PI_NAME', 'PRINCIPAL_INVESTIGATORS']),
                None,
            )

            if not id_col or not pi_col:
                continue

            chunk = chunk.dropna(subset=[id_col, pi_col]).copy()
            chunk['Fiscal_Year'] = fiscal_year
            chunk['Grant_ID'] = chunk[id_col]
            chunk['Cleaned_ID'] = chunk[id_col].apply(extract_core_id)

            for cost_col in ['TOTAL_COST', 'TOTAL_COST_SUB_PROJECT']:
                if cost_col not in chunk.columns:
                    chunk[cost_col] = 0.0
                else:
                    chunk[cost_col] = pd.to_numeric(
                        chunk[cost_col].astype(str).str.replace(',', ''),
                        errors='coerce',
                    ).fillna(0.0)

            chunk['Funding_Amount'] = chunk['TOTAL_COST'] + chunk['TOTAL_COST_SUB_PROJECT']

            if funding_dict:
                mask = chunk['Funding_Amount'] == 0
                chunk.loc[mask, 'Funding_Amount'] = (
                    chunk.loc[mask, 'Cleaned_ID'].map(funding_dict).fillna(0)
                )

            # Strip the "(contact)" suffix that PRINCIPAL_INVESTIGATORS rows
            # frequently carry, then split on ";" to one row per PI.
            chunk['PI_NAMEs_clean'] = chunk[pi_col].astype(str).str.replace(
                r'\(contact\)', '', regex=True, flags=re.IGNORECASE,
            )
            chunk = chunk.assign(PI_NAME=chunk['PI_NAMEs_clean'].str.split(';')).explode('PI_NAME')
            chunk['PI_NAME'] = chunk['PI_NAME'].str.strip().str.upper()

            # Build the canonical join key: LAST_FIRST_MI (e.g. "KAPLAN_ADAM_C").
            def get_key(name):
                if pd.isna(name) or str(name).strip() == '' or str(name).strip().upper() == 'NAN':
                    return None

                parts = str(name).split(',')
                if len(parts) >= 2:
                    last = re.sub(r'[^A-Z]', '', parts[0].strip().upper())
                    given_tokens = parts[1].strip().upper().split()

                    if len(given_tokens) > 0:
                        first = re.sub(r'[^A-Z]', '', given_tokens[0])
                        mi = ""  # middle initial

                        if len(given_tokens) > 1:
                            middle_word = re.sub(r'[^A-Z]', '', given_tokens[1])
                            # Pattern "A B" -> treat second token as full first name.
                            if len(first) == 1 and len(middle_word) > 0:
                                first = f"{first}{middle_word}"
                            elif len(middle_word) > 0:
                                # Otherwise keep just the middle initial.
                                mi = middle_word[0]

                        return f"{last}_{first}_{mi}".strip('_')
                    return last

                return re.sub(r'[^A-Z]', '', str(name).upper())

            chunk['Match_Key'] = chunk['PI_NAME'].apply(get_key)

            final_chunk = chunk[
                ['Match_Key', 'PI_NAME', 'Grant_ID', 'Fiscal_Year', 'Funding_Amount']
            ].dropna(subset=['Match_Key'])
            final_chunk.to_csv(output_file, mode='a', index=False, header=first_file)
            first_file = False

    print(f"Master PI History written to: {output_file}")


if __name__ == "__main__":
    generate_pi_history()
