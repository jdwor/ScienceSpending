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

from config import AGENCIES, CURRENT_FY, HIGHLIGHT_YEARS, BAND_YEARS_EXCLUDE, FY_MONTH_LABELS

PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"
SITE_DATA_DIR = Path(__file__).resolve().parent / "docs" / "data"


def load_csvs():
    obligation_series = pd.read_csv(PROCESSED_DIR / "obligation_series.csv")
    approp_summary = pd.read_csv(PROCESSED_DIR / "approp_summary.csv")
    yoy_comparison = pd.read_csv(PROCESSED_DIR / "yoy_comparison.csv")
    return obligation_series, approp_summary, yoy_comparison


def build_agency_configs():
    """Export agency config for the frontend."""
    return {
        key: {
            "display_name": cfg["display_name"],
            "color": cfg["color"],
        }
        for key, cfg in AGENCIES.items()
    }


def compute_prior_year_envelope(agency_data, fiscal_years, show_pct=True):
    """Compute min/max/median band from band-eligible fiscal years."""
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
            med_vals.append(round(float(np.median(vals)), 3))
        else:
            min_vals.append(None)
            max_vals.append(None)
            med_vals.append(None)

    return {
        "months": all_months,
        "min": min_vals,
        "max": max_vals,
        "median": med_vals,
        "band_fys": band_fys,
    }


def compute_median_lookup(agency_data, fiscal_years, show_pct=True):
    """Build {month: median_value} from band-eligible years."""
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    medians = {}
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
            medians[str(m)] = round(float(np.median(vals)), 3)
    return medians


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

            year_traces[str(fy)] = {
                "months": months,
                "pct": pct_vals,
                "dollars_b": dollar_vals,
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
        agency_all = obligation_series[obligation_series["agency"] == agency_key]
        all_fys = sorted(agency_all["fiscal_year"].unique())
        agency_fy = agency_all[agency_all["fiscal_year"] == CURRENT_FY].sort_values("period_month")
        if agency_fy.empty:
            continue

        medians = compute_median_lookup(agency_all, all_fys, show_pct=True)

        x_vals = [1]
        y_vals = [100.0]

        for _, row in agency_fy.iterrows():
            m = row["period_month"]
            med = medians.get(str(int(m)))
            curr_pct = row["pct_obligated"]
            if med and med > 0 and curr_pct is not None:
                pct_of_median = curr_pct / med * 100
            else:
                pct_of_median = None
            if pct_of_median is not None:
                x_vals.append(int(m))
                y_vals.append(round(pct_of_median, 2))

        traces[agency_key] = {
            "months": x_vals,
            "pct_of_median": y_vals,
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

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DATA_DIR / "site_data.json"

    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return round(float(obj), 6)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(out_path, "w") as f:
        json.dump(site_data, f, cls=NumpyEncoder)

    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({size_kb:.0f} KB)")
    print("Done. Open docs/index.html to view.")


if __name__ == "__main__":
    main()
