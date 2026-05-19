# =============================================================================
# ENTREZ CLIENT - PUBMED METADATA EXTRACTION
# =============================================================================
# Single function wrapper around ``Bio.Entrez`` that resolves a Retraction
# Watch row (using its PMID) into the publication's
# study designs and grant list, ready to be merged back into the main
# dataframe by :mod:`src.pipeline`.
#
# The implementation favours robustness over thoroughness: any individual
# network failure or XML edge case returns a sentinel rather than raising,
# so a single bad row cannot abort the long-running pipeline.
# =============================================================================
import pandas as pd
from Bio import Entrez


def get_pubmed_metadata(provided_pmid):
    """Resolve a paper to ``(pmid, study_design_str, funding_list)``.

    Resolution strategy:
        1. Use ``provided_pmid`` after stripping any trailing ``.0`` introduced by pandas.
        2. If no usable PMID, return the sentinel triple
           ``("No valid PMID", "Unknown", [])``.

    Errors raised by Entrez or by XML parsing are caught and returned as
    ``("Error", "Error: <details>", [])`` so the pipeline can persist
    partial state and move on.
    """

    pmid_to_fetch = None

    # ------------------------------------------------------------------
    # Step 1 - resolution by the PMID supplied by Retraction Watch.
    # ------------------------------------------------------------------
    if pd.notna(provided_pmid):
        # Pandas often loads numeric PMIDs as floats ("12345.0"); strip
        # the suffix so Entrez accepts the value.
        clean_pmid = str(provided_pmid).split('.')[0].strip()

        if clean_pmid not in {"", "0"}:
            pmid_to_fetch = clean_pmid

    if not pmid_to_fetch:
        return "No valid PMID", "Unknown", []

    # ------------------------------------------------------------------
    # Step 2 - fetch and parse the full PubMed XML record.
    # ------------------------------------------------------------------
    try:
        handle = Entrez.efetch(db="pubmed", id=pmid_to_fetch, retmode="xml")
        fetch_records = Entrez.read(handle)
        handle.close()

        article = fetch_records['PubmedArticle'][0]['MedlineCitation']['Article']

        # PublicationTypeList encodes study design tags such as
        # "Journal Article", "Randomized Controlled Trial", "Review", etc.
        study_designs = []
        if 'PublicationTypeList' in article:
            study_designs = [str(pt) for pt in article['PublicationTypeList']]

        # GrantList contains the funding source records associated with the
        # paper. We extract just the agency and grant ID; any missing fields
        # fall back to neutral placeholders.
        funding_data = []
        if 'GrantList' in article:
            for grant in article['GrantList']:
                funding_data.append({
                    'Agency': grant.get('Agency', 'Unknown Agency'),
                    'GrantID': grant.get('GrantID', 'No ID'),
                })

        return pmid_to_fetch, "; ".join(study_designs), funding_data

    except Exception as exc:
        return "Error", f"Error: {str(exc)}", []
