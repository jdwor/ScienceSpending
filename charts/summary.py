"""
Summary metrics and cards for the Streamlit dashboard.
"""
from __future__ import annotations

import pandas as pd

from config import AGENCIES, BAND_YEARS_EXCLUDE, CURRENT_FY, FY_MONTH_LABELS
from data.transform import get_latest_period


def compute_agency_summary(
    obligation_series: pd.DataFrame,
    approp_summary: pd.DataFrame,
    agency_key: str,
    current_fy: int = CURRENT_FY,
) -> dict:
    """
    Compute summary metrics for one agency in the current FY.

    Returns a dict with:
        - appropriations: total appropriation level
        - obligations_to_date: latest cumulative obligations
        - pct_obligated: % of appropriations obligated
        - latest_period: most recent reporting period label
        - prior_year_obligations: obligations at same period last year
        - yoy_change: dollar difference from prior year
        - yoy_pct_change: percentage difference from prior year
        - mean_prior: mean of all prior years at same period
    """
    cfg = AGENCIES[agency_key]
    agency_data = obligation_series[obligation_series["agency"] == agency_key]

    latest_month = get_latest_period(obligation_series, current_fy)
    if latest_month is None:
        return {"error": "No current FY data available"}

    # Current FY values at latest period
    current = agency_data[
        (agency_data["fiscal_year"] == current_fy)
        & (agency_data["period_month"] == latest_month)
    ]

    if current.empty:
        return {"error": "No current FY data at latest period"}

    current_row = current.iloc[0]
    obligations_to_date = current_row["obligations"]
    appropriations = current_row["appropriations"]
    pct = current_row["pct_obligated"]

    # Prior year spend-down rate at same period
    prior = agency_data[
        (agency_data["fiscal_year"] == current_fy - 1)
        & (agency_data["period_month"] == latest_month)
    ]
    prior_pct = prior["pct_obligated"].iloc[0] if not prior.empty else None

    # Mean spend-down rate across band-eligible prior years at same period
    # (must match the envelope computation, which excludes BAND_YEARS_EXCLUDE)
    all_prior = agency_data[
        (~agency_data["fiscal_year"].isin(BAND_YEARS_EXCLUDE))
        & (agency_data["fiscal_year"] < current_fy)
        & (agency_data["period_month"] == latest_month)
    ]["pct_obligated"]
    mean_pct = all_prior.mean() if not all_prior.empty else None

    yoy_diff = (pct - prior_pct) if prior_pct is not None else None
    yoy_rel = (yoy_diff / prior_pct * 100) if prior_pct else None
    mean_diff = (pct - mean_pct) if (pct is not None and mean_pct is not None) else None
    mean_rel = (mean_diff / mean_pct * 100) if mean_pct else None

    return {
        "agency": agency_key,
        "display_name": cfg["display_name"],
        "appropriations": appropriations,
        "obligations_to_date": obligations_to_date,
        "pct_obligated": pct,
        "latest_period": FY_MONTH_LABELS.get(latest_month, f"Month {latest_month}"),
        "prior_year_pct": prior_pct,
        "yoy_diff": yoy_diff,
        "yoy_rel": yoy_rel,
        "mean_prior_pct": mean_pct,
        "mean_diff": mean_diff,
        "mean_rel": mean_rel,
    }


def format_dollars(amount: float | None) -> str:
    """Format a dollar amount for display."""
    if amount is None:
        return "N/A"
    if abs(amount) >= 1e9:
        return f"${amount / 1e9:,.2f}B"
    elif abs(amount) >= 1e6:
        return f"${amount / 1e6:,.1f}M"
    else:
        return f"${amount:,.0f}"


def format_pct(value: float | None) -> str:
    """Format a percentage for display."""
    if value is None:
        return "N/A"
    return f"{value:+.1f}%"
