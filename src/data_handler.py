# =============================================================================
# DATA HANDLING: LOADING, FILTERING & EXPORT
# =============================================================================
import pandas as pd  # Pandas is used for data manipulation and tabular analysis.
import re  # Regular expressions (needed to split the reasons).


def load_and_filter_data(input_file):
    print("1. Loading and filtering dataset...")

    # Instantiate the primary pandas DataFrame from the source CSV.
    df = pd.read_csv(input_file)

    # 1. Filter by Country (United States)
    # We cast the 'Country' column to string to prevent attribute errors on NaN values,
    # and execute a case-insensitive substring match for "United States".
    us_studies = df[df['Country'].astype(str).str.contains("United States", case=False, na=False)].copy()

    # 2. Filter by RetractionNature (Only "Retraction")
    us_studies = us_studies[us_studies['RetractionNature'] == 'Retraction']

    # 3. Filter by Reason (Exclude publisher errors IF they are the only reasons)
    excluded_reasons = {
        'Error by Journal/Publisher',
        'Duplicate Publication through Error by Journal/Publisher',
        'Withdrawn (out of date)'
    }

    def is_valid_reason(reason_str):
        # If the cell is empty (NaN), we do not discard it under this rule.
        if pd.isna(reason_str):
            return True

            # We split the text by ";" or "+" (common delimiters in RetractionWatch)
        # and strip any leading/trailing whitespace around each tag.
        current_reasons = {r.strip() for r in re.split(r'[;+]', str(reason_str)) if r.strip()}

        # If 'current_reasons' is a subset of 'excluded_reasons', it means
        # ALL tags for this row are publisher errors. Therefore, it is discarded (False).
        # If there is at least one extra reason (e.g., 'Data Falsification'),
        # it will not be a subset and the record is kept (True).
        return not current_reasons.issubset(excluded_reasons)

    # Apply the custom filtering function to the Reason column.
    us_studies = us_studies[us_studies['Reason'].apply(is_valid_reason)]

    print(f"   Isolated {len(us_studies)} valid Retraction records affiliated with the United States.")

    # Initialize destination columns with a "Pending" state marker.
    us_studies['PubMed_ID'] = "Pending"
    us_studies['Study_Design'] = "Pending"
    us_studies['Funding_Info'] = "Pending"

    return us_studies


def save_data(df, output_file):
    print(f"\n3. Exporting processed DataFrame to {output_file}...")

    # Write the modified DataFrame to disk. index=False omits the index array from the CSV output.
    df.to_csv(output_file, index=False)