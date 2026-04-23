"""
Preprocess "all awards" data (new + continuing) for all agencies.

Uses NIH Reporter (types 1+2+3+4+5+7+9 — all extramural grant actions)
for NIH and its sub-agencies, and USASpending with action_date for DOE,
NASA, and USDA — capturing continuations, modifications, and new awards.

    python3 -m awards.preprocess_all [--force]

Produces:
    awards/processed/award_series_all.csv
    awards/processed/award_summary_all.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

from awards.fetch_all import fetch_all_awards_all, fetch_all_freshness_all
from awards.fetch_nih import fetch_nih_all
from awards.transform import build_award_series, build_award_summary
from config import ALL_AWARDS_CONFIG, NIH_ALL_AWARDS_FISCAL_YEARS, NIH_ALL_TYPES

PROCESSED_DIR = Path(__file__).parent / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

NIH_CACHE_DIR = Path(__file__).parent / "cache" / "nih_all"
NIH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def main(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
):
    print("=== All Awards Pipeline ===")
    print()

    # Determine which keys to process
    all_keys = agency_keys or list(ALL_AWARDS_CONFIG.keys())

    # Split into NIH-family (use NIH Reporter) and USASpending agencies
    nih_keys = [k for k in all_keys
                if ALL_AWARDS_CONFIG.get(k, {}).get("source") == "nih_reporter"]
    usa_keys = [k for k in all_keys if k not in nih_keys]

    raw: dict = {}

    # --- NIH Reporter: fetch once with types 1+2+5, share across NIH family ---
    if nih_keys:
        print("Fetching NIH all-awards data (types 1+2+3+4+5+7+9) from NIH Reporter...")
        nih_years = fiscal_years or NIH_ALL_AWARDS_FISCAL_YEARS
        nih_df = fetch_nih_all(
            fiscal_years=nih_years, force=force,
            award_types=NIH_ALL_TYPES,
            cache_dir=NIH_CACHE_DIR,
        )
        if not nih_df.empty:
            for k in nih_keys:
                raw[k] = nih_df
            print(f"  NIH Reporter: {len(nih_df)} records (shared across {len(nih_keys)} keys)")
        print()

    # --- USASpending: DOE, NASA, USDA (action_date) ---
    if usa_keys:
        print("Fetching USASpending all-awards data...")
        usa_raw = fetch_all_awards_all(
            fiscal_years=fiscal_years, agency_keys=usa_keys, force=force,
        )
        raw.update(usa_raw)
        for key, df in usa_raw.items():
            print(f"  {key}: {len(df)} monthly records")
        print()

    # Patch AWARDS_CONFIG so transform routes each agency to the right builder
    import config
    original_config = dict(config.AWARDS_CONFIG)
    for key in raw:
        acfg = ALL_AWARDS_CONFIG.get(key, {})
        source = acfg.get("source", "usaspending")
        config.AWARDS_CONFIG[key] = {
            **config.AWARDS_CONFIG.get(key, {}),
            **acfg,
            "source": source,
        }

    # Freshness only needed for USASpending agencies
    freshness = {}
    usa_raw_keys = [k for k in raw if ALL_AWARDS_CONFIG.get(k, {}).get("source") != "nih_reporter"]
    if usa_raw_keys:
        print("Fetching freshness data...")
        freshness = fetch_all_freshness_all(
            agency_keys=usa_raw_keys, force=force,
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
