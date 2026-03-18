"""
Fetch competing award data from the NIH Reporter API.

Retrieves Type 1 (new) and Type 2 (competing renewal) awards for each
fiscal year, partitioned by IC to stay under the 15,000-record API limit.
Results are cached locally; completed fiscal years are cached permanently,
while the current FY is re-fetched if the cache is older than 24 hours.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import (
    CURRENT_FY,
    NIH_COMPETING_TYPES,
    NIH_IC_CODES,
    NIH_REPORTER_MAX_OFFSET,
    NIH_REPORTER_PAGE_SIZE,
    NIH_REPORTER_RATE_LIMIT,
    NIH_REPORTER_URL,
)

CACHE_DIR = Path(__file__).parent / "cache" / "nih"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_last_request_time: float = 0.0


def _rate_limit():
    """Enforce minimum delay between API requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < NIH_REPORTER_RATE_LIMIT:
        time.sleep(NIH_REPORTER_RATE_LIMIT - elapsed)
    _last_request_time = time.time()


def _cache_path(fiscal_year: int, ic: str) -> Path:
    return CACHE_DIR / f"fy{fiscal_year}_{ic}.json"


def _cache_is_fresh(path: Path, fiscal_year: int) -> bool:
    """Completed FYs are cached forever; current FY expires after 24h."""
    if not path.exists():
        return False
    if fiscal_year < CURRENT_FY:
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=24)


def _fetch_page(payload: dict) -> dict:
    """POST one page to the NIH Reporter API."""
    _rate_limit()
    resp = requests.post(
        NIH_REPORTER_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_ic(fiscal_year: int, ic: str) -> list[dict]:
    """Fetch all competing awards for one IC in one FY, paginating."""
    all_results = []
    offset = 0

    while offset <= NIH_REPORTER_MAX_OFFSET:
        payload = {
            "criteria": {
                "fiscal_years": [fiscal_year],
                "award_types": NIH_COMPETING_TYPES,
                "exclude_subprojects": True,
                "agencies": [ic],
            },
            "offset": offset,
            "limit": NIH_REPORTER_PAGE_SIZE,
        }
        data = _fetch_page(payload)
        results = data.get("results", [])
        all_results.extend(results)

        total = data.get("meta", {}).get("total", 0)
        if offset + len(results) >= total or len(results) < NIH_REPORTER_PAGE_SIZE:
            break
        offset += NIH_REPORTER_PAGE_SIZE

    return all_results


def _extract_records(results: list[dict], fiscal_year: int) -> list[dict]:
    """Extract the fields we need from raw API results.

    Excludes intramural research records (activity codes starting with 'Z'),
    which are internal laboratory allocations, not extramural grants.
    """
    records = []
    for r in results:
        # Skip intramural research (ZIA, ZIC, ZID, etc.)
        activity = r.get("activity_code", "") or ""
        if activity.startswith("Z"):
            continue

        admin = r.get("agency_ic_admin") or {}
        records.append({
            "fiscal_year": fiscal_year,
            "date": (r.get("award_notice_date") or "")[:10],
            "agency": "NIH",
            "ic_code": admin.get("abbreviation", ""),
            "award_type": r.get("award_type", ""),
            "project_num": r.get("project_num", ""),
            "award_amount": r.get("award_amount") or 0,
            "activity_code": activity,
        })
    return records


def fetch_nih_awards(
    fiscal_year: int, force: bool = False
) -> pd.DataFrame:
    """
    Fetch all competing (Type 1+2) NIH awards for a fiscal year.

    Returns DataFrame with columns:
        fiscal_year, date, agency, ic_code, award_type, project_num,
        award_amount, activity_code
    """
    all_records = []

    for ic in NIH_IC_CODES:
        cache_file = _cache_path(fiscal_year, ic)

        if not force and _cache_is_fresh(cache_file, fiscal_year):
            with open(cache_file) as f:
                results = json.load(f)
        else:
            print(f"  Fetching NIH FY{fiscal_year} / {ic}...")
            results = _fetch_ic(fiscal_year, ic)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(results, f)

        all_records.extend(_extract_records(results, fiscal_year))

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    # Deduplicate — a project could appear under multiple IC queries
    # if funded by multiple ICs. Keep the first (admin IC).
    df = df.drop_duplicates(subset=["project_num", "fiscal_year"], keep="first")
    return df


def fetch_nih_all(
    fiscal_years: list[int] | None = None, force: bool = False
) -> pd.DataFrame:
    """Fetch NIH awards for multiple fiscal years."""
    from config import AWARDS_FISCAL_YEARS

    years = fiscal_years or AWARDS_FISCAL_YEARS
    frames = []
    for fy in years:
        print(f"NIH Reporter: FY{fy}")
        df = fetch_nih_awards(fy, force=force)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
