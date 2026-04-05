"""
Fetch monthly grant obligation data from the USASpending.gov API.

Used for DOE Office of Science, NASA Science, and USDA where no
agency-specific grants API is available.  Returns monthly aggregated
obligation amounts filtered by CFDA program numbers.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import (
    AWARDS_CONFIG,
    CURRENT_FY,
    USASPENDING_AWARD_SEARCH_URL,
    USASPENDING_AWARD_TYPE_CODES,
    USASPENDING_TIME_URL,
)

CACHE_DIR = Path(__file__).parent / "cache" / "usaspending"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(agency_key: str, fiscal_year: int) -> Path:
    return CACHE_DIR / f"{agency_key}_fy{fiscal_year}.json"


def _cache_is_fresh(path: Path, fiscal_year: int) -> bool:
    if not path.exists():
        return False
    if fiscal_year < CURRENT_FY:
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=24)


def _fy_date_range(fiscal_year: int) -> tuple[str, str]:
    """Return (start, end) date strings for a fiscal year."""
    return (
        f"{fiscal_year - 1}-10-01",
        f"{fiscal_year}-09-30",
    )


def _cal_month_to_fy_month(cal_month: int) -> int:
    """Convert calendar month (1-12) to fiscal year month (Oct=1 ... Sep=12)."""
    return (cal_month - 10) % 12 + 1


def fetch_usaspending_awards(
    agency_key: str,
    fiscal_year: int,
    force: bool = False,
    date_type: str = "new_awards_only",
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Fetch monthly grant obligation time series for one agency/FY.

    Parameters:
        date_type: USASpending date filter ("new_awards_only" or "action_date").
        cache_dir: Override cache directory (for "all awards" pipeline).

    Returns DataFrame with columns:
        fiscal_year, fy_month, agency, obligation_amount
    """
    cfg = AWARDS_CONFIG[agency_key]
    cdir = cache_dir or CACHE_DIR
    cache_file = cdir / f"{agency_key}_fy{fiscal_year}.json"

    if not force and _cache_is_fresh(cache_file, fiscal_year):
        with open(cache_file) as f:
            raw = json.load(f)
    else:
        print(f"  Fetching USASpending {agency_key} FY{fiscal_year}...")
        start, end = _fy_date_range(fiscal_year)
        payload = {
            "group": "month",
            "filters": {
                "agencies": [
                    {
                        "type": "funding",
                        "tier": cfg["agency_tier"],
                        "name": cfg["agency_name"],
                    }
                ],
                "award_type_codes": USASPENDING_AWARD_TYPE_CODES,
                "time_period": [{"start_date": start, "end_date": end, "date_type": date_type}],
                "program_numbers": cfg["cfda"],
            },
        }
        resp = requests.post(
            USASPENDING_TIME_URL, json=payload, timeout=60
        )
        resp.raise_for_status()
        raw = resp.json()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(raw, f)

    records = []
    for entry in raw.get("results", []):
        tp = entry.get("time_period", {})
        # USASpending spending_over_time returns fiscal year months
        # (1=Oct, 2=Nov, ..., 12=Sep) when filtered by fiscal year
        fy_month = int(tp.get("month", 0))
        if fy_month == 0:
            continue
        amount = float(entry.get("aggregated_amount", 0) or 0)
        records.append({
            "fiscal_year": fiscal_year,
            "fy_month": fy_month,
            "agency": agency_key,
            "obligation_amount": amount,
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).sort_values("fy_month")
    return df


def fetch_usaspending_freshness(
    agency_key: str,
    fiscal_year: int,
    force: bool = False,
    date_type: str = "new_awards_only",
    cache_dir: Path | None = None,
) -> str | None:
    """
    Query the per-award endpoint to find the max last_modified_date for
    an agency's current-FY awards.  Returns an ISO date string (e.g.
    '2026-03-20') or None on failure / no data.

    Only meaningful for the current FY — for completed FYs, returns None.
    """
    if fiscal_year != CURRENT_FY:
        return None

    cdir = cache_dir or CACHE_DIR
    cache_file = cdir / f"{agency_key}_fy{fiscal_year}_freshness.json"

    if not force and _cache_is_fresh(cache_file, fiscal_year):
        with open(cache_file) as f:
            cached = json.load(f)
        return cached.get("max_last_modified_date")

    cfg = AWARDS_CONFIG[agency_key]
    start, end = _fy_date_range(fiscal_year)

    payload = {
        "filters": {
            "agencies": [
                {
                    "type": "funding",
                    "tier": cfg["agency_tier"],
                    "name": cfg["agency_name"],
                }
            ],
            "award_type_codes": USASPENDING_AWARD_TYPE_CODES,
            "time_period": [
                {"start_date": start, "end_date": end, "date_type": date_type}
            ],
            "program_numbers": cfg["cfda"],
        },
        "fields": ["Award ID", "Last Modified Date"],
        "limit": 1,
        "page": 1,
        "sort": "Last Modified Date",
        "order": "desc",
    }

    try:
        print(f"  Fetching USASpending freshness {agency_key} FY{fiscal_year}...")
        resp = requests.post(USASPENDING_AWARD_SEARCH_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  WARNING: freshness fetch failed for {agency_key}: {exc}")
        return None

    results = data.get("results", [])
    if not results:
        return None

    # last_modified_date looks like '2026-03-20T15:40:52.263484'
    raw_date = results[0].get("Last Modified Date", "")
    max_date = raw_date[:10] if raw_date else None

    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump({"max_last_modified_date": max_date}, f)

    return max_date


def fetch_usaspending_all(
    agency_keys: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    force: bool = False,
    date_type: str = "new_awards_only",
    cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch USASpending data for multiple agencies and fiscal years."""
    from config import AWARDS_FISCAL_YEARS

    if agency_keys is None:
        agency_keys = [
            k for k, v in AWARDS_CONFIG.items() if v["source"] == "usaspending"
        ]
    years = fiscal_years or AWARDS_FISCAL_YEARS

    results = {}
    for key in agency_keys:
        frames = []
        for fy in years:
            print(f"USASpending: {key} FY{fy}")
            df = fetch_usaspending_awards(
                key, fy, force=force, date_type=date_type, cache_dir=cache_dir,
            )
            if not df.empty:
                frames.append(df)
        if frames:
            results[key] = pd.concat(frames, ignore_index=True)
    return results


def fetch_all_freshness(
    agency_keys: list[str] | None = None,
    force: bool = False,
    date_type: str = "new_awards_only",
    cache_dir: Path | None = None,
) -> dict[str, str]:
    """Fetch freshness (max last_modified_date) for all USASpending agencies."""
    if agency_keys is None:
        agency_keys = [
            k for k, v in AWARDS_CONFIG.items() if v["source"] == "usaspending"
        ]

    freshness = {}
    for key in agency_keys:
        result = fetch_usaspending_freshness(
            key, CURRENT_FY, force=force, date_type=date_type, cache_dir=cache_dir,
        )
        if result:
            freshness[key] = result
    return freshness
