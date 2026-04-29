# =============================================================================
# STEP 5 - PUBMED GRANT PUBLICATION COUNTER
# =============================================================================
# For every NIH grant attached to a retracted paper that actually has
# funding (i.e. cost > 0), queries PubMed via the Entrez API to obtain
# the total number of publications associated with that grant identifier.
#
# This count is later used by the dashboard to compute "attributed cost
# per paper" - dividing the grant's cumulative funding by the number of
# publications it produced gives a rough estimate of how much taxpayer
# money each individual paper consumed.
#
# Output (data/processed/FINAL_Retractions_Costs_and_Pubs.csv):
#     Individual_Grant_Pub_Counts  Per-grant pub counts (parallel order)
#     Total_Grant_Pubs             Sum of pub counts for the row
# =============================================================================
import os
import time

import pandas as pd
from Bio import Entrez
from tqdm import tqdm

from src.config import API_KEY, BASE_DIR

INPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_with_Costs.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "FINAL_Retractions_Costs_and_Pubs.csv")


def fetch_publication_count(grant_id):
    """Return the PubMed publication count for a single NIH grant ID.

    Implements a single retry on failure; on a second consecutive error
    the function returns 0 to keep the pipeline progressing rather than
    aborting an entire ~hour-long run for one transient network glitch.
    """
    try:
        handle = Entrez.esearch(db="pubmed", term=f"{grant_id}[Grant Number]", retmax=1)
        record = Entrez.read(handle)
        handle.close()
        return int(record["Count"])
    except Exception as exc:
        tqdm.write(f"[!] Connection failed for {grant_id}. Reason: {exc}")
        time.sleep(2)
        try:
            handle = Entrez.esearch(db="pubmed", term=f"{grant_id}[Grant Number]", retmax=1)
            record = Entrez.read(handle)
            handle.close()
            return int(record["Count"])
        except Exception:
            return 0


def link_publication_counts():
    """Top-level entrypoint executed by step 5 of the pipeline."""
    print("1. Loading dataset and extracting funded grants...")
    if not os.path.exists(INPUT_FILE):
        print(f"[!] Error: {INPUT_FILE} not found. Run step 4 first.")
        return

    df = pd.read_csv(INPUT_FILE)

    # Collect the unique set of grant IDs whose cost is strictly positive.
    # Grants with zero cost cannot meaningfully attribute funding per paper,
    # so we skip them and save the API quota.
    unique_grants = set()
    for _, row in df.iterrows():
        grants = str(row.get('Funding_Info_cleaned', '')).split(';')
        costs = str(row.get('Individual_NIH_Grant_Costs', '')).split(';')

        for i, g in enumerate(grants):
            g = g.strip()
            if g and g != "nan":
                try:
                    cost_val = float(costs[i].strip())
                except (IndexError, ValueError):
                    cost_val = 0.0

                if cost_val > 0:
                    unique_grants.add(g)

    print(f"   Found {len(unique_grants)} funded unique grants to query.")

    print("\n2. Querying PubMed API for publication counts...")
    grant_pub_counts = {}

    # The NCBI rate limit is 3 req/s without an API key and 10 req/s with one.
    sleep_seconds = 0.15 if API_KEY else 0.35
    for grant in tqdm(unique_grants, desc="Fetching counts from PubMed"):
        grant_pub_counts[grant] = fetch_publication_count(grant)
        time.sleep(sleep_seconds)

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

                # Force a zero count when the grant carries zero cost: this
                # keeps the per-paper attributed cost calculation stable
                # (zero cost grants contribute neither dollars nor pubs).
                count = 0 if cost_val == 0.0 else grant_pub_counts.get(g, 0)

                ind_counts.append(str(count))
                total_pubs += count

        if ind_counts:
            df.at[index, 'Individual_Grant_Pub_Counts'] = "; ".join(ind_counts)
            df.at[index, 'Total_Grant_Pubs'] = total_pubs

    print(f"\n4. Saving final fully-enriched dataset to: {OUTPUT_FILE}")
    df.to_csv(OUTPUT_FILE, index=False)
    print("Step 5 complete.")


if __name__ == "__main__":
    link_publication_counts()
