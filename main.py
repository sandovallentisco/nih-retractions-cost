"""
=============================================================================
RETRACTION WATCH & PUBMED METADATA INTEGRATION PIPELINE
=============================================================================
Description:
This script constructs an automated data pipeline to merge records from the
Retraction Watch database with study design and funding metadata retrieved
from the NCBI PubMed database.

Methodology:
1. Loads a CSV containing retracted publications.
2. Filters studies affiliated with the United States.
3. Iteratively queries the PubMed API (via E-utilities) using the DOI/PMID.
4. Parses the returned XML payload to extract 'PublicationTypeList' and 'GrantList'.
5. Appends the extracted metadata to the dataset and exports the updated dataframe.
=============================================================================
"""

import sys

# Importamos todos los módulos de la carpeta src/
from src.pipeline import run_pipeline
from src.nih_merger import merge_nih_csvs
from src.pi_history_generator import generate_pi_history
from src.funding_cleaner_linker import link_funding_costs
from src.publication_counter import link_publication_counts
from src.author_funding_matcher import match_authors_to_funding


def show_menu():
    print("\n" + "=" * 70)
    print(" RESEARCH FUNDING PIPELINE MAIN MENU ".center(70))
    print("=" * 70)

    print("1. Fetch PubMed Metadata (Takes ~1.5 hours)")
    print("   ↳ Reads: data/raw/retraction_watch/retraction_watch.csv")
    print("   ↳ Saves: data/processed/retraction_watch_with_funding.csv\n")

    print("2. Merge Raw NIH RePORTER Files (Aggregated Costs for Papers)")
    print("   ↳ Reads: data/raw/nih_reporter/*.csv")
    print("   ↳ Saves: data/processed/MASTER_NIH_Projects.csv\n")

    print("3. Generate MASTER PI History (Author Timeline directly from RAW)")
    print("   ↳ Reads: data/raw/nih_reporter/*.csv")
    print("   ↳ Saves: data/processed/MASTER_PI_History.csv\n")

    print("4. Link PubMed Grants to NIH Costs")
    print("   ↳ Reads: retraction_watch_with_funding.csv + MASTER_NIH_Projects.csv")
    print("   ↳ Saves: data/processed/FINAL_Retractions_with_Costs.csv\n")

    print("5. Fetch Publication Counts per Grant")
    print("   ↳ Reads: FINAL_Retractions_with_Costs.csv")
    print("   ↳ Saves: data/processed/FINAL_Retractions_Costs_and_Pubs.csv\n")

    print("6. Match Retracted Authors to ALL their NIH Grants")
    print("   ↳ Reads: FINAL_Retractions_Costs_and_Pubs.csv + MASTER_PI_History.csv")
    print("   ↳ Saves: data/processed/Author_Funding_Matches.csv\n")

    print("7. Run Entire Python Pipeline (Steps 1 -> 6)")
    print("0. Exit")
    print("=" * 70)


def main():
    while True:
        show_menu()
        choice = input("\nEnter the number of the step you want to run: ").strip()

        if choice == '1':
            print("\n>>> STARTING STEP 1: PUBMED FETCHING...\n")
            run_pipeline()

        elif choice == '2':
            print("\n>>> STARTING STEP 2: NIH MERGING (AGGREGATED COSTS)...\n")
            merge_nih_csvs()

        elif choice == '3':
            print("\n>>> STARTING STEP 3: GENERATING PI HISTORY (AUTHOR TIMELINE)...\n")
            generate_pi_history()

        elif choice == '4':
            print("\n>>> STARTING STEP 4: CLEANING & LINKING FUNDING COSTS...\n")
            link_funding_costs()

        elif choice == '5':
            print("\n>>> STARTING STEP 5: FETCHING PUBLICATION COUNTS...\n")
            link_publication_counts()

        elif choice == '6':
            print("\n>>> STARTING STEP 6: AUTHOR FUNDING MATCHING...\n")
            match_authors_to_funding()

        elif choice == '7':
            print("\n>>> STARTING FULL PYTHON PIPELINE...\n")
            run_pipeline()
            merge_nih_csvs()
            generate_pi_history()
            link_funding_costs()
            link_publication_counts()
            match_authors_to_funding()

        elif choice == '0':
            print("\nExiting program. Have a great day!")
            sys.exit()

        else:
            print("\n[!] Invalid choice. Please enter a number between 0 and 7.")


if __name__ == "__main__":
    main()