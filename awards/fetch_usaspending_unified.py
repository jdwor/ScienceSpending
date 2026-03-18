"""
Fetch new-award data from USASpending.gov for ALL five agencies.

This is a comparison/experimental module that uses USASpending as a
unified data source, replacing the agency-specific APIs (NIH Reporter,
NSF Awards) with USASpending queries. This allows apples-to-apples
comparison of the data source differences.

For NIH: uses awarding subtier agency filter (data from FY2017+).
For NSF: uses CFDA program number filter (same codes as NSF Awards API).
For DOE/NASA/USDA: uses the same config as the main pipeline.
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
    USASPENDING_TIME_URL,
)

CACHE_DIR = Path(__file__).parent / "cache" / "usaspending_unified"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Unified USASpending configuration for all 5 agencies.
# NIH and NSF use different filter strategies than DOE/NASA/USDA.
USA_UNIFIED_CONFIG = {
    "NIH": {
        "agencies": [
            {
                "type": "awarding",
                "tier": "subtier",
                "name": "National Institutes of Health",
            }
        ],
        # No CFDA filter — subtier agency is sufficient for NIH
        "cfda": None,
    },
    "NSF": {
        "agencies": [
            {
                "type": "funding",
                "tier": "toptier",
                "name": "National Science Foundation",
            }
        ],
        "cfda": [
            "47.041", "47.049", "47.050", "47.070", "47.074", "47.075",
            "47.076", "47.083", "47.084",
        ],
    },
    "DOE_SC": {
        "agencies": [
            {
                "type": "funding",
                "tier": "toptier",
                "name": "Department of Energy",
            }
        ],
        "cfda": ["81.049"],
    },
    "NASA_SCI": {
        "agencies": [
            {
                "type": "funding",
                "tier": "toptier",
                "name": "National Aeronautics and Space Administration",
            }
        ],
        "cfda": ["43.001", "43.013"],
    },
    "USDA_RD": {
        "agencies": [
            {
                "type": "funding",
                "tier": "toptier",
                "name": "Department of Agriculture",
            }
        ],
        "cfda": ["10.310"],
    },
}


def _cache_path(agency_key: str, fiscal_year: int) -> Path:
    return CACHE_DIR / f"{agency_key}_fy{fiscal_year}.json"


def _cache_is_fresh(path: Path, fiscal_year: int) -> bool:
    if not path.exists():
        return False
    if fiscal_year < CURRENT_FY:
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=24)


def fetch_unified(
    agency_key: str, fiscal_year: int, force: bool = False
) -> pd.DataFrame:
    """Fetch monthly new-award obligations for one agency/FY via USASpending."""
    cfg = USA_UNIFIED_CONFIG[agency_key]
    cache_file = _cache_path(agency_key, fiscal_year)

    if not force and _cache_is_fresh(cache_file, fiscal_year):
        with open(cache_file) as f:
            raw = json.load(f)
    else:
        print(f"  Fetching USASpending (unified) {agency_key} FY{fiscal_year}...")
        import time as _time
        start = f"{fiscal_year - 1}-10-01"
        end = f"{fiscal_year}-09-30"
        filters = {
            "agencies": cfg["agencies"],
            "award_type_codes": USASPENDING_AWARD_TYPE_CODES,
            "time_period": [
                {"start_date": start, "end_date": end, "date_type": "new_awards_only"}
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


def fetch_all_unified(
    agency_keys: list[str] | None = None,
    fiscal_years: list[int] | None = None,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch USASpending data for all agencies."""
    keys = agency_keys or list(USA_UNIFIED_CONFIG.keys())
    years = fiscal_years or AWARDS_FISCAL_YEARS

    results = {}
    for key in keys:
        frames = []
        for fy in years:
            print(f"USASpending (unified): {key} FY{fy}")
            df = fetch_unified(key, fy, force=force)
            if not df.empty:
                frames.append(df)
        if frames:
            results[key] = pd.concat(frames, ignore_index=True)
    return results
