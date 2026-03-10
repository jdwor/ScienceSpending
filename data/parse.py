"""
Parse SF-133 Excel files and extract relevant rows for tracked agencies.

Each file's "Raw Data" sheet contains one row per TAFS × line item,
with cumulative amounts for each reporting period.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from config import AGENCIES, AMOUNT_COLUMNS, TARGET_LINES

# Column indices in the Raw Data sheet (0-based)
COL_MAP = {
    "RPT_YR": 0,
    "BUREAU": 2,
    "TRACCT": 6,
    "STAT": 9,
    "LINENO": 12,
    "LINE_DESC": 13,
    "TAFS": 16,
    "LINE_TYPE": 21,
}

# Build column name -> index map from the known header structure
RAW_DATA_COLUMNS = [
    "RPT_YR", "AGENCY", "BUREAU", "OMB_ACCT", "TRAG", "ALLOC", "TRACCT",
    "FY1", "FY2", "STAT", "CRED_IND", "COHORT", "LINENO", "LINE_DESC",
    "CAT_B", "F2_USER_ID", "TAFS", "AGENCY_TITLE", "LAST_UPDATED",
    "SECTION", "SECTION_NO", "LINE_TYPE", "TAFS_ACCT", "BUREAU_TITLE",
    "OMB_ACCOUNT", "FIN_ACCTS", "F2_USER",
    "AMT_NOV", "AMT_JAN", "AMT_FEB", "AMT_APR", "AMT_MAY",
    "AMT_JUL", "AMT_AUG", "AGEUP", "AMT_OCT",
    "AMT1", "AMT2", "AMT3", "AMT4",
    "LINE_DESC_SHORT", "PGM_CAT", "PGM_CAT_STUB", "CAT_B_STUB",
]

# Amount column names in the raw data
AMOUNT_COL_NAMES = [col for col, _, _ in AMOUNT_COLUMNS]


def _matches_agency_filter(row: dict, agency_cfg: dict) -> bool:
    """Check if a raw data row matches the agency's filter criteria."""
    filter_type = agency_cfg["filter_type"]
    filter_value = agency_cfg["filter_value"]

    if filter_type == "all":
        return True
    elif filter_type == "bureau":
        bureau = str(row.get("BUREAU", "")).strip()
        if isinstance(filter_value, list):
            return bureau in filter_value
        return bureau == filter_value
    elif filter_type == "tracct":
        tracct = str(row.get("TRACCT", "")).strip().lstrip("0")
        if isinstance(filter_value, list):
            return tracct in [str(v).strip().lstrip("0") for v in filter_value]
        target = str(filter_value).strip().lstrip("0")
        return tracct == target
    elif filter_type == "bureau_exclude":
        bureau = str(row.get("BUREAU", "")).strip()
        if isinstance(filter_value, list):
            if bureau not in filter_value:
                return False
        elif bureau != filter_value:
            return False
        # Check exclusion list
        exclude = agency_cfg.get("exclude_tracct", [])
        if exclude:
            tracct = str(row.get("TRACCT", "")).strip().lstrip("0")
            if tracct in [str(v).strip().lstrip("0") for v in exclude]:
                return False
        return True
    return False


def parse_file(filepath: Path, agency_key: str) -> pd.DataFrame | None:
    """
    Parse a single SF-133 Excel file for a specific agency.

    Returns a DataFrame with columns:
        fiscal_year, agency, line_item, line_desc, period_month, amount
    One row per (line_item, period_month) after summing across all matching TAFS.
    """
    agency_cfg = AGENCIES[agency_key]

    if not filepath.exists():
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            # Try reading with pandas for speed; fall back to openpyxl if needed
            df_raw = pd.read_excel(
                filepath,
                sheet_name="Raw Data",
                engine="openpyxl",
            )
        except Exception as e:
            print(f"  Warning: could not read {filepath.name}: {e}")
            return None

    if df_raw.empty:
        return None

    # Normalize column names (strip whitespace)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    # Filter to unexpired accounts
    if "STAT" in df_raw.columns:
        df_raw = df_raw[df_raw["STAT"].astype(str).str.strip() == "U"]

    # Apply agency-specific filter
    mask = df_raw.apply(
        lambda row: _matches_agency_filter(row.to_dict(), agency_cfg), axis=1
    )
    df_filtered = df_raw[mask].copy()

    if df_filtered.empty:
        return None

    # Filter to target line items
    df_filtered["LINENO_CLEAN"] = df_filtered["LINENO"].astype(str).str.strip()
    df_filtered = df_filtered[df_filtered["LINENO_CLEAN"].isin(TARGET_LINES)]

    if df_filtered.empty:
        return None

    # Extract fiscal year from the data
    fiscal_year = int(df_filtered["RPT_YR"].iloc[0])

    # FY2016 (and earlier) amounts are in thousands of dollars; FY2017+ are in dollars.
    amt_multiplier = 1000 if fiscal_year <= 2016 else 1

    # For each line item, sum amounts across all matching TAFS and cohorts
    records = []
    for line_no, group in df_filtered.groupby("LINENO_CLEAN"):
        line_desc = group["LINE_DESC"].iloc[0]
        if isinstance(line_desc, str):
            line_desc = line_desc.strip()

        # Check which line type (D=detail, S=subtotal/summary)
        # For subtotal lines, they may already be aggregated — use them directly
        # For detail lines, we need to sum
        line_types = group["LINE_TYPE"].astype(str).str.strip().unique()

        # Prefer summary lines (S) if available, otherwise sum detail lines (D)
        if "S" in line_types and len(group[group["LINE_TYPE"].astype(str).str.strip() == "S"]) > 0:
            sum_group = group[group["LINE_TYPE"].astype(str).str.strip() == "S"]
        else:
            sum_group = group

        # Deduplicate rows that differ only by CAT_B (FY2017 has duplicate S-rows
        # with CAT_B='011' and CAT_B='' carrying identical amounts)
        if "CAT_B" in sum_group.columns:
            dedup_cols = ["TAFS", "LINENO_CLEAN"]
            dedup_cols = [c for c in dedup_cols if c in sum_group.columns]
            if dedup_cols:
                sum_group = sum_group.drop_duplicates(subset=dedup_cols, keep="first")

        for col_name, display_label, fy_month in AMOUNT_COLUMNS:
            if col_name in sum_group.columns:
                amount = pd.to_numeric(sum_group[col_name], errors="coerce").sum()
                amount *= amt_multiplier
                if pd.notna(amount) and amount != 0:
                    records.append({
                        "fiscal_year": fiscal_year,
                        "agency": agency_key,
                        "line_item": line_no,
                        "line_desc": line_desc,
                        "period_month": fy_month,
                        "period_label": display_label,
                        "amount": amount,
                    })

    if not records:
        return None

    return pd.DataFrame(records)


def parse_all_files(
    fiscal_years: list[int] | None = None,
    agency_keys: list[str] | None = None,
) -> pd.DataFrame:
    """
    Parse all cached SF-133 files and return a combined DataFrame.

    Returns DataFrame with columns:
        fiscal_year, agency, line_item, line_desc, period_month, period_label, amount
    """
    from data.download import get_local_path

    if agency_keys is None:
        agency_keys = list(AGENCIES.keys())

    all_frames = []

    for agency_key in agency_keys:
        file_key = AGENCIES[agency_key]["sf133_file_key"]
        years = fiscal_years if fiscal_years else list(range(2016, 2027))

        for fy in years:
            path = get_local_path(fy, file_key)
            if path is None:
                continue

            print(f"  Parsing FY{fy} / {agency_key}...")
            df = parse_file(path, agency_key)
            if df is not None and not df.empty:
                all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    return pd.concat(all_frames, ignore_index=True)
