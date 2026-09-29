"""
Download SF-133 Excel files from the OMB MAX portal.

Reads file_registry.json to determine URLs, downloads to data/cache/,
and skips files that already exist unless --force is specified.

Use --check to detect whether new monthly data is available without
running the full preprocessing pipeline.
"""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Ensure project root is on sys.path so config.py can be imported
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
REGISTRY_PATH = PROJECT_ROOT / "file_registry.json"
BASE_URL = "https://portal.max.gov/portal/document/SF133/Budget/attachments"
# Each FY's SF-133 page on OMB MAX lists that year's attachment links
FY_PAGE_URL = (
    "https://portal.max.gov/portal/document/SF133/Budget/"
    "FY%20{fy}%20-%20SF%20133%20Reports%20on%20Budget%20Execution%20and%20Budgetary%20Resources.html"
)


def load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def download_file(url: str, dest: Path, force: bool = False) -> bool:
    """Download a single file. Returns True if downloaded, False if skipped."""
    if dest.exists() and not force:
        return False

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return True


def download_all(
    fiscal_years: list[int] | None = None,
    file_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, Path]:
    """
    Download SF-133 files for specified fiscal years and agency file keys.

    Returns a dict mapping "YYYY/key" to the local file path.
    """
    registry = load_registry()
    downloaded = {}

    for fy_str, fy_info in registry.items():
        fy = int(fy_str)
        if fiscal_years is not None and fy not in fiscal_years:
            continue

        attachment_id = fy_info["attachment_id"]
        files = fy_info["files"]

        for key, filename in files.items():
            if file_keys is not None and key not in file_keys:
                continue

            url = f"{BASE_URL}/{attachment_id}/{filename}"
            dest = CACHE_DIR / f"FY{fy}" / filename
            label = f"FY{fy}/{key}"

            try:
                was_downloaded = download_file(url, dest, force=force)
                status = "downloaded" if was_downloaded else "cached"
                print(f"  [{status}] {label}: {dest.name}")
                downloaded[label] = dest
            except requests.HTTPError as e:
                print(f"  [ERROR] {label}: {e}", file=sys.stderr)
            except requests.RequestException as e:
                print(f"  [ERROR] {label}: {type(e).__name__}", file=sys.stderr)

    return downloaded


def get_local_path(fiscal_year: int, file_key: str) -> Path | None:
    """Get the local cache path for a specific FY/agency file, or None if not available."""
    registry = load_registry()
    fy_str = str(fiscal_year)
    if fy_str not in registry:
        return None
    files = registry[fy_str].get("files", {})
    if file_key not in files:
        return None
    path = CACHE_DIR / f"FY{fiscal_year}" / files[file_key]
    return path if path.exists() else None


def list_available() -> list[tuple[int, str, bool]]:
    """List all registry entries and whether they are cached locally."""
    registry = load_registry()
    result = []
    for fy_str, fy_info in sorted(registry.items()):
        for key in sorted(fy_info.get("files", {})):
            path = get_local_path(int(fy_str), key)
            result.append((int(fy_str), key, path is not None))
    return result


def _calendar_to_fy_month(cal_month: int, cal_year: int, fiscal_year: int) -> int | None:
    """Map a calendar month/year to a fiscal-year month number (Oct=1..Sep=12)."""
    # FY starts in October of the prior calendar year
    fy_start_year = fiscal_year - 1
    if cal_year == fy_start_year and cal_month >= 10:
        return cal_month - 9  # Oct=1, Nov=2, Dec=3
    elif cal_year == fiscal_year and cal_month <= 9:
        return cal_month + 3  # Jan=4, Feb=5, ..., Sep=12
    return None


def _get_site_latest_period() -> tuple[str | None, int | None]:
    """Read site_data.json and return (latest_period_label, current_fy)."""
    site_json = PROJECT_ROOT / "docs" / "data" / "site_data.json"
    if not site_json.exists():
        return None, None
    with open(site_json) as f:
        data = json.load(f)
    cfg = data.get("config", {})
    return cfg.get("latest_period_label"), cfg.get("current_fy")


def _label_to_fy_month(label: str) -> int | None:
    """Map a period label like 'Jan' or 'Dec (Q1)' to FY month number."""
    from config import FY_MONTH_LABELS
    label_clean = label.split("(")[0].strip()
    for month_num, month_label in FY_MONTH_LABELS.items():
        if month_label == label_clean:
            return month_num
    return None


def _detect_latest_month_in_file(filepath: Path) -> int | None:
    """Quick-parse an SF-133 Excel file to find the latest populated month.

    Reads only obligations line 2190 and checks which amount columns have data.
    Returns the highest FY month number with non-zero values, or None.
    """
    from config import AMOUNT_COLUMNS

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            df = pd.read_excel(filepath, sheet_name="Raw Data", engine="openpyxl")
        except Exception:
            return None

    if df.empty:
        return None

    df.columns = [str(c).strip() for c in df.columns]

    # Filter to line 2190 (total obligations) — fastest check
    if "LINENO" not in df.columns:
        return None
    df["_lineno"] = df["LINENO"].astype(str).str.strip()
    df = df[df["_lineno"] == "2190"]

    if df.empty:
        return None

    latest = None
    for col_name, _, fy_month in AMOUNT_COLUMNS:
        if col_name in df.columns:
            vals = pd.to_numeric(df[col_name], errors="coerce")
            if vals.notna().any() and (vals != 0).any():
                latest = fy_month

    return latest


def discover_registry_entry(fiscal_year: int) -> dict | None:
    """Find a new FY's attachment ID and filenames on its OMB MAX page.

    OMB posts each FY's SF-133 files under one attachment ID, named like
    FY2026_SF133_MONTHLY_Department_of_Energy.xlsx. Expected names are derived
    from the latest registry entry. Returns None until the page exists and
    lists every tracked agency's file.
    """
    registry = load_registry()
    latest_fy = max(int(k) for k in registry)
    template = registry[str(latest_fy)]["files"]
    expected = {
        key: name.replace(f"FY{latest_fy}_", f"FY{fiscal_year}_", 1)
        for key, name in template.items()
    }
    try:
        resp = requests.get(FY_PAGE_URL.format(fy=fiscal_year), timeout=60)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    links = re.findall(r"attachments/(\d+)/([^\"'?#]+\.xlsx)", resp.text)
    for attachment_id in {aid for aid, _ in links}:
        names = {name for aid, name in links if aid == attachment_id}
        if all(name in names for name in expected.values()):
            return {"attachment_id": attachment_id, "files": expected}
    return None


def ensure_registry_entry(fiscal_year: int) -> bool:
    """Make sure file_registry.json has fiscal_year, discovering it if needed."""
    if str(fiscal_year) in load_registry():
        return True
    entry = discover_registry_entry(fiscal_year)
    if entry is None:
        print(f"  FY{fiscal_year} SF-133 files not yet posted on OMB MAX.")
        return False
    registry = load_registry()
    registry[str(fiscal_year)] = entry
    registry = dict(sorted(registry.items()))
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")
    print(f"  Added FY{fiscal_year} to file_registry.json (attachment {entry['attachment_id']}).")
    return True


def check_for_new_data() -> dict:
    """Check whether new SF-133 monthly data is available.

    Returns a dict with keys:
        - site_period: current latest period label in site_data.json
        - site_fy_month: FY month number of site data
        - expected_fy_month: latest month that could be available given today's date
        - check_needed: whether a download check is warranted
        - file_fy_month: latest month found in downloaded file (if checked)
        - file_period_label: label for file_fy_month
        - new_data: True if the downloaded file has newer data than the site
    """
    from config import CURRENT_FY, FY_MONTH_LABELS, TODAY, fiscal_year_of

    result = {
        "site_period": None,
        "site_fy": None,
        "site_fy_month": None,
        "expected_fy_month": None,
        "check_needed": False,
        "file_fy": None,
        "file_fy_month": None,
        "file_period_label": None,
        "new_data": False,
    }

    # Step 1: What does the site currently have? (obligations FY + period)
    site_label, site_fy = _get_site_latest_period()
    if site_label:
        result["site_period"] = site_label
        result["site_fy_month"] = _label_to_fy_month(site_label)
    result["site_fy"] = site_fy
    site_key = (site_fy or 0, result["site_fy_month"] or 0)

    # Step 2: Latest (FY, month) that could be published (1-month reporting lag)
    today = TODAY
    prev_cal_month = today.month - 1 if today.month > 1 else 12
    prev_cal_year = today.year if today.month > 1 else today.year - 1
    expected_fy = fiscal_year_of(date(prev_cal_year, prev_cal_month, 1))
    expected = _calendar_to_fy_month(prev_cal_month, prev_cal_year, expected_fy)
    result["expected_fy_month"] = expected

    # Step 3: Do we need to check?
    if site_key >= (expected_fy, expected):
        result["check_needed"] = False
        return result
    result["check_needed"] = True

    # Step 4: FYs that could have new data: the site's FY until its final
    # (September) report, plus any newer FY through the current one.
    candidates = []
    if site_fy is None:
        candidates = [CURRENT_FY]
    else:
        if (result["site_fy_month"] or 0) < 12:
            candidates.append(site_fy)
        candidates += list(range(site_fy + 1, CURRENT_FY + 1))

    # Step 5: Download each candidate FY and find its latest populated month
    # (use HHS/NIH — largest, most reliable)
    for fy in candidates:
        if not ensure_registry_entry(fy):
            continue
        print(f"Downloading FY{fy} files to check for new data...")
        download_all(fiscal_years=[fy], force=True)
        hhs_path = get_local_path(fy, "hhs")
        file_month = _detect_latest_month_in_file(hhs_path) if hhs_path else None
        if file_month and (fy, file_month) > (result["file_fy"] or 0, result["file_fy_month"] or 0):
            result["file_fy"] = fy
            result["file_fy_month"] = file_month
            result["file_period_label"] = FY_MONTH_LABELS.get(file_month)

    if result["file_fy_month"]:
        result["new_data"] = (result["file_fy"], result["file_fy_month"]) > site_key

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download SF-133 data files")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    parser.add_argument("--years", nargs="*", type=int, help="Specific fiscal years")
    parser.add_argument("--agencies", nargs="*", help="Specific file keys (hhs, nsf, etc.)")
    parser.add_argument("--list", action="store_true", help="List available files")
    parser.add_argument("--check", action="store_true", help="Check for new monthly data")
    args = parser.parse_args()

    if args.list:
        for fy, key, cached in list_available():
            status = "cached" if cached else "missing"
            print(f"  FY{fy}/{key}: {status}")
    elif args.check:
        result = check_for_new_data()
        site = result["site_period"] or "unknown"
        print(f"\nSF-133 status:")
        print(f"  Site currently shows: FY{result['site_fy']} {site} (FY month {result['site_fy_month']})")
        if not result["check_needed"]:
            print(f"  No check needed — site data is current for this point in the FY.")
        else:
            if result["file_fy_month"]:
                print(f"  Downloaded files have data through: FY{result['file_fy']} {result['file_period_label']} (FY month {result['file_fy_month']})")
                if result["new_data"]:
                    print(f"  NEW DATA AVAILABLE. Run: python3 data/preprocess.py && python3 build.py")
                else:
                    print(f"  No new data beyond what the site already shows.")
            else:
                print(f"  Could not determine latest month from downloaded file.")
    else:
        print("Downloading SF-133 files...")
        results = download_all(
            fiscal_years=args.years,
            file_keys=args.agencies,
            force=args.force,
        )
        print(f"\nDone. {len(results)} files ready.")
