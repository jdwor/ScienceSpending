"""
Preprocess "all awards" data (new + continuing) for all agencies.

Uses USASpending with action_date as a unified source for all agencies,
capturing continuations, modifications, and new awards.

    python3 -m awards.preprocess_all [--force]

Produces:
    awards/processed/award_series_all.csv
    awards/processed/award_summary_all.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

from awards.fetch_all import fetch_all_awards_all, fetch_all_freshness_all
from awards.transform import build_award_series, build_award_summary

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def main(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
):
    print("=== All Awards Pipeline (USASpending, action_date) ===")
    print()

    print("Fetching all-awards data...")
    raw = fetch_all_awards_all(
        fiscal_years=fiscal_years, agency_keys=agency_keys, force=force,
    )
    for key, df in raw.items():
        print(f"  {key}: {len(df)} monthly records")
    print()

    # All agencies use USASpending format — patch AWARDS_CONFIG so
    # transform.py routes everything through _build_monthly_cumulative.
    import config
    original_config = dict(config.AWARDS_CONFIG)
    for key in raw:
        config.AWARDS_CONFIG[key] = {
            **config.AWARDS_CONFIG.get(key, {}),
            **config.ALL_AWARDS_CONFIG.get(key, {}),
            "source": "usaspending",
        }

    print("Fetching freshness data...")
    freshness = fetch_all_freshness_all(
        agency_keys=list(raw.keys()), force=force,
    )
    for key, dt in freshness.items():
        print(f"  {key}: max last_modified_date = {dt}")

    print("\nBuilding cumulative series...")
    series = build_award_series(raw, freshness_data=freshness)
    print(f"  {len(series)} series rows")

    summary = build_award_summary(series)
    print(f"  {len(summary)} summary rows")
    print()

    # Restore original config
    config.AWARDS_CONFIG = original_config

    series_path = PROCESSED_DIR / "award_series_all.csv"
    series.to_csv(series_path, index=False)
    print(f"Wrote {series_path}")

    summary_path = PROCESSED_DIR / "award_summary_all.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all-awards pipeline")
    parser.add_argument("--years", type=int, nargs="+", default=None)
    parser.add_argument("--agencies", nargs="+", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(
        fiscal_years=args.years,
        agency_keys=args.agencies,
        force=args.force,
    )
