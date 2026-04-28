# =============================================================================
# NIH REPORTER MERGER & AGGREGATOR
# =============================================================================
import pandas as pd
import os
import glob
import re
from tqdm import tqdm
from src.config import BASE_DIR

# 1. Añadimos TOTAL_COST_SUB_PROJECT de vuelta a nuestra lista
TARGET_COLUMNS = {
    "AWARD_NOTICE_DATE",
    "BUDGET_START",
    "BUDGET_END",
    "CORE_PROJECT_NUM",
    "PROJECT_NUM",
    "SUPPORT_YEAR",
    "TOTAL_COST",
    "TOTAL_COST_SUB_PROJECT"  # <-- ¡De vuelta al juego!
}


def extract_core_id(x):
    """
    Vectorized cleaning: Extracts the 2-letter, 6-digit core ID.
    Perfectly converts '5R01AG008179-05' -> 'AG008179'
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
    """Extracts historical costs from PRJFUNDING files (1985-1999)."""
    funding_dict = {}
    chunk_iterator = pd.read_csv(
        funding_filepath, chunksize=100000,
        usecols=['FULL_PROJECT_NUM', 'TOTAL_COST'], encoding='latin1', low_memory=False
    )
    for chunk in chunk_iterator:
        chunk = chunk.dropna(subset=['FULL_PROJECT_NUM', 'TOTAL_COST']).copy()
        chunk['TOTAL_COST'] = pd.to_numeric(
            chunk['TOTAL_COST'].astype(str).str.replace(',', ''), errors='coerce'
        ).fillna(0)

        chunk['Match_ID'] = chunk['FULL_PROJECT_NUM'].apply(extract_core_id)
        chunk = chunk.dropna(subset=['Match_ID'])

        grouped = chunk.groupby('Match_ID')['TOTAL_COST'].sum().to_dict()
        for match_id, cost in grouped.items():
            funding_dict[match_id] = funding_dict.get(match_id, 0) + cost
    return funding_dict


def merge_nih_csvs(
        input_folder=os.path.join(BASE_DIR, "data", "raw", "nih_reporter"),
        output_file=os.path.join(BASE_DIR, "data", "processed", "MASTER_NIH_Projects.csv")
):
    temp_file = os.path.join(BASE_DIR, "data", "processed", "TEMP_NIH_Merged.csv")
    print("PHASE 1: Memory-safe merge, ID standardization, and cost summation...")

    search_pattern = os.path.join(input_folder, "RePORTER_PRJ_C_FY*.csv")
    prj_files = sorted(glob.glob(search_pattern))

    if not prj_files:
        print("[!] No PRJ CSV files found. Make sure you extracted the ZIPs!")
        return

    first_file = True

    for prj_file in tqdm(prj_files, desc="Processing FY Files"):
        match = re.search(r'FY(\d{4})', os.path.basename(prj_file))
        fiscal_year = int(match.group(1)) if match else 0
        funding_dict = {}

        if 1985 <= fiscal_year <= 1999:
            funding_file = os.path.join(input_folder, f"RePORTER_PRJFUNDING_C_FY{fiscal_year}.csv")
            if os.path.exists(funding_file):
                funding_dict = build_funding_dictionary(funding_file)

        chunk_container = pd.read_csv(
            prj_file, chunksize=100000, encoding='latin1', low_memory=False,
            usecols=lambda c: c in TARGET_COLUMNS
        )

        for chunk in chunk_container:
            id_col = 'CORE_PROJECT_NUM' if 'CORE_PROJECT_NUM' in chunk.columns else 'PROJECT_NUM'
            if id_col not in chunk.columns:
                continue

            chunk = chunk.dropna(subset=[id_col]).copy()
            chunk['Fiscal_Year'] = fiscal_year

            chunk['Cleaned_ID'] = chunk[id_col].apply(extract_core_id)
            chunk = chunk.dropna(subset=['Cleaned_ID'])

            # 2. Aseguramos que TOTAL_COST esté limpio y sea numérico
            if 'TOTAL_COST' not in chunk.columns:
                chunk['TOTAL_COST'] = 0.0
            else:
                chunk['TOTAL_COST'] = pd.to_numeric(
                    chunk['TOTAL_COST'].astype(str).str.replace(',', ''), errors='coerce'
                ).fillna(0.0)

            # 3. Aseguramos que TOTAL_COST_SUB_PROJECT esté limpio y sea numérico
            if 'TOTAL_COST_SUB_PROJECT' not in chunk.columns:
                chunk['TOTAL_COST_SUB_PROJECT'] = 0.0
            else:
                chunk['TOTAL_COST_SUB_PROJECT'] = pd.to_numeric(
                    chunk['TOTAL_COST_SUB_PROJECT'].astype(str).str.replace(',', ''), errors='coerce'
                ).fillna(0.0)

            # 4. CREAMOS LA COLUMNA COMBINADA
            chunk['COMBINED_COST'] = chunk['TOTAL_COST'] + chunk['TOTAL_COST_SUB_PROJECT']

            # Inyectamos datos históricos (1985-1999) si COMBINED_COST es 0
            if funding_dict:
                mask = chunk['COMBINED_COST'] == 0
                chunk.loc[mask, 'COMBINED_COST'] = chunk.loc[mask, 'Cleaned_ID'].map(funding_dict).fillna(0)

            # Solo guardamos el ID, el Año, y nuestro nuevo Coste Combinado
            final_chunk = chunk[['Cleaned_ID', 'Fiscal_Year', 'COMBINED_COST']]
            final_chunk.to_csv(temp_file, mode='a', index=False, header=first_file)
            first_file = False

    print("\nPHASE 2: Aggregating grants into unique rows...")
    df = pd.read_csv(temp_file, low_memory=False)

    # Formateamos el string usando nuestra nueva columna COMBINED_COST
    df['Year_Cost_Str'] = "FY" + df['Fiscal_Year'].astype(str) + ": " + df['COMBINED_COST'].astype(str)

    print(" -> Grouping and summing total historical costs...")
    aggregated_df = df.groupby('Cleaned_ID').agg(
        Yearly_Funding_Breakdown=('Year_Cost_Str', lambda x: '; '.join(x)),
        # Sumamos todos los COMBINED_COST a lo largo de los años
        Final_Total_Cost=('COMBINED_COST', 'sum')
    ).reset_index()

    aggregated_df.to_csv(output_file, index=False)

    if os.path.exists(temp_file):
        os.remove(temp_file)

    print(f"\nSuccess! Aggregated master dataset saved to: {output_file}")


if __name__ == "__main__":
    merge_nih_csvs()