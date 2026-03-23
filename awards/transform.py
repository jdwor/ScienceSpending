"""
Transform raw award data into cumulative time series for charting.

Produces:
  - award_series: cumulative award counts and dollars over time
  - award_summary: YoY comparison metrics at the latest available date
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

import numpy as np
import pandas as pd

from config import AWARDS_CONFIG, BAND_YEARS_EXCLUDE, CURRENT_FY


def _fy_day(d: date, fiscal_year: int) -> int:
    """Convert a calendar date to day-of-fiscal-year (Oct 1 = day 1)."""
    fy_start = date(fiscal_year - 1, 10, 1)
    return (d - fy_start).days + 1


def _fy_month_last_day(fy_month: int, fiscal_year: int) -> int:
    """Return the fy_day corresponding to the last day of a fiscal-year month."""
    # fy_month 1 = Oct, 2 = Nov, ... 12 = Sep
    cal_month = (fy_month + 8) % 12 + 1  # back to calendar month
    cal_year = fiscal_year - 1 if cal_month >= 10 else fiscal_year
    last_day = calendar.monthrange(cal_year, cal_month)[1]
    d = date(cal_year, cal_month, last_day)
    return _fy_day(d, fiscal_year)


def _build_daily_cumulative(df: pd.DataFrame, agency_key: str) -> pd.DataFrame:
    """Build daily cumulative series for NIH or NSF data."""
    source = AWARDS_CONFIG[agency_key]["source"]
    records = []

    for fy, fy_group in df.groupby("fiscal_year"):
        fy_group = fy_group.copy()
        fy_group["_date"] = pd.to_datetime(fy_group["date"]).dt.date
        fy_group = fy_group.dropna(subset=["_date"])
        fy_group = fy_group[
            (fy_group["_date"] >= date(int(fy) - 1, 10, 1))
            & (fy_group["_date"] <= date(int(fy), 9, 30))
        ]

        if fy_group.empty:
            continue

        # Daily aggregation
        daily = (
            fy_group.groupby("_date")
            .agg(count=("_date", "size"), dollars=("award_amount", "sum"))
            .sort_index()
        )
        daily["cumulative_count"] = daily["count"].cumsum()
        daily["cumulative_dollars"] = daily["dollars"].cumsum()

        for d, row in daily.iterrows():
            records.append({
                "agency": agency_key,
                "fiscal_year": int(fy),
                "date": d.isoformat(),
                "fy_day": _fy_day(d, int(fy)),
                "cumulative_count": int(row["cumulative_count"]),
                "cumulative_dollars": float(row["cumulative_dollars"]),
                "source_type": source,
                "is_provisional": False,
            })

    return pd.DataFrame(records)


def _fy_month_to_next_boundary(fy_month: int, fiscal_year: int) -> date:
    """Convert a fiscal-year month to the first day of the NEXT calendar month.

    This places "cumulative through end of October" at the Nov 1 boundary,
    matching how obligations data sits on month boundaries.
    """
    next_month = (fy_month % 12) + 1  # next fiscal month (1-12)
    cal_month = (next_month + 8) % 12 + 1
    cal_year = fiscal_year - 1 if cal_month >= 10 else fiscal_year
    # For fy_month 12 (Sep), next month is Oct of the following FY
    if fy_month == 12:
        cal_year = fiscal_year
    return date(cal_year, cal_month, 1)


def _build_monthly_cumulative(
    df: pd.DataFrame, agency_key: str,
    freshness_date: str | None = None,
) -> pd.DataFrame:
    """Build monthly cumulative series for USASpending data.

    If *freshness_date* is provided (ISO date string, e.g. '2026-03-20'),
    it represents the max last_modified_date from the per-award API.
    A fiscal month M is considered complete if *freshness_date* falls in
    calendar month M+1 or later.  The latest incomplete month is placed
    at *freshness_date* rather than the next-month boundary.  If freshness
    data is unavailable (None), the latest active month is dropped entirely
    for the current FY to avoid showing potentially incomplete data.
    """
    source = AWARDS_CONFIG[agency_key]["source"]
    records = []

    # Parse freshness date once
    fresh_date = None
    if freshness_date:
        try:
            fresh_date = date.fromisoformat(freshness_date)
        except ValueError:
            fresh_date = None

    for fy, fy_group in df.groupby("fiscal_year"):
        fy_int = int(fy)
        fy_group = fy_group.sort_values("fy_month")

        # Find last month with non-zero obligation to trim trailing zeros
        nonzero = fy_group[fy_group["obligation_amount"] != 0]
        last_active_month = int(nonzero["fy_month"].max()) if not nonzero.empty else 0
        fy_group = fy_group[fy_group["fy_month"] <= last_active_month]

        if fy_group.empty:
            continue

        # Determine which months are complete for current FY
        is_current_fy = (fy_int == CURRENT_FY)
        last_complete_fy_month = None  # None means "all complete" (past FYs)

        if is_current_fy:
            if fresh_date is None:
                # No freshness data — be conservative: drop the last active month
                last_complete_fy_month = last_active_month - 1
            else:
                # A month M is complete if fresh_date is in calendar month M+1.
                # fresh_date's calendar month → the FY month that is "completed"
                fresh_cal_month = fresh_date.month
                # The completed month is the one *before* the month containing fresh_date.
                # Convert fresh_date's calendar month to FY month:
                fresh_fy_month = (fresh_cal_month - 10) % 12 + 1
                # All FY months before fresh_fy_month are complete
                last_complete_fy_month = fresh_fy_month - 1

        cumulative = 0.0

        for _, row in fy_group.iterrows():
            fy_month = int(row["fy_month"])
            cumulative += float(row["obligation_amount"])

            if is_current_fy and last_complete_fy_month is not None:
                if fy_month > last_complete_fy_month + 1:
                    # Beyond the provisional month — don't include
                    break
                elif fy_month == last_complete_fy_month + 1:
                    # This is the provisional month — place at freshness date
                    if fresh_date is None:
                        # No freshness data — skip this month entirely
                        break
                    d = fresh_date
                    is_provisional = True
                else:
                    # Complete month — place at next-month boundary
                    d = _fy_month_to_next_boundary(fy_month, fy_int)
                    is_provisional = False
            else:
                # Past FY or all months complete
                d = _fy_month_to_next_boundary(fy_month, fy_int)
                is_provisional = False

            records.append({
                "agency": agency_key,
                "fiscal_year": fy_int,
                "date": d.isoformat(),
                "fy_day": _fy_day(d, fy_int),
                "cumulative_count": 0,  # Not meaningful for USASpending
                "cumulative_dollars": cumulative,
                "source_type": source,
                "is_provisional": is_provisional,
            })

    return pd.DataFrame(records)


def build_award_series(
    raw_data: dict[str, pd.DataFrame],
    freshness_data: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Build cumulative award time series for all agencies.

    *freshness_data* maps USASpending agency keys to their max
    last_modified_date (ISO string), used to determine which months
    are complete vs provisional.

    Returns DataFrame with columns:
        agency, fiscal_year, date, fy_day, cumulative_count,
        cumulative_dollars, source_type, is_provisional
    """
    freshness_data = freshness_data or {}
    frames = []

    for agency_key, df in raw_data.items():
        if df.empty:
            continue
        source = AWARDS_CONFIG[agency_key]["source"]
        if source in ("nih_reporter", "nsf_awards"):
            frames.append(_build_daily_cumulative(df, agency_key))
        elif source == "usaspending":
            frames.append(_build_monthly_cumulative(
                df, agency_key,
                freshness_date=freshness_data.get(agency_key),
            ))

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_award_summary(
    series: pd.DataFrame,
    current_fy: int = CURRENT_FY,
) -> pd.DataFrame:
    """
    Compute YoY comparison metrics at the latest available date in the
    current FY for each agency.
    """
    records = []

    for agency_key in series["agency"].unique():
        agency_data = series[series["agency"] == agency_key]
        current = agency_data[agency_data["fiscal_year"] == current_fy]
        if current.empty:
            continue

        latest = current.loc[current["fy_day"].idxmax()]
        latest_day = int(latest["fy_day"])
        latest_date = latest["date"]

        # Prior year at same day (interpolate for leap-year day offsets)
        prior = agency_data[agency_data["fiscal_year"] == current_fy - 1].sort_values("fy_day")
        prior_count = 0
        prior_dollars = 0.0
        if not prior.empty and latest_day >= prior["fy_day"].iloc[0]:
            prior_dollars = float(np.interp(latest_day, prior["fy_day"].values, prior["cumulative_dollars"].values))
            prior_count = int(np.interp(latest_day, prior["fy_day"].values, prior["cumulative_count"].values))

        # Mean of all prior years (excluding BAND_YEARS_EXCLUDE) at same day
        band_years = agency_data[
            (~agency_data["fiscal_year"].isin(BAND_YEARS_EXCLUDE))
            & (agency_data["fiscal_year"] < current_fy)
        ]
        mean_counts = []
        mean_dollars_list = []
        for fy, fy_data in band_years.groupby("fiscal_year"):
            fy_data = fy_data.sort_values("fy_day")
            if fy_data.empty or latest_day < fy_data["fy_day"].iloc[0]:
                continue
            mean_dollars_list.append(float(np.interp(latest_day, fy_data["fy_day"].values, fy_data["cumulative_dollars"].values)))
            mean_counts.append(int(np.interp(latest_day, fy_data["fy_day"].values, fy_data["cumulative_count"].values)))

        mean_count = float(np.mean(mean_counts)) if mean_counts else 0.0
        mean_dollars = float(np.mean(mean_dollars_list)) if mean_dollars_list else 0.0

        records.append({
            "agency": agency_key,
            "source_type": AWARDS_CONFIG[agency_key]["source"],
            "latest_fy_day": latest_day,
            "latest_date": latest_date,
            "cumul_count": int(latest["cumulative_count"]),
            "cumul_dollars": float(latest["cumulative_dollars"]),
            "prior_year_count": prior_count,
            "prior_year_dollars": prior_dollars,
            "mean_count": mean_count,
            "mean_dollars": mean_dollars,
        })

    return pd.DataFrame(records)
