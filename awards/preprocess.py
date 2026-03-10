"""
Orchestrate the awards pipeline: fetch → transform → CSV.

Usage:
    python3 -m awards.preprocess [--years 2025 2026] [--agencies NIH NSF] [--force]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from awards.fetch import fetch_all_awards
from awards.transform import build_award_series, build_award_summary

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def main(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
):
    print("=== Awards Pipeline ===")
    print()

    # Fetch
    print("Fetching award data...")
    raw = fetch_all_awards(
        fiscal_years=fiscal_years, agency_keys=agency_keys, force=force
    )
    for key, df in raw.items():
        print(f"  {key}: {len(df)} raw records")
    print()

    # Transform
    print("Building cumulative series...")
    series = build_award_series(raw)
    print(f"  {len(series)} series rows")

    summary = build_award_summary(series)
    print(f"  {len(summary)} summary rows")
    print()

    # Write
    series_path = PROCESSED_DIR / "award_series.csv"
    series.to_csv(series_path, index=False)
    print(f"Wrote {series_path}")

    summary_path = PROCESSED_DIR / "award_summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run awards preprocessing pipeline")
    parser.add_argument("--years", type=int, nargs="+", default=None)
    parser.add_argument("--agencies", nargs="+", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(
        fiscal_years=args.years,
        agency_keys=args.agencies,
        force=args.force,
    )
