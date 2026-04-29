"""
=============================================================================
RETRACTION WATCH x NIH FUNDING PIPELINE - ENTRYPOINT
=============================================================================
This script is the orchestrator for the entire data pipeline. It can be
invoked in two modes:

  1. Interactive (default when no CLI flags are passed): prints a numeric
     menu identical to the original behaviour. Intended for exploratory
     and ad-hoc use on a developer workstation.

  2. Non-interactive: a small ``argparse``-based interface that allows
     each individual step (or the full chain) to be triggered from CI,
     cron, or any other automated environment.

The seven pipeline steps and their inputs/outputs are documented inline in
both the menu and the ``STEPS`` registry below. The registry is the single
source of truth used by both modes, ensuring that interactive and CLI
behaviour cannot diverge.

USAGE
-----
Interactive::

    python main.py

Non-interactive::

    python main.py --steps all                 # run every step in order
    python main.py --steps 2,4,5               # run a subset of steps
    python main.py --steps all --download      # download raw data first
    python main.py --download-only             # download only, skip pipeline
=============================================================================
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict, List, Tuple

# Import the worker functions from the ``src`` package. Each function
# corresponds to a single, idempotent stage of the pipeline.
from src.pipeline import run_pipeline
from src.nih_merger import merge_nih_csvs
from src.pi_history_generator import generate_pi_history
from src.funding_cleaner_linker import link_funding_costs
from src.publication_counter import link_publication_counts
from src.author_funding_matcher import match_authors_to_funding
from src.cpi_fetcher import fetch_cpi


# ---------------------------------------------------------------------------
# Pipeline registry
# ---------------------------------------------------------------------------
# Mapping of step number -> (human readable name, callable to execute).
# Both the interactive menu and the CLI dispatcher iterate over this dict;
# adding a new step here automatically wires it into both surfaces.
STEPS: Dict[int, Tuple[str, Callable[[], object]]] = {
    1: ("Fetch PubMed metadata",                run_pipeline),
    2: ("Merge raw NIH RePORTER files",         merge_nih_csvs),
    3: ("Generate MASTER PI history",           generate_pi_history),
    4: ("Link PubMed grants to NIH costs",      link_funding_costs),
    5: ("Fetch publication counts per grant",   link_publication_counts),
    6: ("Match retracted authors to NIH grants", match_authors_to_funding),
    7: ("Refresh FRED CPI cache",               fetch_cpi),
}


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------
def show_menu() -> None:
    """Render the interactive menu. Pure presentation; no side effects."""
    print("\n" + "=" * 70)
    print(" RESEARCH FUNDING PIPELINE - MAIN MENU ".center(70))
    print("=" * 70)

    print("1. Fetch PubMed metadata (~1.5 hours on a cold cache)")
    print("   Reads:  data/raw/retraction_watch/retraction_watch.csv")
    print("   Writes: data/processed/retraction_watch_with_funding.csv\n")

    print("2. Merge raw NIH RePORTER files (aggregated costs per grant)")
    print("   Reads:  data/raw/nih_reporter/*.csv")
    print("   Writes: data/processed/MASTER_NIH_Projects.csv\n")

    print("3. Generate MASTER PI history (author-level timeline from raw)")
    print("   Reads:  data/raw/nih_reporter/*.csv")
    print("   Writes: data/processed/MASTER_PI_History.csv\n")

    print("4. Link PubMed grants to NIH costs")
    print("   Reads:  retraction_watch_with_funding.csv + MASTER_NIH_Projects.csv")
    print("   Writes: data/processed/FINAL_Retractions_with_Costs.csv\n")

    print("5. Fetch publication counts per grant")
    print("   Reads:  FINAL_Retractions_with_Costs.csv")
    print("   Writes: data/processed/FINAL_Retractions_Costs_and_Pubs.csv\n")

    print("6. Match retracted authors to all their NIH grants")
    print("   Reads:  FINAL_Retractions_Costs_and_Pubs.csv + MASTER_PI_History.csv")
    print("   Writes: data/processed/Author_Funding_Matches.csv\n")

    print("7. Refresh FRED CPI cache (annual_cpi.csv consumed by the Shiny app)")
    print("   Reads:  https://fred.stlouisfed.org/...CPIAUCSL")
    print("   Writes: data/processed/annual_cpi.csv\n")

    print("8. Run the entire pipeline (steps 1 -> 7)")
    print("D. Download raw data (Retraction Watch + NIH RePORTER)")
    print("0. Exit")
    print("=" * 70)


def parse_steps(value: str) -> List[int]:
    """Translate ``--steps`` argument into a sorted list of step numbers.

    Accepts either the literal ``all`` (case-insensitive) or a
    comma-separated list of integers. Raises ``ValueError`` if any token
    refers to a step that does not exist in ``STEPS``.
    """
    if value.lower() == "all":
        return sorted(STEPS.keys())

    out: List[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        n = int(token)
        if n not in STEPS:
            raise ValueError(
                f"Unknown step {n}; valid values are {list(STEPS)}"
            )
        out.append(n)
    return out


def run_steps(steps: List[int]) -> None:
    """Execute the requested steps in numeric order.

    Each step is logged with a banner so that interleaved output remains
    legible in CI logs.
    """
    for step in steps:
        title, func = STEPS[step]
        print(f"\n>>> STARTING STEP {step}: {title.upper()}\n")
        func()


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------
def run_cli(args: argparse.Namespace) -> int:
    """Non-interactive dispatch. Runs the requested operations in order."""
    if args.download or args.download_only:
        # Local import keeps the heavy ``requests`` dependency out of the
        # interactive code path when the user never asks for a download.
        from src.downloader import (
            download_recent_nih_years,
            download_retraction_watch,
        )

        download_retraction_watch()
        download_recent_nih_years(n_back=2, force_current=True)
        if args.download_only:
            return 0

    if args.steps:
        run_steps(parse_steps(args.steps))
    return 0


def run_interactive() -> None:
    """Interactive REPL-style menu. Returns when the user selects ``0``."""
    while True:
        show_menu()
        choice = input("\nEnter the option you want to run: ").strip()

        if choice in {"1", "2", "3", "4", "5", "6", "7"}:
            run_steps([int(choice)])
        elif choice == "8":
            run_steps(sorted(STEPS.keys()))
        elif choice.upper() == "D":
            from src.downloader import (
                download_recent_nih_years,
                download_retraction_watch,
            )
            download_retraction_watch()
            download_recent_nih_years(n_back=2, force_current=True)
        elif choice == "0":
            print("\nExiting program.")
            return
        else:
            print("\n[!] Invalid choice. Please enter 0-8 or D.")


def build_parser() -> argparse.ArgumentParser:
    """Build the ``argparse`` parser. Kept separate from ``main`` so the
    parser can be exercised in unit tests without invoking the pipeline."""
    parser = argparse.ArgumentParser(
        description="Retraction Watch + NIH funding pipeline orchestrator.",
    )
    parser.add_argument(
        "--steps",
        help=(
            "Steps to execute: 'all' or a comma-separated list, e.g. '1,2,4'. "
            "If omitted and no other flag is given, the interactive menu is "
            "launched instead."
        ),
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download Retraction Watch and NIH ExPORTER raw files before running the pipeline.",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Download raw files and exit without running the pipeline.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    # Enter interactive mode only when no CLI flag has been passed at all.
    # This preserves the original ergonomic for developers running the
    # script directly while keeping CI invocations fully deterministic.
    if not (args.steps or args.download or args.download_only):
        run_interactive()
        return 0

    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
