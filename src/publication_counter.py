# =============================================================================
# PUBMED GRANT PUBLICATION COUNTER
# =============================================================================
import pandas as pd
import time
import os
from tqdm import tqdm
from Bio import Entrez
from src.config import BASE_DIR, API_KEY

# We read the file that just finished in Step 3
INPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_with_Costs.csv")
# We save it as a new, fully enriched file
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_Costs_and_Pubs.csv")


def fetch_publication_count(grant_id):
    """
    Queries the PubMed API to get the total number of publications
    associated with a specific NIH Grant ID.
    """
    try:
        handle = Entrez.esearch(db="pubmed", term=f"{grant_id}[Grant Number]", retmax=1)
        record = Entrez.read(handle)
        handle.close()
        return int(record["Count"])
    except Exception as e:
        tqdm.write(f"[!] Connection failed for {grant_id}. Reason: {e}")
        time.sleep(2)
        try:
            handle = Entrez.esearch(db="pubmed", term=f"{grant_id}[Grant Number]", retmax=1)
            record = Entrez.read(handle)
            handle.close()
            return int(record["Count"])
        except:
            return 0


def link_publication_counts():
    print("1. Loading dataset and extracting funded grants...")
    if not os.path.exists(INPUT_FILE):
        print(f"[!] Error: Could not find {INPUT_FILE}. Did you run Step 3?")
        return

    df = pd.read_csv(INPUT_FILE)

    # Extract all unique grants THAT HAVE FUNDING > 0
    unique_grants = set()
    for index, row in df.iterrows():
        grants = str(row.get('Funding_Info_cleaned', '')).split(';')
        costs = str(row.get('Individual_NIH_Grant_Costs', '')).split(';')

        for i, g in enumerate(grants):
            g = g.strip()
            if g and g != "nan":
                try:
                    # Look at the corresponding cost for this exact grant
                    cost_val = float(costs[i].strip())
                except (IndexError, ValueError):
                    cost_val = 0.0

                # Only query PubMed if there is actual money attached
                if cost_val > 0:
                    unique_grants.add(g)

    print(f"   Found {len(unique_grants)} funded unique grants to query.")

    print("\n2. Querying PubMed API for publication counts...")
    grant_pub_counts = {}

    for grant in tqdm(unique_grants, desc="Fetching counts from PubMed"):
        grant_pub_counts[grant] = fetch_publication_count(grant)
        time.sleep(0.15 if API_KEY else 0.35)

    print("\n3. Mapping counts back to the master dataset...")
    df['Individual_Grant_Pub_Counts'] = ""
    df['Total_Grant_Pubs'] = 0

    for index, row in df.iterrows():
        grants = str(row.get('Funding_Info_cleaned', '')).split(';')
        costs = str(row.get('Individual_NIH_Grant_Costs', '')).split(';')

        ind_counts = []
        total_pubs = 0

        for i, g in enumerate(grants):
            g = g.strip()
            if g and g != "nan":
                try:
                    cost_val = float(costs[i].strip())
                except (IndexError, ValueError):
                    cost_val = 0.0

                # If cost is 0, force pub count to 0. Otherwise, fetch the real count.
                if cost_val == 0.0:
                    count = 0
                else:
                    count = grant_pub_counts.get(g, 0)

                ind_counts.append(str(count))
                total_pubs += count

        if ind_counts:
            df.at[index, 'Individual_Grant_Pub_Counts'] = "; ".join(ind_counts)
            df.at[index, 'Total_Grant_Pubs'] = total_pubs

    print(f"\n4. Saving final fully-enriched dataset to: {OUTPUT_FILE}")
    df.to_csv(OUTPUT_FILE, index=False)
    print("Pipeline complete! 🚀")


if __name__ == "__main__":
    link_publication_counts()