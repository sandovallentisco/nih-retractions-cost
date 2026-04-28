# =============================================================================
# MAIN EXECUTION & CONTROL FLOW
# =============================================================================
import time # The time module is required to implement rate-limiting protocols.

from tqdm import tqdm # tqdm provides a lightweight, extensible progress bar for iterative processes.

from src.config import INPUT_FILE, OUTPUT_FILE
from src.data_handler import load_and_filter_data, save_data
from src.entrez_client import get_pubmed_metadata

def run_pipeline():
    # Instantiate the primary pandas DataFrame from the source CSV.
    us_studies = load_and_filter_data(INPUT_FILE)

    print("2. Initiating PubMed API queries (Interrupt via Ctrl+C to execute safe shutdown)...")

    # ---------------------------------------------------------
    # STEP 3: Iterative Processing with State Preservation
    # ---------------------------------------------------------
    # A try/except/finally block is employed to ensure the DataFrame is exported
    # even if the process encounters an unhandled exception or user interruption.
    try:
        for index, row in tqdm(us_studies.iterrows(), total=len(us_studies), desc="Fetching"):

            # Extract identifiers from the current observational row.
            doi = row.get('OriginalPaperDOI', None)
            provided_pmid = row.get('OriginalPaperPubMedID', None)

            # Execute the metadata extraction function.
            pmid, design, fund_list = get_pubmed_metadata(doi, provided_pmid)

            # Format the list of funding dictionaries into a standardized string scalar.
            fund_str = "; ".join([f"{f['Agency']} ({f['GrantID']})" for f in fund_list])

            # Print a sneak peek of what was fetched without breaking the progress bar
            tqdm.write(
                f"Retrieved -> DOI: {doi} | PMID: {pmid} | Info: {design[:40]}... | Funding: {fund_str[:40]}...")

            # Utilize the .at accessor for highly optimized, scalar-level value assignment
            # directly into the DataFrame in memory.
            us_studies.at[index, 'PubMed_ID'] = pmid
            us_studies.at[index, 'Study_Design'] = design
            us_studies.at[index, 'Funding_Info'] = fund_str

            # Enforce rate-limiting (approx. 3 queries per second) to comply with NCBI guidelines.
            time.sleep(0.35)

    # Catch a user-initiated KeyboardInterrupt (Ctrl+C).
    except KeyboardInterrupt:
        print("\n\n[!] Process interrupted by user. Commencing state preservation...")

    # Catch arbitrary runtime exceptions to prevent complete data loss.
    except Exception as e:
        print(f"\n\n[!] Unhandled exception encountered: {e}. Commencing state preservation...")

    # The 'finally' clause guarantees execution of the export protocol regardless of prior control flow.
    finally:
        save_data(us_studies, OUTPUT_FILE)
        print("Pipeline execution terminated.")