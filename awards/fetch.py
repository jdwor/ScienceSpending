"""
Orchestrator: dispatch award fetches to the correct API client per agency.
"""
from __future__ import annotations

import pandas as pd

from config import AWARDS_CONFIG, AWARDS_FISCAL_YEARS


def fetch_all_awards(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """
    Fetch award data for all (or selected) agencies and fiscal years.

    Returns {agency_key: DataFrame} where the DataFrame schema varies
    by source but always has: fiscal_year, date or fy_month, agency.
    """
    from awards.fetch_nih import fetch_nih_all
    from awards.fetch_nsf import fetch_nsf_all
    from awards.fetch_usaspending import fetch_usaspending_all

    years = fiscal_years or AWARDS_FISCAL_YEARS
    keys = agency_keys or list(AWARDS_CONFIG.keys())

    results: dict[str, pd.DataFrame] = {}

    # NIH: fetch once, share with all NIH-family keys (parent + sub-agencies)
    nih_keys = [k for k in keys if k == "NIH" or AWARDS_CONFIG.get(k, {}).get("source") == "nih_reporter"]
    if nih_keys:
        df = fetch_nih_all(fiscal_years=years, force=force)
        if not df.empty:
            for k in nih_keys:
                results[k] = df

    # NSF: fetch once, share with all NSF-family keys
    nsf_keys = [k for k in keys if k == "NSF" or AWARDS_CONFIG.get(k, {}).get("source") == "nsf_awards"]
    if nsf_keys:
        df = fetch_nsf_all(fiscal_years=years, force=force)
        if not df.empty:
            for k in nsf_keys:
                results[k] = df

    # USASpending agencies (each makes its own API call with distinct CFDAs)
    usa_keys = [k for k in keys if AWARDS_CONFIG.get(k, {}).get("source") == "usaspending"]
    if usa_keys:
        usa_data = fetch_usaspending_all(
            agency_keys=usa_keys, fiscal_years=years, force=force
        )
        results.update(usa_data)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch award data from APIs")
    parser.add_argument(
        "--years", type=int, nargs="+", default=None,
        help="Fiscal years to fetch (default: all configured)",
    )
    parser.add_argument(
        "--agencies", nargs="+", default=None,
        help="Agency keys to fetch (default: all)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-fetch even if cache is fresh",
    )
    args = parser.parse_args()

    data = fetch_all_awards(
        fiscal_years=args.years,
        agency_keys=args.agencies,
        force=args.force,
    )
    for key, df in data.items():
        print(f"{key}: {len(df)} records")
