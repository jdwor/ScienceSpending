"""
Fetch new award data from the NSF Awards API.

Retrieves awards whose award decision date falls within each fiscal year,
partitioned by month to stay under the 3,000-result API limit.  Results are
filtered to Research & Related directorate CFDAs.
"""
from __future__ import annotations

import calendar
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from config import (
    CURRENT_FY,
    NSF_AWARDS_URL,
    NSF_MAX_RESULTS,
    NSF_AWARD_CFDAS,
)

CACHE_DIR = Path(__file__).parent / "cache" / "nsf"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Use large page size — NSF API is slow per-request, so fewer requests is better
_NSF_PAGE_SIZE = 250

# Only request the fields we actually need for counting and dollar totals
_PRINT_FIELDS = "id,date,startDate,estimatedTotalAmt,fundsObligatedAmt,cfdaNumber"


def _fy_months(fiscal_year: int) -> list[tuple[int, int]]:
    """Return (year, month) pairs for Oct-Sep of a fiscal year."""
    months = []
    for m in range(10, 13):
        months.append((fiscal_year - 1, m))
    for m in range(1, 10):
        months.append((fiscal_year, m))
    return months


def _cache_path(fiscal_year: int, cal_year: int, cal_month: int) -> Path:
    return CACHE_DIR / f"fy{fiscal_year}_d{cal_year}{cal_month:02d}.json"


def _cache_is_fresh(path: Path, fiscal_year: int) -> bool:
    if not path.exists():
        return False
    if fiscal_year < CURRENT_FY:
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=24)


def _fetch_month(
    cal_year: int, cal_month: int
) -> list[dict]:
    """Fetch all NSF awards with award decision date in the given calendar month."""
    last_day = calendar.monthrange(cal_year, cal_month)[1]
    start_str = f"{cal_month:02d}/01/{cal_year}"
    end_str = f"{cal_month:02d}/{last_day:02d}/{cal_year}"

    all_awards = []
    offset = 0

    while offset < NSF_MAX_RESULTS:
        params = {
            "dateStart": start_str,
            "dateEnd": end_str,
            "printFields": _PRINT_FIELDS,
            "rpp": _NSF_PAGE_SIZE,
            "offset": offset,
        }
        data = None
        for attempt in range(3):
            try:
                resp = requests.get(NSF_AWARDS_URL, params=params, timeout=120)
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < 2:
                    print(f"    Retry {attempt + 1} after error: {e}")
                    time.sleep(5 * (attempt + 1))
                else:
                    raise
        if data is None:
            break

        awards = data.get("response", {}).get("award", [])
        if not awards:
            break
        all_awards.extend(awards)

        total = int(
            data.get("response", {}).get("metadata", {}).get("totalCount", 0)
        )
        if offset + len(awards) >= total:
            break
        offset += _NSF_PAGE_SIZE

    return all_awards


def _extract_records(
    awards: list[dict], fiscal_year: int
) -> list[dict]:
    """Extract and filter to NSF directorate CFDAs."""
    records = []
    for a in awards:
        cfda = a.get("cfdaNumber", "")
        # Awards may list multiple CFDAs (e.g., "47.076, 47.083").
        # Include the award if ANY listed CFDA is in the allowed set.
        award_cfdas = [c.strip() for c in cfda.split(",")]
        if not any(c in NSF_AWARD_CFDAS for c in award_cfdas):
            continue

        # Use the first entry in the per-year fundsObligated array.
        # This is the initial obligation when the award was made.
        # The FY tag may not match the decision-date fiscal year (e.g., an Oct 2023
        # award may be tagged "FY 2023" if funded from prior-year budget), so we
        # take the first entry unconditionally rather than matching by FY.
        amt = 0
        fo_list = a.get("fundsObligated", [])
        if fo_list:
            try:
                parts = fo_list[0].split("=")
                amt = int(float(parts[1].strip().replace("$", "").replace(",", "")))
            except (ValueError, IndexError):
                amt = 0
        # Fall back to estimatedTotalAmt only if fundsObligated is empty
        if amt == 0:
            try:
                amt = int(a.get("estimatedTotalAmt", "0").replace(",", ""))
            except (ValueError, AttributeError):
                amt = 0

        # Convert award decision date from MM/DD/YYYY to YYYY-MM-DD
        date_raw = a.get("date", "")
        try:
            dt = datetime.strptime(date_raw, "%m/%d/%Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = ""

        records.append({
            "fiscal_year": fiscal_year,
            "date": date_str,
            "agency": "NSF",
            "award_id": a.get("id", ""),
            "award_amount": amt,
            "cfda_number": cfda,
        })
    return records


def fetch_nsf_awards(
    fiscal_year: int, force: bool = False
) -> pd.DataFrame:
    """
    Fetch all new NSF R&R awards for a fiscal year.

    "New" = award decision date falls within the fiscal year (Oct 1 - Sep 30).

    Returns DataFrame with columns:
        fiscal_year, date, agency, award_id, award_amount,
        funds_obligated, cfda_number
    """
    all_records = []

    for cal_year, cal_month in _fy_months(fiscal_year):
        cache_file = _cache_path(fiscal_year, cal_year, cal_month)

        if not force and _cache_is_fresh(cache_file, fiscal_year):
            with open(cache_file) as f:
                awards = json.load(f)
        else:
            month_name = calendar.month_abbr[cal_month]
            print(f"  Fetching NSF FY{fiscal_year} / {month_name} {cal_year}...")
            awards = _fetch_month(cal_year, cal_month)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(awards, f)

        all_records.extend(_extract_records(awards, fiscal_year))

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df = df.drop_duplicates(subset=["award_id"], keep="first")
    return df


def fetch_nsf_all(
    fiscal_years: list[int] | None = None, force: bool = False
) -> pd.DataFrame:
    """Fetch NSF awards for multiple fiscal years."""
    from config import AWARDS_FISCAL_YEARS

    years = fiscal_years or AWARDS_FISCAL_YEARS
    frames = []
    for fy in years:
        print(f"NSF Awards: FY{fy}")
        df = fetch_nsf_awards(fy, force=force)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
