# =============================================================================
# AUTHOR TO NIH FUNDING MATCHER (ULTRA-STRICT MATCHING & DIFF_RETRACTED)
# =============================================================================
import pandas as pd
import os
import re
from src.config import BASE_DIR

RWD_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_Costs_and_Pubs.csv")
PI_HISTORY_MASTER = os.path.join(BASE_DIR, "data", "processed", "MASTER_PI_History.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "Author_Funding_Matches.csv")


def match_authors_to_funding():
    print("1. Cargando datos de Retraction Watch...")
    if not os.path.exists(RWD_FILE):
        print(f"[!] Error: {RWD_FILE} no encontrado.")
        return

    df_rwd = pd.read_csv(RWD_FILE, low_memory=False)

    print("2. Vinculando Autores con fechas de Retracción...")
    author_col = 'Author' if 'Author' in df_rwd.columns else 'Authors'
    author_records = []

    for idx, row in df_rwd.iterrows():
        authors_str = str(row.get(author_col, ''))
        ret_date = row.get('RetractionDate', pd.NaT)
        record_id = row.get('Record ID', idx)

        authors = [a.strip() for a in authors_str.split(';') if a.strip()]
        if authors:
            for target in list(set([authors[0], authors[-1]])):
                author_records.append({
                    'Original_Author_Name': target,
                    'Record_ID': record_id,
                    'RetractionDate': ret_date
                })

    df_author_papers = pd.DataFrame(author_records)
    df_author_papers['Retraction_Year'] = pd.to_datetime(df_author_papers['RetractionDate'], errors='coerce').dt.year
    df_author_papers = df_author_papers.dropna(subset=['Retraction_Year'])

    print("3. Generando llaves ultra-estrictas (Apellido_Nombre_Inicial)...")
    match_keys = {}
    for name in df_author_papers['Original_Author_Name'].unique():
        parts = name.upper().split()
        if len(parts) > 1:
            last = re.sub(r'[^A-Z]', '', parts[-1])
            first = re.sub(r'[^A-Z]', '', parts[0])
            mi = ""

            if len(parts) > 2:
                middle_word = re.sub(r'[^A-Z]', '', parts[1])
                if len(first) == 1 and len(middle_word) > 0:
                    first = f"{first}{middle_word}"
                elif len(middle_word) > 0:
                    mi = middle_word[0]  # Cogemos solo la inicial del segundo nombre

            key = f"{last}_{first}_{mi}".strip('_')

            if key not in match_keys: match_keys[key] = []
            match_keys[key].append(name)

    print("4. Ejecutando cruce con MASTER_PI_History...")
    if not os.path.exists(PI_HISTORY_MASTER):
        print(f"[!] Error: {PI_HISTORY_MASTER} no encontrado. Ejecuta el Paso 3 primero.")
        return

    df_pi_history = pd.read_csv(PI_HISTORY_MASTER, low_memory=False)

    matched_nih = df_pi_history[df_pi_history['Match_Key'].isin(match_keys.keys())].copy()
    if matched_nih.empty:
        print("No se encontraron coincidencias.")
        return

    matched_nih['Original_Author_Name'] = matched_nih['Match_Key'].map(match_keys)
    matched_nih = matched_nih.explode('Original_Author_Name')

    final_output = pd.merge(matched_nih, df_author_papers, on='Original_Author_Name', how='inner')

    print("5. Calculando la diferencia de años (diff_retracted)...")
    final_output['diff_retracted'] = final_output['Fiscal_Year'] - final_output['Retraction_Year']

    cols = ['Original_Author_Name', 'PI_NAME', 'Record_ID', 'Retraction_Year', 'Grant_ID', 'Fiscal_Year',
            'Funding_Amount', 'diff_retracted']
    final_output = final_output[cols].sort_values(['Original_Author_Name', 'Fiscal_Year'])

    final_output.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Archivo de coincidencias guardado: {OUTPUT_FILE}")


if __name__ == "__main__":
    match_authors_to_funding()