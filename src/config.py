# =============================================================================
# GLOBAL CONFIGURATION & AUTHENTICATION
# =============================================================================
import os
from dotenv import load_dotenv
from Bio import Entrez

# 1. BULLETPROOF PATH RESOLUTION
# This dynamically finds the absolute path of your project root (one folder up from src/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load environment variables explicitly from that exact path
load_dotenv(ENV_PATH)

# Define input/output file paths for the data ingestion and export phases.
INPUT_FILE = os.path.join(BASE_DIR, "data", "raw", "retraction_watch", "retraction_watch.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "retraction_watch_with_funding.csv")

# 2. CREDENTIAL EXTRACTION & CLEANING
# We use .get() and .strip() to ensure no accidental spaces or quotes are included
EMAIL = os.environ.get("ENTREZ_EMAIL", "").strip()
API_KEY = os.environ.get("ENTREZ_API_KEY", "").strip()

# Assign credentials to the Entrez global configuration.
Entrez.email = EMAIL
if API_KEY:
    Entrez.api_key = API_KEY