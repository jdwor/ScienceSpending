"""
Preprocess USASpending unified data for all 5 agencies.

This is an experimental comparison pipeline. Run separately from the
main awards pipeline:

    python3 -m awards.preprocess_unified [--force]

Produces:
    awards/processed/award_series_unified.csv
    awards/processed/award_summary_unified.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

from awards.fetch_usaspending_unified import fetch_all_unified, fetch_all_unified_freshness
from awards.transform import build_award_series, build_award_summary

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def main(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
):
    print("=== USASpending Unified Pipeline (Experimental) ===")
    print()

    print("Fetching from USASpending for all agencies...")
    raw = fetch_all_unified(
        agency_keys=agency_keys, fiscal_years=fiscal_years, force=force
    )
    for key, df in raw.items():
        print(f"  {key}: {len(df)} monthly records")
    print()

    # The transform pipeline expects USASpending-style data (fy_month, obligation_amount).
    # All agencies in the unified pipeline use this format, so we can reuse the
    # existing _build_monthly_cumulative path by setting source to "usaspending"
    # in a temporary AWARDS_CONFIG override.

    # Monkey-patch AWARDS_CONFIG temporarily so transform.py treats all agencies
    # as usaspending source type
    import config
    original_config = dict(config.AWARDS_CONFIG)
    for key in raw:
        if key not in config.AWARDS_CONFIG:
            config.AWARDS_CONFIG[key] = {}
        config.AWARDS_CONFIG[key] = {
            **config.AWARDS_CONFIG.get(key, {}),
            "source": "usaspending",
            "metric_label": "New Awards (USASpending)",
            "metric_label_short": "Awards",
        }

    print("Fetching USASpending freshness data...")
    freshness = fetch_all_unified_freshness(agency_keys=list(raw.keys()), force=force)
    for key, dt in freshness.items():
        print(f"  {key}: last modified {dt}")

    print("Building cumulative series...")
    series = build_award_series(raw, freshness_data=freshness)
    print(f"  {len(series)} series rows")

    summary = build_award_summary(series)
    print(f"  {len(summary)} summary rows")
    print()

    # Restore original config
    config.AWARDS_CONFIG = original_config

    series_path = PROCESSED_DIR / "award_series_unified.csv"
    series.to_csv(series_path, index=False)
    print(f"Wrote {series_path}")

    summary_path = PROCESSED_DIR / "award_summary_unified.csv"
    summary.to_csv(summary_path, index=False)
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run unified USASpending pipeline")
    parser.add_argument("--years", type=int, nargs="+", default=None)
    parser.add_argument("--agencies", nargs="+", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    main(
        fiscal_years=args.years,
        agency_keys=args.agencies,
        force=args.force,
    )
