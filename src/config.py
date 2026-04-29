# =============================================================================
# GLOBAL CONFIGURATION & AUTHENTICATION
# =============================================================================
# Resolves the project's filesystem layout relative to this file's location
# (so the package keeps working regardless of the user's current working
# directory) and loads NCBI Entrez credentials from a ``.env`` file at the
# project root. Importing this module has the side-effect of configuring
# ``Bio.Entrez`` globally with those credentials.
# =============================================================================
import os

from Bio import Entrez
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------
# ``BASE_DIR`` points at the repository root (one folder above ``src/``)
# regardless of where Python is invoked from.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load environment variables from the project-root ``.env`` file. The file
# is git-ignored and must contain at least ``ENTREZ_EMAIL``.
load_dotenv(ENV_PATH)

# Canonical input/output paths consumed by the step-1 pipeline.
INPUT_FILE = os.path.join(BASE_DIR, "data", "raw", "retraction_watch", "retraction_watch.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "processed", "retraction_watch_with_funding.csv")

# ---------------------------------------------------------------------------
# Entrez credentials
# ---------------------------------------------------------------------------
# ``.get`` and ``.strip`` defend against the common mistake of leaving
# trailing whitespace or quotes around values in the ``.env`` file.
EMAIL = os.environ.get("ENTREZ_EMAIL", "").strip()
API_KEY = os.environ.get("ENTREZ_API_KEY", "").strip()

# Configure ``Bio.Entrez`` once at import time so every downstream module
# that imports from this file inherits the authenticated client.
Entrez.email = EMAIL
if API_KEY:
    Entrez.api_key = API_KEY
