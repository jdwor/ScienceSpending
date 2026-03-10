"""
Transform parsed SF-133 data into analysis-ready structures.

Produces obligation time series, appropriation summaries, and
year-over-year comparison metrics for each tracked agency.
"""
from __future__ import annotations

import pandas as pd

from config import AGENCIES, LINE_ITEMS, FY_MONTH_LABELS


def build_obligation_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build cumulative obligation time series for each (agency, fiscal_year).

    Input: raw parsed DataFrame from parse.parse_all_files()
    Output: DataFrame with columns:
        agency, fiscal_year, period_month, period_label,
        obligations, appropriations, pct_obligated
    """
    # Use line 2190 (total obligations) — it has one clean row per TAFS across
    # all fiscal years, avoiding the CAT_B duplicate issues that plague line 2170.
    line_oblig = LINE_ITEMS["obligations_total"]           # 2190
    # Use raw appropriation lines (1100/1200) rather than net totals (1160/1260).
    # Line 1160 includes CR preclusions (line 1134) which drastically understate
    # the full-year appropriation during a continuing resolution. Line 1100 gives
    # the annualized rate, which equals the enacted level once a full-year bill passes.
    line_approp_disc_raw = LINE_ITEMS["approp_disc_raw"]
    line_approp_mand_raw = LINE_ITEMS.get("approp_mand_raw", "1200")

    results = []

    for (agency, fy), group in df.groupby(["agency", "fiscal_year"]):
        oblig = group[group["line_item"] == line_oblig].copy()
        if oblig.empty:
            continue

        # Get total appropriations using RAW lines (before CR preclusion).
        # Use latest period value — for completed FYs this is year-end enacted;
        # for current FY during CR this is the annualized rate.
        approp_disc = group[group["line_item"] == line_approp_disc_raw]
        approp_mand = group[group["line_item"] == line_approp_mand_raw]

        disc_total = 0
        if not approp_disc.empty:
            disc_total = approp_disc.loc[approp_disc["period_month"].idxmax(), "amount"]

        mand_total = 0
        if not approp_mand.empty:
            mand_total = approp_mand.loc[approp_mand["period_month"].idxmax(), "amount"]

        total_approp = disc_total + mand_total

        for _, row in oblig.iterrows():
            pct = (row["amount"] / total_approp * 100) if total_approp else None
            results.append({
                "agency": agency,
                "display_name": AGENCIES[agency]["display_name"],
                "fiscal_year": fy,
                "period_month": row["period_month"],
                "period_label": row["period_label"],
                "obligations": row["amount"],
                "appropriations": total_approp,
                "pct_obligated": pct,
            })

    return pd.DataFrame(results)


def build_appropriations_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a summary table of appropriations and budget authority by agency and FY.

    Uses the end-of-year (or latest available) values for each metric.
    """
    summary_lines = {
        "approp_disc_raw": LINE_ITEMS["approp_disc_raw"],
        "approp_mand_raw": LINE_ITEMS["approp_mand_raw"],
        "approp_disc_net": LINE_ITEMS["approp_disc"],
        "approp_mand_net": LINE_ITEMS["approp_mand"],
        "budget_authority": LINE_ITEMS["budget_authority"],
        "total_resources": LINE_ITEMS["total_budgetary_resources"],
        "obligations_total": LINE_ITEMS["obligations_total"],
        "outlays_net": LINE_ITEMS["outlays_net"],
        "approp_precluded": LINE_ITEMS["approp_precluded"],
    }

    records = []
    for (agency, fy), group in df.groupby(["agency", "fiscal_year"]):
        row = {"agency": agency, "fiscal_year": fy}
        for metric_name, line_no in summary_lines.items():
            line_data = group[group["line_item"] == line_no]
            if not line_data.empty:
                # Use the latest period available
                row[metric_name] = line_data.loc[
                    line_data["period_month"].idxmax(), "amount"
                ]
            else:
                row[metric_name] = None
        records.append(row)

    return pd.DataFrame(records)


def compute_yoy_comparison(
    obligation_series: pd.DataFrame,
    current_fy: int = 2026,
) -> pd.DataFrame:
    """
    For each agency, compute year-over-year metrics at each available period
    in the current FY.

    Returns DataFrame with columns:
        agency, period_month, current_obligations, prior_year_obligations,
        yoy_change, yoy_pct_change, median_prior_obligations
    """
    records = []

    for agency in obligation_series["agency"].unique():
        agency_data = obligation_series[obligation_series["agency"] == agency]
        current = agency_data[agency_data["fiscal_year"] == current_fy]
        prior = agency_data[agency_data["fiscal_year"] < current_fy]

        if current.empty:
            continue

        for _, row in current.iterrows():
            month = row["period_month"]
            curr_pct = row["pct_obligated"]

            # Prior year spend-down rate at same month
            prior_same = prior[
                (prior["fiscal_year"] == current_fy - 1)
                & (prior["period_month"] == month)
            ]
            prior_pct = prior_same["pct_obligated"].iloc[0] if not prior_same.empty else None

            # Mean spend-down rate across all prior years at same month
            prior_all = prior[prior["period_month"] == month]["pct_obligated"]
            median_pct = prior_all.mean() if not prior_all.empty else None

            yoy_diff = (curr_pct - prior_pct) if prior_pct is not None else None

            records.append({
                "agency": agency,
                "display_name": AGENCIES[agency]["display_name"],
                "period_month": month,
                "period_label": FY_MONTH_LABELS.get(month, ""),
                "current_pct": curr_pct,
                "prior_year_pct": prior_pct,
                "yoy_diff": yoy_diff,
                "median_prior_pct": median_pct,
            })

    return pd.DataFrame(records)


def get_latest_period(obligation_series: pd.DataFrame, fiscal_year: int) -> int | None:
    """Get the most recent reporting period month for a given FY."""
    fy_data = obligation_series[obligation_series["fiscal_year"] == fiscal_year]
    if fy_data.empty:
        return None
    return int(fy_data["period_month"].max())
