# =============================================================================
# NIH REPORTER FUNDING LINKER & DATA CLEANER
# =============================================================================
import pandas as pd
import re
import os
from tqdm import tqdm
from src.config import BASE_DIR, OUTPUT_FILE

# Define the paths for our files
NIH_FILE = os.path.join(BASE_DIR, "data", "processed", "MASTER_NIH_Projects.csv")
FINAL_OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_with_Costs.csv")


def clean_and_extract_ids(funding_string):
    """
    Cleans dirty PubMed funding strings into standard 8-character NIH Core IDs.
    Removes duplicates while STRICTLY PRESERVING the original order.
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

    # dict.fromkeys() removes duplicates but keeps the exact order
    return list(dict.fromkeys(ordered_ids))


def link_funding_costs():
    print("1. Loading the newly aggregated NIH RePORTER database...")
    # Because Step 2 made this file so small, we can load it instantly!
    df_nih = pd.read_csv(NIH_FILE)

    # Create a lightning-fast Python dictionary for cost lookups
    # Maps 'AG008179' -> 316160.0
    grant_costs = dict(zip(df_nih['Cleaned_ID'], df_nih['Final_Total_Cost']))
    print(f"   Loaded {len(grant_costs)} unique NIH grants into memory.")

    print("\n2. Loading PubMed dataset and matching funds...")
    df_pubmed = pd.read_csv(
        OUTPUT_FILE,
        sep=None,               # Autodetecs ',' or ';'
        engine='python',        # To make sep=None work
        on_bad_lines='skip',    # Safeguard against broken lines
        encoding='utf-8')

    # Initialize our three new columns
    df_pubmed['Funding_Info_cleaned'] = ""
    df_pubmed['Individual_NIH_Grant_Costs'] = ""
    df_pubmed['Total_NIH_Funding_Cost'] = 0.0

    # Iterate through the retracted papers
    for index, row in tqdm(df_pubmed.iterrows(), total=len(df_pubmed), desc="Processing Papers"):
        raw_funding = row.get('Funding_Info', '')

        # Apply our rigorous cleaning rules to the PubMed data
        cleaned_grants = clean_and_extract_ids(raw_funding)

        individual_costs = []
        total_paper_cost = 0.0

        for core_id in cleaned_grants:
            # Fetch the specific aggregated cost for this grant from our dictionary
            cost = grant_costs.get(core_id, 0.0)

            individual_costs.append(f"{cost:.2f}")
            total_paper_cost += cost

        # Assign the final strings and sums to the dataframe
        df_pubmed.at[index, 'Funding_Info_cleaned'] = "; ".join(cleaned_grants)
        df_pubmed.at[index, 'Individual_NIH_Grant_Costs'] = "; ".join(individual_costs)
        df_pubmed.at[index, 'Total_NIH_Funding_Cost'] = round(total_paper_cost, 2)

    print(f"\n3. Saving final enriched dataset to: {FINAL_OUTPUT_FILE}")
    df_pubmed.to_csv(FINAL_OUTPUT_FILE, index=False)
    print("Pipeline complete! 🚀")


if __name__ == "__main__":
    link_funding_costs()