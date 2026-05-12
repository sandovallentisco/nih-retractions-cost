# Cost of Retracted Articles to the NIH: A Living Analysis

This repository contains the code, data processing pipeline, and Shiny application for analyzing the financial impact of retracted articles for the National Institutes of Health (NIH), using data from the Retraction Watch Database and the NIH ExPORTER. 

Designed as a **Living Analysis**, this project features a fully automated weekly workflow that updates the underlying dataset and redeploys an interactive public dashboard to reflect the most current state of retracted biomedical literature.

## 📊 Dashboard

The interactive dashboard visualizing the results of this analysis can be accessed here: [https://sandovallentisco.shinyapps.io/nih-retractions/](https://sandovallentisco.shinyapps.io/nih-retractions/)

## 🗂️ Project Structure

The project is divided into a Python-based data processing backend and an R-based frontend dashboard.

```text
📁 pubmed_funding_project/
├── 📁 data/
│   ├── 📁 raw/                           # Raw material (Unprocessed data from NIH and Retraction Watch)
│   └── 📁 processed/                     # Generated CSVs by the Python pipeline, read by the R Shiny app
├── 📁 src/                               # Specialized Python modules for the data pipeline
│   ├── config.py                         # Global paths and API credentials setup (.env)
│   ├── data_handler.py                   # Filters US papers and removes publisher-error retractions
│   ├── entrez_client.py                  # Connects to PubMed to extract study designs and Grants
│   ├── pipeline.py                       # Orchestrates PubMed metadata extraction
│   ├── nih_merger.py                     # Aggregates NIH rows into total grant costs
│   ├── pi_history_generator.py           # Builds the yearly funding history for authors
│   ├── funding_cleaner_linker.py         # Matches PubMed Grants with NIH dollars
│   ├── publication_counter.py            # Counts how many papers each Grant has produced
│   └── author_funding_matcher.py         # Calculates pre/post retraction metrics for survival analysis
├── main.py                               # CLI entry point to run the pipeline steps manually
├── app.R                                 # ShinyApp R script for the dashboard frontend
├── .github/workflows/weekly_update.yml   # GitHub Actions workflow for weekly automation
├── SETUP.md                              # Detailed guide on repository and GitHub Actions setup
└── requirements.txt                      # Python dependencies
```

## ⚙️ Automated Weekly Workflow

To ensure the analysis remains current, the entire data ingestion, processing, and deployment pipeline is automated using **GitHub Actions**. 

Every Sunday at 06:00 UTC, the workflow automatically:
1. Provisions an Ubuntu environment.
2. Downloads the latest datasets from Retraction Watch and NIH ExPORTER.
3. Runs the data processing scripts (`main.py`), querying the NCBI Entrez API for updated publication metadata.
4. Commits the newly processed datasets back to the `data/processed/` directory in this repository, maintaining transparent data versioning.
5. Deploys the updated `app.R` dashboard to `shinyapps.io` via an automated R script.

## 🚀 Local Setup & Execution

If you wish to run the pipeline locally or modify the dashboard, follow these steps:

### Requirements
* Python 3.11+
* R 4.3+
* A valid NCBI Entrez Email and API Key (for querying PubMed metadata).

### 1. Environment Setup
Clone the repository and install the required Python packages:

```bash
git clone <repository_url>
cd pubmed_funding_project
pip install -r requirements.txt
```

Create a `.env` file in the project root with your NCBI credentials:
```env
ENTREZ_EMAIL=your_email@example.com
ENTREZ_API_KEY=your_ncbi_api_key
```

### 2. Running the Pipeline
You can run the entire data processing pipeline manually via the command line. This will sequentially execute all data matching, cleaning, and financial calculation steps.

```bash
python main.py --steps all
```

*Note: The first execution requires downloading the raw NIH dataset. See `SETUP.md` for detailed instructions on initial setup and downloading historical data.*

### 3. Running the Dashboard
To launch the dashboard locally, open `app.R` in RStudio or run the following command in your R console:

```R
shiny::runApp("app.R")
```

## 📖 Additional Documentation

For more detailed instructions regarding setting up the GitHub Actions automation, obtaining API tokens, and maintaining the NIH ExPORTER data release, please consult the [SETUP.md](SETUP.md) file.
