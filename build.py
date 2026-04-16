"""
Build script: converts preprocessed CSVs into JSON for the static site.

Usage:
    python3 build.py
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    AGENCIES, AWARDS_CONFIG, CURRENT_FY, HIGHLIGHT_YEARS,
    BAND_YEARS_EXCLUDE, FY_MONTH_LABELS,
)

PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"
AWARDS_PROCESSED_DIR = Path(__file__).resolve().parent / "awards" / "processed"
SITE_DATA_DIR = Path(__file__).resolve().parent / "docs" / "data"


def load_csvs():
    obligation_series = pd.read_csv(PROCESSED_DIR / "obligation_series.csv")
    approp_summary = pd.read_csv(PROCESSED_DIR / "approp_summary.csv")
    yoy_comparison = pd.read_csv(PROCESSED_DIR / "yoy_comparison.csv")
    return obligation_series, approp_summary, yoy_comparison


def build_agency_configs():
    """Export agency config for the frontend.

    Includes SF-133 agencies from AGENCIES, plus awards-only sub-agencies
    from AWARDS_CONFIG that have a parent field but aren't in AGENCIES.
    """
    configs = {
        key: {
            "display_name": cfg["display_name"],
            "color": cfg["color"],
            **({"parent": cfg["parent"]} if "parent" in cfg else {}),
        }
        for key, cfg in AGENCIES.items()
    }
    # Add awards-only sub-agencies (e.g., NSF directorates)
    for key, cfg in AWARDS_CONFIG.items():
        if key not in configs and "parent" in cfg:
            parent_cfg = AGENCIES.get(cfg["parent"], {})
            configs[key] = {
                "display_name": cfg.get("display_name", key),
                "color": parent_cfg.get("color", "#666"),
                "parent": cfg["parent"],
            }
    return configs


def compute_prior_year_envelope(agency_data, fiscal_years, show_pct=True):
    """Compute min/max/mean band from band-eligible fiscal years."""
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    if not band_fys:
        return None

    y_col = "pct_obligated" if show_pct else "obligations"
    all_months = list(range(1, 13))
    min_vals, max_vals, med_vals = [], [], []

    for m in all_months:
        vals = []
        for fy in band_fys:
            if m == 1:
                vals.append(0.0)
                continue
            fy_data = agency_data[
                (agency_data["fiscal_year"] == fy) & (agency_data["period_month"] == m)
            ]
            if not fy_data.empty:
                v = fy_data[y_col].iloc[0]
                if not show_pct:
                    v = v / 1e9
                vals.append(v)
        if vals:
            min_vals.append(round(min(vals), 3))
            max_vals.append(round(max(vals), 3))
            med_vals.append(round(float(np.mean(vals)), 3))
        else:
            min_vals.append(None)
            max_vals.append(None)
            med_vals.append(None)

    return {
        "months": all_months,
        "min": min_vals,
        "max": max_vals,
        "mean": med_vals,
        "band_fys": band_fys,
    }


def compute_mean_lookup(agency_data, fiscal_years, show_pct=True):
    """Build {month: mean_value} from band-eligible years."""
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    means = {}
    y_col = "pct_obligated" if show_pct else "obligations"
    for m in range(1, 13):
        vals = []
        for fy in band_fys:
            if m == 1:
                vals.append(0.0)
                continue
            fy_data = agency_data[
                (agency_data["fiscal_year"] == fy) & (agency_data["period_month"] == m)
            ]
            if not fy_data.empty:
                v = fy_data[y_col].iloc[0]
                if not show_pct:
                    v = v / 1e9
                vals.append(v)
        if vals:
            means[str(m)] = round(float(np.mean(vals)), 3)
    return means


def build_spenddown_data(obligation_series):
    """Build per-agency spend-down chart data (for both pct and dollar views)."""
    agencies_data = {}

    for agency_key in AGENCIES:
        agency_data = obligation_series[obligation_series["agency"] == agency_key].copy()
        if agency_data.empty:
            continue

        fiscal_years = sorted(agency_data["fiscal_year"].unique())

        # Envelopes for pct and dollar modes
        envelope_pct = compute_prior_year_envelope(agency_data, fiscal_years, show_pct=True)
        envelope_dollar = compute_prior_year_envelope(agency_data, fiscal_years, show_pct=False)

        # Individual year traces
        year_traces = {}
        for fy in fiscal_years:
            fy_data = agency_data[agency_data["fiscal_year"] == fy].sort_values("period_month")
            if fy_data.empty:
                continue

            months = fy_data["period_month"].tolist()
            pct_vals = fy_data["pct_obligated"].tolist()
            dollar_vals = [round(v / 1e9, 4) for v in fy_data["obligations"].tolist()]

            # Prepend Oct=0 if not present
            if not months or months[0] != 1:
                months = [1] + months
                pct_vals = [0.0] + pct_vals
                dollar_vals = [0.0] + dollar_vals

            # Round pct vals
            pct_vals = [round(v, 3) if v is not None else None for v in pct_vals]

            # Include the appropriation for this FY (same for all months)
            approp_val = fy_data["appropriations"].iloc[0] if not fy_data.empty else None

            year_traces[str(fy)] = {
                "months": months,
                "pct": pct_vals,
                "dollars_b": dollar_vals,
                "appropriation": round(approp_val / 1e9, 4) if approp_val else None,
            }

        agencies_data[agency_key] = {
            "fiscal_years": fiscal_years,
            "envelope_pct": envelope_pct,
            "envelope_dollar": envelope_dollar,
            "years": year_traces,
        }

    return agencies_data


def build_multi_agency_data(obligation_series):
    """Build data for the multi-agency comparison chart."""
    traces = {}

    for agency_key in AGENCIES:
        if "parent" in AGENCIES[agency_key]:
            continue  # Only parent agencies in multi-agency chart
        agency_all = obligation_series[obligation_series["agency"] == agency_key]
        all_fys = sorted(agency_all["fiscal_year"].unique())
        agency_fy = agency_all[agency_all["fiscal_year"] == CURRENT_FY].sort_values("period_month")
        if agency_fy.empty:
            continue

        means = compute_mean_lookup(agency_all, all_fys, show_pct=True)

        x_vals = []
        y_vals = []

        for _, row in agency_fy.iterrows():
            m = row["period_month"]
            avg = means.get(str(int(m)))
            curr_pct = row["pct_obligated"]
            if avg and avg > 0 and curr_pct is not None:
                pct_of_mean = curr_pct / avg * 100 - 100
            else:
                pct_of_mean = None
            if pct_of_mean is not None:
                x_vals.append(int(m))
                y_vals.append(round(pct_of_mean, 2))

        traces[agency_key] = {
            "months": x_vals,
            "pct_of_mean": y_vals,
        }

    return traces


def build_summary_data(obligation_series, approp_summary):
    """Build summary metric cards for each agency."""
    from charts.summary import compute_agency_summary, format_dollars

    summaries = {}
    for agency_key in AGENCIES:
        if agency_key not in obligation_series["agency"].unique():
            continue
        summary = compute_agency_summary(obligation_series, approp_summary, agency_key)
        # Make JSON-serializable
        for k, v in summary.items():
            if isinstance(v, (np.floating, np.integer)):
                summary[k] = round(float(v), 4)
            elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                summary[k] = None
        summaries[agency_key] = summary

    return summaries


def build_data_tables(approp_summary, yoy_comparison):
    """Build data for the tables tab."""
    # Appropriations summary
    approp_records = []
    if approp_summary is not None:
        for _, row in approp_summary.iterrows():
            record = {}
            for col in approp_summary.columns:
                v = row[col]
                if pd.isna(v):
                    record[col] = None
                elif isinstance(v, (np.floating, np.integer)):
                    record[col] = round(float(v), 2)
                else:
                    record[col] = v
            approp_records.append(record)

    # YoY comparison
    yoy_records = []
    if yoy_comparison is not None:
        for _, row in yoy_comparison.iterrows():
            record = {}
            for col in yoy_comparison.columns:
                v = row[col]
                if pd.isna(v):
                    record[col] = None
                elif isinstance(v, (np.floating, np.integer)):
                    record[col] = round(float(v), 2)
                else:
                    record[col] = v
            yoy_records.append(record)

    return {"approp_summary": approp_records, "yoy_comparison": yoy_records}


def _load_approp_lookup():
    """Build {agency: {fy: approp_dollars}} from SF-133 approp_summary.

    Sub-agencies without their own appropriation data fall back to their
    parent agency's appropriation as the denominator.
    """
    approp_path = PROCESSED_DIR / "approp_summary.csv"
    if not approp_path.exists():
        return {}
    approp = pd.read_csv(approp_path)
    lookup = {}
    for _, row in approp.iterrows():
        agency = row["agency"]
        fy = int(row["fiscal_year"])
        # Use discretionary appropriation (Line 1100) as denominator.
        # Mandatory (Line 1200) is excluded because competitive grants are
        # funded from discretionary accounts; mandatory supports earmarked programs.
        val = row.get("approp_disc_raw")
        if pd.notna(val) and val > 0:
            lookup.setdefault(agency, {})[fy] = float(val)
    # Fall back to parent appropriation for sub-agencies without their own
    for key, cfg in AGENCIES.items():
        if key not in lookup and "parent" in cfg and cfg["parent"] in lookup:
            lookup[key] = lookup[cfg["parent"]]
    for key, cfg in AWARDS_CONFIG.items():
        if key not in lookup and "parent" in cfg and cfg["parent"] in lookup:
            lookup[key] = lookup[cfg["parent"]]
    return lookup


def _detect_reliable_years(agency_series, fiscal_years, current_fy):
    """Auto-exclude years with implausibly low grant totals (bad USASpending data)."""
    fy_totals = {}
    for fy in fiscal_years:
        if fy == current_fy:
            continue
        fy_data = agency_series[agency_series["fiscal_year"] == fy]
        if not fy_data.empty:
            fy_totals[fy] = fy_data["cumulative_dollars"].max()

    if not fy_totals:
        return fiscal_years

    peak = max(fy_totals.values())
    if peak <= 0:
        return fiscal_years

    threshold = peak * 0.25
    return [
        fy for fy in fiscal_years
        if fy == current_fy
        or fy in HIGHLIGHT_YEARS
        or fy_totals.get(fy, 0) >= threshold
    ]


def build_awards_site_data(series_override=None, summary_override=None):
    """Build awards chart data from awards/processed/ CSVs if available."""
    series_path = series_override or (AWARDS_PROCESSED_DIR / "award_series.csv")
    summary_path = summary_override or (AWARDS_PROCESSED_DIR / "award_summary.csv")

    if not Path(series_path).exists():
        print("No awards data found — skipping awards build.")
        return {}, {}

    print(f"Loading awards CSVs from {Path(series_path).name}...")
    series = pd.read_csv(series_path)
    summary_df = pd.read_csv(summary_path) if Path(summary_path).exists() else pd.DataFrame()
    approp_lookup = _load_approp_lookup()

    awards_data = {}
    for agency_key in AWARDS_CONFIG:
        agency_series = series[series["agency"] == agency_key]
        if agency_series.empty:
            continue

        acfg = AWARDS_CONFIG[agency_key]
        fiscal_years = sorted(agency_series["fiscal_year"].unique())

        # Auto-exclude years with bad data
        reliable_years = _detect_reliable_years(agency_series, fiscal_years, CURRENT_FY)
        excluded_years = [fy for fy in fiscal_years if fy not in reliable_years]
        if excluded_years:
            print(f"  {agency_key}: excluding {excluded_years} (incomplete USASpending data)")

        band_fys = [fy for fy in reliable_years
                    if fy not in BAND_YEARS_EXCLUDE and fy != CURRENT_FY]

        # Get appropriation lookup for this agency
        agency_approp = approp_lookup.get(agency_key, {})

        # Build year traces — always anchor at fy_day=1 with value 0
        year_traces = {}
        for fy in reliable_years:
            fy_data = agency_series[agency_series["fiscal_year"] == fy].sort_values("fy_day")
            if fy_data.empty:
                continue

            fy_days = fy_data["fy_day"].tolist()
            dates = fy_data["date"].tolist()
            counts = fy_data["cumulative_count"].tolist()
            dollars_list = fy_data["cumulative_dollars"].tolist()

            # Prepend Oct 1 anchor if series doesn't start there
            prepended_anchor = fy_days[0] != 1
            if prepended_anchor:
                fy_start_date = f"{fy - 1}-10-01"
                fy_days = [1] + fy_days
                dates = [fy_start_date] + dates
                counts = [0] + counts
                dollars_list = [0.0] + dollars_list

            dollars_m = [round(v / 1e6, 2) for v in dollars_list]

            # Compute pct of appropriation if available
            approp_val = agency_approp.get(fy)
            if approp_val and approp_val > 0:
                pct_approp = [round(v / approp_val * 100, 3) for v in dollars_list]
            else:
                pct_approp = [None] * len(dollars_list)

            # Determine provisional_index if the is_provisional column exists
            provisional_index = None
            if "is_provisional" in fy_data.columns:
                prov_rows = fy_data[fy_data["is_provisional"] == True]
                if not prov_rows.empty:
                    # provisional_index is the index in the *output* arrays
                    # (after prepending Oct 1 anchor)
                    offset = 1 if prepended_anchor else 0
                    prov_pos = fy_data.index.get_loc(prov_rows.index[0])
                    provisional_index = prov_pos + offset

            trace = {
                "fy_days": fy_days,
                "dates": dates,
                "cumulative_count": counts,
                "cumulative_dollars_m": dollars_m,
                "pct_of_approp": pct_approp,
            }
            if provisional_index is not None:
                trace["provisional_index"] = provisional_index
            year_traces[str(fy)] = trace

        # Anchor all series at fy_day=1 with value 0 before envelope computation
        anchored_frames = []
        for fy in reliable_years:
            fy_data = agency_series[agency_series["fiscal_year"] == fy].sort_values("fy_day")
            if fy_data.empty:
                continue
            if fy_data["fy_day"].iloc[0] != 1:
                anchor = fy_data.iloc[:1].copy()
                anchor["fy_day"] = 1
                anchor["date"] = f"{fy - 1}-10-01"
                anchor["cumulative_count"] = 0
                anchor["cumulative_dollars"] = 0.0
                fy_data = pd.concat([anchor, fy_data], ignore_index=True)
            anchored_frames.append(fy_data)
        anchored_series = pd.concat(anchored_frames, ignore_index=True) if anchored_frames else agency_series

        # Add pct_of_approp to series for envelope computation
        pct_records = []
        for fy in band_fys:
            approp_val = agency_approp.get(fy)
            if not approp_val or approp_val <= 0:
                continue
            fy_data = anchored_series[anchored_series["fiscal_year"] == fy].copy()
            fy_data["pct_of_approp"] = fy_data["cumulative_dollars"] / approp_val * 100
            pct_records.append(fy_data)

        pct_band_fys = [fy for fy in band_fys if agency_approp.get(fy, 0) > 0]

        if pct_records:
            pct_series = pd.concat(pct_records, ignore_index=True)
            envelope_pct = _build_awards_envelope(pct_series, pct_band_fys, "pct_of_approp")
        else:
            envelope_pct = None

        # Also build dollar and count envelopes from reliable years only
        reliable_anchored = anchored_series[anchored_series["fiscal_year"].isin(reliable_years)]
        envelope_count = _build_awards_envelope(reliable_anchored, band_fys, "cumulative_count")
        envelope_dollars = _build_awards_envelope(reliable_anchored, band_fys, "cumulative_dollars", scale=1e6)

        awards_data[agency_key] = {
            "source_type": acfg["source"],
            "metric_label": acfg["metric_label"],
            "fiscal_years": [fy for fy in fiscal_years if fy in reliable_years],
            "years": year_traces,
            "envelope_count": envelope_count,
            "envelope_dollars": envelope_dollars,
            "envelope_pct": envelope_pct,
        }

    # Build summary
    awards_summary = {}
    if not summary_df.empty:
        for _, row in summary_df.iterrows():
            agency = row["agency"]
            rec = {}
            for col in summary_df.columns:
                v = row[col]
                if pd.isna(v):
                    rec[col] = None
                elif isinstance(v, (np.floating, np.integer)):
                    rec[col] = round(float(v), 2)
                else:
                    rec[col] = v

            # Add appropriation for context
            agency_approp = approp_lookup.get(agency, {})
            approp_val = agency_approp.get(CURRENT_FY)
            if approp_val:
                rec["appropriation"] = round(approp_val, 2)

            # Compute pct_of_approp fields for normalized comparisons
            latest_day = rec.get("latest_fy_day")
            cumul_dollars = rec.get("cumul_dollars")

            # Current FY: cumulative $ as % of appropriation
            if approp_val and approp_val > 0 and cumul_dollars is not None:
                rec["cumul_pct_approp"] = round(cumul_dollars / approp_val * 100, 3)
            else:
                rec["cumul_pct_approp"] = None

            # Prior FY: prior year $ at same day as % of prior year appropriation
            prior_approp = agency_approp.get(CURRENT_FY - 1)
            prior_dollars = rec.get("prior_year_dollars")
            if prior_approp and prior_approp > 0 and prior_dollars is not None:
                rec["prior_year_pct_approp"] = round(prior_dollars / prior_approp * 100, 3)
            else:
                rec["prior_year_pct_approp"] = None

            # Mean pct_of_approp across band years at same fy_day.
            # Uses linear interpolation to handle leap-year day offsets,
            # matching the envelope computation.
            agency_series_for_mean = series[series["agency"] == agency]
            reliable = _detect_reliable_years(
                agency_series_for_mean,
                sorted(agency_series_for_mean["fiscal_year"].unique()),
                CURRENT_FY,
            )
            band = [
                fy for fy in reliable
                if fy not in BAND_YEARS_EXCLUDE and fy != CURRENT_FY
            ]
            pct_vals = []
            dollar_vals = []
            count_vals = []
            for fy in band:
                fy_data = agency_series_for_mean[
                    agency_series_for_mean["fiscal_year"] == fy
                ].sort_values("fy_day")
                if fy_data.empty:
                    continue
                days = fy_data["fy_day"].values
                dollars = fy_data["cumulative_dollars"].values
                if latest_day < days[0]:
                    continue
                interp_dollars = float(np.interp(latest_day, days, dollars))
                dollar_vals.append(interp_dollars)
                if "cumulative_count" in fy_data.columns:
                    counts = fy_data["cumulative_count"].values
                    count_vals.append(float(np.interp(latest_day, days, counts)))
                fy_approp = agency_approp.get(fy)
                if fy_approp and fy_approp > 0:
                    pct_vals.append(interp_dollars / fy_approp * 100)

            if pct_vals:
                rec["mean_pct_approp"] = round(float(np.mean(pct_vals)), 4)
            else:
                rec["mean_pct_approp"] = None
            if dollar_vals:
                rec["mean_dollars"] = round(float(np.mean(dollar_vals)), 2)
            if count_vals:
                rec["mean_count"] = round(float(np.mean(count_vals)), 2)

            awards_summary[agency] = rec

    # Fill in zero stubs for sub-agencies missing the current FY.
    # When a sub-agency (e.g. NIMHD) has prior-year data but no current-FY
    # awards yet, the chart shows no FY line and the metrics table disappears.
    # Fix: mirror the parent's current-FY date structure with zero values.
    fy_key = str(CURRENT_FY)
    for agency_key, adata in awards_data.items():
        if fy_key in adata["years"]:
            continue
        parent_key = AWARDS_CONFIG.get(agency_key, {}).get("parent")
        if not parent_key or parent_key not in awards_data:
            continue
        parent_fy = awards_data[parent_key]["years"].get(fy_key)
        if not parent_fy:
            continue

        n = len(parent_fy["fy_days"])
        adata["years"][fy_key] = {
            "fy_days": list(parent_fy["fy_days"]),
            "dates": list(parent_fy["dates"]),
            "cumulative_count": [0] * n,
            "cumulative_dollars_m": [0.0] * n,
            "pct_of_approp": [0.0] * n,
        }
        if CURRENT_FY not in adata["fiscal_years"]:
            adata["fiscal_years"].append(CURRENT_FY)

        # Also fill in a zero summary so the metrics table renders
        if agency_key not in awards_summary:
            parent_summ = awards_summary.get(parent_key)
            if parent_summ:
                agency_approp_lookup = approp_lookup.get(agency_key, {})
                approp_val = agency_approp_lookup.get(CURRENT_FY)
                awards_summary[agency_key] = {
                    "agency": agency_key,
                    "source_type": adata["source_type"],
                    "latest_fy_day": parent_summ["latest_fy_day"],
                    "latest_date": parent_summ["latest_date"],
                    "cumul_count": 0,
                    "cumul_dollars": 0.0,
                    "prior_year_count": None,
                    "prior_year_dollars": None,
                    "mean_count": None,
                    "mean_dollars": None,
                    "appropriation": round(approp_val, 2) if approp_val else None,
                    "cumul_pct_approp": 0.0,
                    "prior_year_pct_approp": None,
                    "mean_pct_approp": None,
                    "mean_dollars": None,
                    "mean_count": None,
                }
                # Compute prior-year and mean benchmarks from the sub-agency's own history
                agency_series_sub = series[series["agency"] == agency_key]
                if not agency_series_sub.empty:
                    latest_day = parent_summ["latest_fy_day"]
                    reliable = _detect_reliable_years(
                        agency_series_sub,
                        sorted(agency_series_sub["fiscal_year"].unique()),
                        CURRENT_FY,
                    )
                    band = [fy for fy in reliable
                            if fy not in BAND_YEARS_EXCLUDE and fy != CURRENT_FY]
                    pct_vals, dollar_vals, count_vals = [], [], []
                    prior_dollars = prior_count = None
                    for fy in sorted(reliable):
                        if fy == CURRENT_FY:
                            continue
                        fy_data = agency_series_sub[
                            agency_series_sub["fiscal_year"] == fy
                        ].sort_values("fy_day")
                        if fy_data.empty or latest_day < fy_data["fy_day"].values[0]:
                            continue
                        days = fy_data["fy_day"].values
                        dollars = fy_data["cumulative_dollars"].values
                        interp_d = float(np.interp(latest_day, days, dollars))
                        if fy == CURRENT_FY - 1:
                            prior_dollars = interp_d
                            if "cumulative_count" in fy_data.columns:
                                prior_count = float(np.interp(
                                    latest_day, days,
                                    fy_data["cumulative_count"].values))
                        if fy in band:
                            dollar_vals.append(interp_d)
                            if "cumulative_count" in fy_data.columns:
                                count_vals.append(float(np.interp(
                                    latest_day, days,
                                    fy_data["cumulative_count"].values)))
                            fy_approp = agency_approp_lookup.get(fy)
                            if fy_approp and fy_approp > 0:
                                pct_vals.append(interp_d / fy_approp * 100)

                    rec = awards_summary[agency_key]
                    rec["prior_year_dollars"] = round(prior_dollars, 2) if prior_dollars is not None else None
                    rec["prior_year_count"] = round(prior_count, 2) if prior_count is not None else None
                    if prior_dollars is not None:
                        prior_approp = agency_approp_lookup.get(CURRENT_FY - 1)
                        if prior_approp and prior_approp > 0:
                            rec["prior_year_pct_approp"] = round(prior_dollars / prior_approp * 100, 3)
                    if pct_vals:
                        rec["mean_pct_approp"] = round(float(np.mean(pct_vals)), 4)
                    if dollar_vals:
                        rec["mean_dollars"] = round(float(np.mean(dollar_vals)), 2)
                    if count_vals:
                        rec["mean_count"] = round(float(np.mean(count_vals)), 2)

    return awards_data, awards_summary


def _build_awards_envelope(agency_series, band_fys, y_col, scale=1):
    """Compute min/max/mean envelope for awards data.

    For each year, linearly interpolates onto a common grid of fy_days
    so that leap-year vs non-leap-year differences don't create
    stair-step artifacts in monthly data.
    """
    if not band_fys:
        return None

    # Build per-FY sorted arrays of (fy_day, value)
    fy_arrays = {}
    for fy in band_fys:
        fy_data = agency_series[agency_series["fiscal_year"] == fy].sort_values("fy_day")
        if fy_data.empty:
            continue
        days = fy_data["fy_day"].values
        vals = fy_data[y_col].values / scale if scale != 1 else fy_data[y_col].values
        fy_arrays[fy] = (days, vals)

    if not fy_arrays:
        return None

    # Use the fy_days from the year with the most points as the base grid,
    # then extend to cover the full day range across all band years so the
    # envelope never ends before a highlighted year's line does.
    canonical_fy = max(fy_arrays, key=lambda fy: len(fy_arrays[fy][0]))
    sample_days = list(fy_arrays[canonical_fy][0])
    max_day = max(int(days[-1]) for days, _ in fy_arrays.values())
    if sample_days and sample_days[-1] < max_day:
        for d in range(sample_days[-1] + 1, max_day + 1):
            sample_days.append(d)

    valid_days, min_vals, max_vals, med_vals = [], [], [], []
    for day in sample_days:
        vals = []
        for fy, (days, values) in fy_arrays.items():
            # Linear interpolation at this day
            if day <= days[0]:
                vals.append(float(values[0]))
            elif day >= days[-1]:
                vals.append(float(values[-1]))
            else:
                v = float(np.interp(day, days, values))
                vals.append(v)
        if vals:
            valid_days.append(int(day))
            min_vals.append(round(min(vals), 4))
            max_vals.append(round(max(vals), 4))
            med_vals.append(round(float(np.mean(vals)), 4))

    return {
        "fy_days": valid_days,
        "min": min_vals,
        "max": max_vals,
        "mean": med_vals,
        "band_fys": band_fys,
    }


def main():
    print("Loading preprocessed CSVs...")
    obligation_series, approp_summary, yoy_comparison = load_csvs()

    # Derive latest period label from obligation_series for current FY
    current_fy_data = obligation_series[obligation_series["fiscal_year"] == CURRENT_FY]
    if not current_fy_data.empty:
        latest_month = int(current_fy_data["period_month"].max())
        latest_period_label = FY_MONTH_LABELS.get(latest_month, f"Month {latest_month}")
    else:
        latest_period_label = None

    # Load awards data if available
    awards_data, awards_summary_data = build_awards_site_data()

    print("Building chart data...")
    site_data = {
        "config": {
            "agencies": build_agency_configs(),
            "current_fy": CURRENT_FY,
            "highlight_years": HIGHLIGHT_YEARS,
            "band_years_exclude": list(BAND_YEARS_EXCLUDE),
            "fy_month_labels": FY_MONTH_LABELS,
            "build_date": datetime.date.today().isoformat(),
            "latest_period_label": latest_period_label,
        },
        "spenddown": build_spenddown_data(obligation_series),
        "multi_agency": build_multi_agency_data(obligation_series),
        "summaries": build_summary_data(obligation_series, approp_summary),
        "tables": build_data_tables(approp_summary, yoy_comparison),
    }

    # Add awards data if available
    if awards_data:
        site_data["awards"] = awards_data
    if awards_summary_data:
        site_data["awards_summary"] = awards_summary_data

    # Add unified USASpending comparison data if available (experimental)
    unified_series_path = AWARDS_PROCESSED_DIR / "award_series_unified.csv"
    if unified_series_path.exists():
        print("Loading unified USASpending comparison data...")
        # Temporarily override AWARDS_CONFIG source types so build treats all as usaspending
        from config import AWARDS_CONFIG as _acfg
        _saved = {k: dict(v) for k, v in _acfg.items()}
        for k in _acfg:
            _acfg[k] = {**_acfg[k], "source": "usaspending"}
        try:
            unified_data, unified_summary = build_awards_site_data(
                series_override=unified_series_path,
                summary_override=AWARDS_PROCESSED_DIR / "award_summary_unified.csv",
            )
        except TypeError:
            # Fallback if build_awards_site_data doesn't accept overrides yet
            unified_data, unified_summary = {}, {}
        # Restore
        for k in _saved:
            _acfg[k] = _saved[k]
        if unified_data:
            site_data["awards_unified"] = unified_data
        if unified_summary:
            site_data["awards_unified_summary"] = unified_summary

    # Add "all awards" data if available
    all_awards_series_path = AWARDS_PROCESSED_DIR / "award_series_all.csv"
    if all_awards_series_path.exists():
        print("Loading all-awards data...")
        from config import AWARDS_CONFIG as _acfg_aa, ALL_AWARDS_CONFIG as _aacfg
        _saved_aa = {k: dict(v) for k, v in _acfg_aa.items()}
        for k in _aacfg:
            if k in _acfg_aa:
                _src = _aacfg[k].get("source", "usaspending")
                _acfg_aa[k] = {**_acfg_aa[k], **_aacfg[k], "source": _src}
        try:
            all_awards_data, all_awards_summary = build_awards_site_data(
                series_override=all_awards_series_path,
                summary_override=AWARDS_PROCESSED_DIR / "award_summary_all.csv",
            )
        except TypeError:
            all_awards_data, all_awards_summary = {}, {}
        for k in _saved_aa:
            _acfg_aa[k] = _saved_aa[k]
        if all_awards_data:
            site_data["awards_all"] = all_awards_data
        if all_awards_summary:
            site_data["awards_all_summary"] = all_awards_summary

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return round(float(obj), 6)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    # Split into parent-only (fast initial load) and sub-agency detail
    agencies_cfg = site_data.get("config", {}).get("agencies", {})
    sub_keys = {k for k, v in agencies_cfg.items() if v.get("parent")}

    # Sections that contain per-agency keyed data
    agency_sections = [
        "spenddown", "awards", "awards_all", "awards_unified",
        "summaries", "awards_summary", "awards_all_summary", "awards_unified_summary",
    ]

    core_data = {}
    detail_data = {}
    for section, data in site_data.items():
        if section in agency_sections and isinstance(data, dict):
            core_data[section] = {k: v for k, v in data.items() if k not in sub_keys}
            sub_part = {k: v for k, v in data.items() if k in sub_keys}
            if sub_part:
                detail_data[section] = sub_part
        else:
            core_data[section] = data

    out_path = SITE_DATA_DIR / "site_data.json"
    with open(out_path, "w") as f:
        json.dump(core_data, f, cls=NumpyEncoder)
    core_kb = out_path.stat().st_size / 1024

    detail_path = SITE_DATA_DIR / "site_data_detail.json"
    with open(detail_path, "w") as f:
        json.dump(detail_data, f, cls=NumpyEncoder)
    detail_kb = detail_path.stat().st_size / 1024

    print(f"Wrote {out_path} ({core_kb:.0f} KB)")
    print(f"Wrote {detail_path} ({detail_kb:.0f} KB)")
    print("Done. Open docs/index.html to view.")


if __name__ == "__main__":
    main()
