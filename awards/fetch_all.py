"""
Fetch dispatcher for "all awards" pipeline (new + continuing).

Uses USASpending with action_date for all agencies, providing a consistent
data source that captures continuations, modifications, and new awards.
Separate cache from the unified (new_awards_only) pipeline.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import (
    AWARDS_FISCAL_YEARS,
    CURRENT_FY,
    USASPENDING_AWARD_TYPE_CODES,
    USASPENDING_AWARD_SEARCH_URL,
    USASPENDING_TIME_URL,
)
from awards.fetch_usaspending_unified import USA_UNIFIED_CONFIG

CACHE_DIR = Path(__file__).parent / "cache" / "usaspending_all"
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


def fetch_all_awards_agency(
    agency_key: str, fiscal_year: int, force: bool = False,
) -> pd.DataFrame:
    """Fetch monthly all-award obligations for one agency/FY via USASpending."""
    cfg = USA_UNIFIED_CONFIG[agency_key]
    cache_file = _cache_path(agency_key, fiscal_year)

    if not force and _cache_is_fresh(cache_file, fiscal_year):
        with open(cache_file) as f:
            raw = json.load(f)
    else:
        import time as _time
        print(f"  Fetching USASpending (all awards) {agency_key} FY{fiscal_year}...")
        start = f"{fiscal_year - 1}-10-01"
        end = f"{fiscal_year}-09-30"
        filters = {
            "agencies": cfg["agencies"],
            "award_type_codes": USASPENDING_AWARD_TYPE_CODES,
            "time_period": [
                {"start_date": start, "end_date": end, "date_type": "action_date"}
            ],
        }
        if cfg["cfda"]:
            filters["program_numbers"] = cfg["cfda"]

        payload = {"group": "month", "filters": filters}
        raw = None
        for attempt in range(3):
            try:
                resp = requests.post(USASPENDING_TIME_URL, json=payload, timeout=120)
                resp.raise_for_status()
                raw = resp.json()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < 2:
                    print(f"    Retry {attempt + 1} after error: {e}")
                    _time.sleep(3 * (attempt + 1))
                else:
                    raise
        if raw is None:
            raw = {"results": []}
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump(raw, f)

    records = []
    for entry in raw.get("results", []):
        tp = entry.get("time_period", {})
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
    return pd.DataFrame(records).sort_values("fy_month")


def fetch_all_awards_all(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch all-awards data for all agencies via USASpending."""
    years = fiscal_years or AWARDS_FISCAL_YEARS
    keys = agency_keys or list(USA_UNIFIED_CONFIG.keys())

    results = {}
    for key in keys:
        frames = []
        for fy in years:
            print(f"USASpending (all awards): {key} FY{fy}")
            df = fetch_all_awards_agency(key, fy, force=force)
            if not df.empty:
                frames.append(df)
        if frames:
            results[key] = pd.concat(frames, ignore_index=True)
    return results


def fetch_all_freshness_all(
    agency_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Fetch freshness (max last_modified_date) for all agencies."""
    keys = agency_keys or list(USA_UNIFIED_CONFIG.keys())
    freshness = {}

    for key in keys:
        cache_file = CACHE_DIR / f"{key}_fy{CURRENT_FY}_freshness.json"
        if not force and _cache_is_fresh(cache_file, CURRENT_FY):
            with open(cache_file) as f:
                cached = json.load(f)
            result = cached.get("max_last_modified_date")
            if result:
                freshness[key] = result
            continue

        cfg = USA_UNIFIED_CONFIG[key]
        start = f"{CURRENT_FY - 1}-10-01"
        end = f"{CURRENT_FY}-09-30"
        filters = {
            "agencies": cfg["agencies"],
            "award_type_codes": USASPENDING_AWARD_TYPE_CODES,
            "time_period": [
                {"start_date": start, "end_date": end, "date_type": "action_date"}
            ],
        }
        if cfg["cfda"]:
            filters["program_numbers"] = cfg["cfda"]

        payload = {
            "filters": filters,
            "fields": ["Award ID", "Last Modified Date"],
            "limit": 1,
            "page": 1,
            "sort": "Last Modified Date",
            "order": "desc",
        }

        try:
            print(f"  Fetching freshness (all awards) {key} FY{CURRENT_FY}...")
            resp = requests.post(USASPENDING_AWARD_SEARCH_URL, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  WARNING: freshness fetch failed for {key}: {exc}")
            continue

        results_list = data.get("results", [])
        max_date = None
        if results_list:
            raw_date = results_list[0].get("Last Modified Date", "")
            max_date = raw_date[:10] if raw_date else None

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump({"max_last_modified_date": max_date}, f)

        if max_date:
            freshness[key] = max_date

    return freshness
