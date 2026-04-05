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
_PRINT_FIELDS = "id,date,startDate,estimatedTotalAmt,fundsObligated,cfdaNumber"


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
        # Awards without per-year obligation data (fundsObligated empty) are
        # kept with amt=0 so they contribute to counts but not dollars.
        # This affects ~1% of awards consistently across all FYs.
        # The alternative (falling back to estimatedTotalAmt) was removed
        # because that field can overstate multi-year grants and did so
        # slightly more in earlier years, creating a small upward bias
        # in historical baselines.

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


def _parse_funds_obligated_entry(entry: str) -> tuple[int | None, int]:
    """Parse 'FY 2024 = $29,000.00' into (fiscal_year, amount)."""
    try:
        parts = entry.split("=")
        fy_str = parts[0].strip().replace("FY ", "")
        fy = int(fy_str)
        amt = int(float(parts[1].strip().replace("$", "").replace(",", "")))
        return fy, amt
    except (ValueError, IndexError):
        return None, 0


def _extract_records_all_years(
    awards: list[dict], target_fys: set[int], decision_fy: int,
) -> list[dict]:
    """Extract records for every FY with funds obligated, plus the decision-date FY.

    Two sources of records per award:
    1. The decision-date FY gets a record using the first fundsObligated entry
       (same logic as the new-awards pipeline — see CLAUDE.md on why FY-matching
       fails for ~7% of awards).
    2. Every OTHER target FY that appears in the fundsObligated array gets a
       record using that entry's dollar amount, dated to March 1 of that FY
       (approximation — exact obligation date isn't available).
    """
    records = []
    for a in awards:
        cfda = a.get("cfdaNumber", "")
        award_cfdas = [c.strip() for c in cfda.split(",")]
        if not any(c in NSF_AWARD_CFDAS for c in award_cfdas):
            continue

        fo_list = a.get("fundsObligated", [])
        award_id = a.get("id", "")
        decision_date = a.get("date", "")

        # Parse decision date
        date_str = ""
        if decision_date:
            try:
                dt = datetime.strptime(decision_date, "%m/%d/%Y")
                date_str = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        emitted_fys = set()

        # Record 1: decision-date FY gets first fundsObligated entry (unconditional)
        if decision_fy in target_fys and fo_list:
            amt = 0
            try:
                parts = fo_list[0].split("=")
                amt = int(float(parts[1].strip().replace("$", "").replace(",", "")))
            except (ValueError, IndexError):
                pass
            records.append({
                "fiscal_year": decision_fy,
                "date": date_str,
                "agency": "NSF",
                "award_id": award_id,
                "award_amount": amt,
                "cfda_number": cfda,
            })
            emitted_fys.add(decision_fy)

        # Record 2+: other FYs from fundsObligated entries
        # Date these by adding yearly increments to the decision date,
        # so continuing awards land at the same calendar position each year.
        for entry in fo_list:
            fy, amt = _parse_funds_obligated_entry(entry)
            if fy is None or fy not in target_fys or fy in emitted_fys:
                continue
            offset_date = ""
            if decision_date and date_str:
                try:
                    dt = datetime.strptime(decision_date, "%m/%d/%Y")
                    year_diff = fy - decision_fy
                    offset_dt = dt.replace(year=dt.year + year_diff)
                    offset_date = offset_dt.strftime("%Y-%m-%d")
                except (ValueError, OverflowError):
                    offset_date = f"{fy}-03-01"
            else:
                offset_date = f"{fy}-03-01"
            records.append({
                "fiscal_year": fy,
                "date": offset_date,
                "agency": "NSF",
                "award_id": award_id,
                "award_amount": amt,
                "cfda_number": cfda,
            })
            emitted_fys.add(fy)

    return records


def fetch_nsf_all_awards(
    fiscal_year: int,
    target_fys: set[int],
    force: bool = False,
) -> list[dict]:
    """Fetch NSF awards for one decision-date FY and extract records for all target FYs.

    Reuses the same cache as the new-awards pipeline.
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
        all_records.extend(_extract_records_all_years(awards, target_fys, decision_fy=fiscal_year))
    return all_records


def fetch_nsf_all_fys_all_awards(
    fiscal_years: list[int] | None = None, force: bool = False,
) -> pd.DataFrame:
    """Fetch NSF awards for all FYs, extracting funds-obligated records across years.

    For each decision-date FY, scans the fundsObligated array to find obligations
    in any target FY. This captures continuing awards where funds are obligated
    in years after the original decision.
    """
    from config import AWARDS_FISCAL_YEARS

    years = fiscal_years or AWARDS_FISCAL_YEARS
    target_fys = set(years)
    all_records = []

    for fy in years:
        print(f"NSF Awards (all obligations): FY{fy}")
        records = fetch_nsf_all_awards(fy, target_fys=target_fys, force=force)
        all_records.extend(records)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    # Deduplicate: same award_id + fiscal_year should appear only once
    df = df.drop_duplicates(subset=["award_id", "fiscal_year"], keep="first")
    return df
