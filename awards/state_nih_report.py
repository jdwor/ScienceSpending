"""
Generate per-state NIH funding-curve PDFs.

Reads cached NIH Reporter data (both new awards and all awards), aggregates
by recipient state, and produces a one-page (or 2-page with congressional
district breakdown) PDF per state, suitable for distribution to Members.

Usage:
    python3 -m awards.state_nih_report [--state CA] [--limit 5]
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd

from config import CURRENT_FY, NIH_IC_DISPLAY_NAMES

ROOT = Path(__file__).resolve().parent.parent
NIH_NEW_CACHE = ROOT / "awards" / "cache" / "nih"
NIH_ALL_CACHE = ROOT / "awards" / "cache" / "nih_all"
FONT_DIR = ROOT / "awards" / "fonts"
OUTPUT_DIR = ROOT / "output" / "state_pdfs"

# Match the site's typography: Newsreader (serif) for display, Inter (sans)
# for body. Fonts are downloaded on first run from the Google Fonts repo and
# cached locally in awards/fonts/ (gitignored).
_FONT_FILES = {
    "Newsreader[opsz,wght].ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/newsreader/"
        "Newsreader%5Bopsz%2Cwght%5D.ttf",
    "Newsreader-Italic[opsz,wght].ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/newsreader/"
        "Newsreader-Italic%5Bopsz%2Cwght%5D.ttf",
    "Inter[opsz,wght].ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/"
        "Inter%5Bopsz%2Cwght%5D.ttf",
}
SERIF = "Newsreader"
SANS = "Inter"


def _ensure_fonts():
    """Download Newsreader + Inter on first run and register with matplotlib."""
    import requests
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in _FONT_FILES.items():
        path = FONT_DIR / fname
        if not path.exists():
            print(f"  Downloading {fname}...")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        fm.fontManager.addfont(str(path))
    # Make Inter the default sans-serif for axis ticks, legends, etc.
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [SANS, "DejaVu Sans"]
    plt.rcParams["font.serif"] = [SERIF, "DejaVu Serif"]
    plt.rcParams["pdf.fonttype"] = 42  # TrueType embedding for crisp PDFs

PRIOR_YEAR = CURRENT_FY - 1                       # FY25
BASELINE_YEARS = list(range(CURRENT_FY - 6, CURRENT_FY - 1))  # FY20-24
LOAD_YEARS = sorted(set(BASELINE_YEARS + [PRIOR_YEAR, CURRENT_FY]))

NIH_BLUE = "#2c5f8a"
NIH_BLUE_LIGHT = "#7ba3c4"
# Site design tokens (from docs/css/style.css :root variables)
INK = "#202124"
INK_SOFT = "#4a4a4a"
GRAY = "#606060"
LIGHT_GRAY = "#dadce0"
SURFACE_ALT = "#efefef"
TEAL_ACCENT = "#0a6b5e"   # callout border
POSITIVE = "#064d49"      # well-above / pos deltas
NEGATIVE = "#b35a3a"      # well-below / neg deltas

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------

def _load_cache(cache_dir: Path, fiscal_years: list[int]) -> pd.DataFrame:
    """Load all extramural NIH records from cached JSON files.

    Mirrors the filtering in awards.fetch_nih._extract_records (skip
    intramural Z-prefixed activity codes), but additionally keeps
    recipient state, organization name, and congressional district.
    The cache files themselves were fetched with the correct
    `award_types` for the new-vs-all distinction (Types 1+2 for
    `cache/nih/`, Types 1+2+3+4+5+7+9 for `cache/nih_all/`), so
    award-type filtering is implicit.
    """
    rows = []
    for fy in fiscal_years:
        for cache_file in sorted(cache_dir.glob(f"fy{fy}_*.json")):
            with open(cache_file) as f:
                recs = json.load(f)
            for r in recs:
                activity = (r.get("activity_code") or "")
                if activity.startswith("Z"):
                    continue
                org = r.get("organization") or {}
                state = org.get("org_state")
                if not state or state not in US_STATES:
                    continue
                date_str = (r.get("award_notice_date") or "")[:10]
                fy_day_val = None
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                        fy_day_val = (dt - date(fy - 1, 10, 1)).days + 1
                    except ValueError:
                        pass
                rows.append({
                    "fiscal_year": fy,
                    "date": date_str,
                    "fy_day": fy_day_val,
                    "state": state,
                    "org_name": (org.get("org_name") or "").strip(),
                    "cong_dist": (r.get("cong_dist") or "").strip(),
                    "project_num": r.get("project_num", ""),
                    "award_amount": r.get("award_amount") or 0,
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Match the dedup behavior used by fetch_nih.fetch_nih_awards
    df = df.drop_duplicates(subset=["project_num", "fiscal_year"], keep="first")
    return df


def load_all_records() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (new_awards_df, all_awards_df)."""
    print("Loading NIH new-awards cache...")
    new_df = _load_cache(NIH_NEW_CACHE, LOAD_YEARS)
    print(f"  {len(new_df):,} records, {new_df['state'].nunique()} states")

    print("Loading NIH all-awards cache...")
    all_df = _load_cache(NIH_ALL_CACHE, LOAD_YEARS)
    print(f"  {len(all_df):,} records, {all_df['state'].nunique()} states")
    return new_df, all_df


# ----------------------------------------------------------------------
# Series construction
# ----------------------------------------------------------------------

def _fy_day(d: date, fy: int) -> int:
    return (d - date(fy - 1, 10, 1)).days + 1


def _build_cumulative_series(sub: pd.DataFrame) -> pd.DataFrame:
    """Build per-FY daily cumulative count and dollars from a record df."""
    if sub.empty:
        return pd.DataFrame(columns=["fiscal_year", "fy_day", "cumulative_count", "cumulative_dollars"])
    sub = sub.copy()
    sub["_date"] = pd.to_datetime(sub["date"], errors="coerce").dt.date
    sub = sub.dropna(subset=["_date"])

    out = []
    for fy, g in sub.groupby("fiscal_year"):
        fy = int(fy)
        g = g[(g["_date"] >= date(fy - 1, 10, 1)) & (g["_date"] <= date(fy, 9, 30))]
        if g.empty:
            continue
        daily = (
            g.groupby("_date")
            .agg(count=("_date", "size"), dollars=("award_amount", "sum"))
            .sort_index()
        )
        daily["cumulative_count"] = daily["count"].cumsum()
        daily["cumulative_dollars"] = daily["dollars"].cumsum()
        out.append({
            "fiscal_year": fy, "fy_day": 1,
            "cumulative_count": 0, "cumulative_dollars": 0.0,
        })
        for d, row in daily.iterrows():
            out.append({
                "fiscal_year": fy,
                "fy_day": _fy_day(d, fy),
                "cumulative_count": int(row["cumulative_count"]),
                "cumulative_dollars": float(row["cumulative_dollars"]),
            })
        if fy < CURRENT_FY:
            fy_end_day = _fy_day(date(fy, 9, 30), fy)
            last = out[-1]
            if last["fy_day"] < fy_end_day:
                out.append({
                    "fiscal_year": fy, "fy_day": fy_end_day,
                    "cumulative_count": last["cumulative_count"],
                    "cumulative_dollars": last["cumulative_dollars"],
                })
    return pd.DataFrame(out).sort_values(["fiscal_year", "fy_day"]).reset_index(drop=True)


def build_state_series(df: pd.DataFrame, state: str) -> pd.DataFrame:
    """Daily cumulative series for one state, all loaded FYs."""
    return _build_cumulative_series(df[df["state"] == state])


def _interp_at(series: pd.DataFrame, fy: int, fy_day: int, col: str) -> float | None:
    g = series[series["fiscal_year"] == fy].sort_values("fy_day")
    if g.empty:
        return None
    if fy_day < g["fy_day"].iloc[0]:
        return None
    if fy_day > g["fy_day"].iloc[-1]:
        return float(g[col].iloc[-1])
    return float(np.interp(fy_day, g["fy_day"].values, g[col].values))


def compute_metrics(series: pd.DataFrame) -> dict:
    """Headline metrics at the latest fy_day in the current FY."""
    current = series[series["fiscal_year"] == CURRENT_FY]
    if current.empty:
        return {}
    latest = current.loc[current["fy_day"].idxmax()]
    latest_day = int(latest["fy_day"])
    cumul_d = float(latest["cumulative_dollars"])
    cumul_c = int(latest["cumulative_count"])

    prior_d = _interp_at(series, PRIOR_YEAR, latest_day, "cumulative_dollars")
    prior_c = _interp_at(series, PRIOR_YEAR, latest_day, "cumulative_count")

    baseline_d = [
        _interp_at(series, fy, latest_day, "cumulative_dollars")
        for fy in BASELINE_YEARS
    ]
    baseline_d = [v for v in baseline_d if v is not None]
    mean_d = float(np.mean(baseline_d)) if baseline_d else None

    baseline_c = [
        _interp_at(series, fy, latest_day, "cumulative_count")
        for fy in BASELINE_YEARS
    ]
    baseline_c = [v for v in baseline_c if v is not None]
    mean_c = float(np.mean(baseline_c)) if baseline_c else None

    return {
        "latest_fy_day": latest_day,
        "cumul_dollars": cumul_d,
        "cumul_count": cumul_c,
        "prior_year_dollars": prior_d,
        "prior_year_count": prior_c,
        "yoy_dollars_pct": ((cumul_d - prior_d) / prior_d * 100) if prior_d else None,
        "mean_dollars": mean_d,
        "mean_count": mean_c,
        "vs_mean_pct": ((cumul_d - mean_d) / mean_d * 100) if mean_d else None,
        "vs_mean_count_pct": ((cumul_c - mean_c) / mean_c * 100) if mean_c else None,
    }


# ----------------------------------------------------------------------
# Aggregations
# ----------------------------------------------------------------------

def top_recipients(df: pd.DataFrame, state: str,
                   latest_fy_day: int | None, n: int = 10) -> pd.DataFrame:
    """Top recipients with point-in-time FY26 totals + 5-yr historical avg.

    All years are filtered to records with fy_day <= *latest_fy_day*, so
    the FY26 numbers and the baseline comparison are at the same point
    in the fiscal year. Organizations not seen in a baseline year are
    excluded from that year's contribution to the mean (i.e., mean is
    computed only over years the org received NIH funding).
    """
    sub = df[df["state"] == state].copy()
    if sub.empty or latest_fy_day is None:
        return pd.DataFrame(
            columns=["org_name", "dollars_cur", "count_cur",
                     "dollars_mean", "count_mean"]
        )
    sub = sub.dropna(subset=["fy_day"])
    sub = sub[sub["fy_day"] <= latest_fy_day]
    if sub.empty:
        return pd.DataFrame(
            columns=["org_name", "dollars_cur", "count_cur",
                     "dollars_mean", "count_mean"]
        )

    per_fy = sub.groupby(["org_name", "fiscal_year"]).agg(
        d=("award_amount", "sum"),
        c=("project_num", "size"),
    ).reset_index()

    cur = per_fy[per_fy["fiscal_year"] == CURRENT_FY].set_index("org_name")
    cur = cur.rename(columns={"d": "dollars_cur", "c": "count_cur"})[["dollars_cur", "count_cur"]]

    base = per_fy[per_fy["fiscal_year"].isin(BASELINE_YEARS)]
    if not base.empty:
        mean_df = base.groupby("org_name").agg(
            dollars_mean=("d", "mean"),
            count_mean=("c", "mean"),
        )
    else:
        mean_df = pd.DataFrame(columns=["dollars_mean", "count_mean"])

    out = cur.join(mean_df, how="left").reset_index()
    out["dollars_mean"] = out["dollars_mean"].fillna(0)
    out["count_mean"] = out["count_mean"].fillna(0)
    out = out.sort_values("dollars_cur", ascending=False).head(n).reset_index(drop=True)
    return out


def top_ics(df: pd.DataFrame, state: str, n: int = 5) -> pd.DataFrame:
    sub = df[(df["state"] == state) & (df["fiscal_year"] == CURRENT_FY)]
    if sub.empty:
        return pd.DataFrame(columns=["ic_code", "dollars", "count"])
    return (
        sub.groupby("ic_code", as_index=False)
        .agg(dollars=("award_amount", "sum"), count=("project_num", "size"))
        .sort_values("dollars", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def district_breakdown(df: pd.DataFrame, state: str,
                       latest_fy_day: int | None) -> pd.DataFrame:
    """Point-in-time district breakdown.

    All FYs (current, prior, baseline) are filtered to records with
    fy_day <= *latest_fy_day*, so comparisons are apples-to-apples at
    the same point in the fiscal year. *latest_fy_day* is typically the
    latest fy_day from the current-FY records for this state.
    """
    sub = df[df["state"] == state].copy()
    sub = sub[sub["cong_dist"].str.startswith(state)]
    if sub.empty or latest_fy_day is None:
        return pd.DataFrame()
    sub = sub.dropna(subset=["fy_day"])
    sub = sub[sub["fy_day"] <= latest_fy_day]

    cur = sub[sub["fiscal_year"] == CURRENT_FY].groupby("cong_dist").agg(
        dollars_cur=("award_amount", "sum"),
        count_cur=("project_num", "size"),
    )
    prior = sub[sub["fiscal_year"] == PRIOR_YEAR].groupby("cong_dist").agg(
        dollars_prior=("award_amount", "sum"),
        count_prior=("project_num", "size"),
    )

    # 5-year baseline mean per district (mean of per-FY totals, at same fy_day)
    baseline = sub[sub["fiscal_year"].isin(BASELINE_YEARS)]
    if not baseline.empty:
        per_fy = baseline.groupby(["cong_dist", "fiscal_year"]).agg(
            d=("award_amount", "sum"),
            c=("project_num", "size"),
        ).reset_index()
        mean_df = per_fy.groupby("cong_dist").agg(
            dollars_mean=("d", "mean"),
            count_mean=("c", "mean"),
        )
    else:
        mean_df = pd.DataFrame(columns=["dollars_mean", "count_mean"])

    out = cur.join(prior, how="outer").join(mean_df, how="outer").fillna(0).reset_index()
    out = out.sort_values("dollars_cur", ascending=False).reset_index(drop=True)
    return out


# ----------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------

def fmt_dollars(v: float | None) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    av = abs(v)
    if av >= 1e9:
        return f"${v/1e9:.2f}B"
    if av >= 1e6:
        return f"${v/1e6:.1f}M"
    if av >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def fmt_pct(v: float | None) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def fmt_count(v: float | int | None) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    return f"{int(round(v)):,}"


# Common acronyms in NIH RePORTER org names that .title() would mangle.
# Compared in upper-case form against each whitespace-delimited token.
_TITLE_ACRONYMS = {
    "UT", "UC", "UCLA", "UCSF", "UCSD", "USC", "MIT", "NIH", "NYU", "BU",
    "JHU", "MGH", "BWH", "VA", "TX", "NIST", "MD", "NC", "SC", "USDA",
    "DOE", "DOD", "II", "III", "IV", "V", "VI", "PhD", "MD/PhD",
    "RTI", "SRI", "CWRU", "NJIT", "MIT/WHOI",
}

import re as _re


def smart_title(s: str) -> str:
    """Title-case an NIH org name without mangling apostrophes or acronyms.

    Python's ``str.title()`` capitalizes the letter following any non-alpha,
    so "CHILDREN'S" becomes "Children'S" — broken English. It also lowers
    valid acronyms like "UT" to "Ut". This wrapper fixes both.
    """
    if not s or not s.isupper():
        return s
    out_words = []
    for word in s.split():
        if word in _TITLE_ACRONYMS:
            out_words.append(word)
            continue
        # Title-case the word, then re-lowercase any letter that immediately
        # follows an apostrophe (Children's, O'Brien, etc.)
        tc = word.title()
        tc = _re.sub(r"'([A-Za-z])", lambda m: "'" + m.group(1).lower(), tc)
        out_words.append(tc)
    return " ".join(out_words)


# ----------------------------------------------------------------------
# Chart drawing
# ----------------------------------------------------------------------

# Fiscal-year month-tick positions (Oct=1 ... Sep=12). fy_day of first of month.
_FY_MONTH_LABELS = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar",
                    "Apr", "May", "Jun", "Jul", "Aug", "Sep"]


def _fy_month_tick_days() -> tuple[list[int], list[str]]:
    days = []
    for i, _ in enumerate(_FY_MONTH_LABELS):
        # First-of-month fy_day; use Oct=1 -> 1, Nov -> 32, Dec -> 62, ...
        cal_month = (i + 9) % 12 + 1
        cal_year = CURRENT_FY - 1 if cal_month >= 10 else CURRENT_FY
        d = date(cal_year, cal_month, 1)
        days.append(_fy_day(d, CURRENT_FY))
    return days, _FY_MONTH_LABELS


def _draw_series_chart(ax, series: pd.DataFrame, title: str,
                       y_col: str = "cumulative_dollars",
                       y_scale: float = 1e6, y_label: str = "Cumulative ($M)",
                       show_legend: bool = True):
    """Render one cumulative chart with envelope + lines.

    *y_col* — column from the series df to plot ("cumulative_dollars"
    or "cumulative_count"). *y_scale* divides values for display
    (1e6 for $M, 1 for counts).
    """
    ax.set_title(title, fontsize=11, fontweight="bold", color=INK, loc="left",
                 pad=6, family=SANS)

    grid = np.arange(1, 366)

    fy_arrays = {}
    for fy in [*BASELINE_YEARS, PRIOR_YEAR, CURRENT_FY]:
        g = series[series["fiscal_year"] == fy].sort_values("fy_day")
        if g.empty:
            continue
        d = g["fy_day"].values
        v = g[y_col].values / y_scale
        if len(d) == 1:
            interp = np.full_like(grid, v[0], dtype=float)
        else:
            interp = np.interp(grid, d, v, left=v[0], right=v[-1])
        fy_arrays[fy] = (d, v, interp)

    baseline_arrs = [arr for fy, (_, _, arr) in fy_arrays.items() if fy in BASELINE_YEARS]
    if baseline_arrs:
        stacked = np.vstack(baseline_arrs)
        env_min = stacked.min(axis=0)
        env_max = stacked.max(axis=0)
        env_mean = stacked.mean(axis=0)
        ax.fill_between(grid, env_min, env_max, color=LIGHT_GRAY, alpha=0.7,
                        linewidth=0, label=f"FY{BASELINE_YEARS[0]}–{BASELINE_YEARS[-1]} range")
        ax.plot(grid, env_mean, color=GRAY, linestyle="--", linewidth=1.1,
                label=f"5-yr avg")

    if PRIOR_YEAR in fy_arrays:
        d, v, _ = fy_arrays[PRIOR_YEAR]
        ax.plot(d, v, color=NIH_BLUE_LIGHT, linewidth=1.6, label=f"FY{PRIOR_YEAR}")

    if CURRENT_FY in fy_arrays:
        d, v, _ = fy_arrays[CURRENT_FY]
        ax.plot(d, v, color=NIH_BLUE, linewidth=2.4, label=f"FY{CURRENT_FY}")
        ax.scatter([d[-1]], [v[-1]], color=NIH_BLUE, s=22, zorder=5)

    tick_days, tick_labels = _fy_month_tick_days()
    ax.set_xticks(tick_days)
    ax.set_xticklabels(tick_labels, fontsize=7.5, color=INK)
    ax.set_xlim(1, 366)
    ax.set_xlabel("")
    # Y-axis label is redundant with the chart title (e.g. "New award
    # dollars") — dropping it tightens the left margin so the chart's
    # plotting area aligns with the flush-left content above/below.
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=7.5, colors=INK, pad=2)
    ax.grid(True, axis="y", linestyle="-", linewidth=0.4, color=LIGHT_GRAY, alpha=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(LIGHT_GRAY)
    if show_legend:
        ax.legend(loc="upper left", frameon=False, fontsize=7, labelcolor=INK,
                  handlelength=1.2, handletextpad=0.5, borderpad=0.2, ncol=1)


# ----------------------------------------------------------------------
# Page layout
# ----------------------------------------------------------------------

def _draw_hero(ax, state_code: str, state_name: str, latest_date_str: str):
    """Slim hero: state name + subtitle + as-of date."""
    ax.axis("off")
    ax.text(0.0, 0.66, f"{state_name.upper()}", fontsize=24, fontweight="bold",
            color=NIH_BLUE, transform=ax.transAxes,
            family=SERIF, va="center")
    ax.text(0.0, 0.16, "NIH Funding Tracker", fontsize=12, color=INK,
            transform=ax.transAxes, family=SERIF, style="italic", va="center")
    if latest_date_str:
        ax.text(1.0, 0.66,
                f"FY{CURRENT_FY} through {latest_date_str}",
                fontsize=9.5, color=GRAY, transform=ax.transAxes,
                family=SANS, ha="right", va="center")


def _draw_takeaway(ax, state_name: str, latest_date_str: str,
                   state_new_pct: float | None, state_all_pct: float | None):
    """Site-style callout: state deviation + definition.

    Layout matches docs/css/style.css `.callout`: pale-gray background
    with an NIH-blue left bar. State sentence on top; a small italic
    definition line clarifies what "5-year pace" means.
    """
    from matplotlib.patches import Rectangle
    ax.axis("off")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    ax.add_patch(Rectangle(
        (0, 0), 1, 1, transform=ax.transAxes,
        facecolor=SURFACE_ALT, edgecolor="none", zorder=0,
    ))
    ax.add_patch(Rectangle(
        (0, 0), 0.012, 1, transform=ax.transAxes,
        facecolor=NIH_BLUE, edgecolor="none", zorder=1,
    ))

    pad_x = 0.028

    # State sentence — "vs. its 5-year pace" goes at the end of the sentence
    # so it modifies both percentages, not just the first. Manual break
    # before "and" for a natural visual rhythm.
    state_line = (
        f"{state_name}'s NIH funding through {latest_date_str} is "
        f"{_signed_pct(state_new_pct)} on new awards\n"
        f"and {_signed_pct(state_all_pct)} on total grant funding "
        f"vs. its 5-year pace."
    )
    ax.text(pad_x, 0.66, state_line, fontsize=10.5, color=INK,
            transform=ax.transAxes, family=SANS, va="center",
            linespacing=1.35)

    # Definition line — explain what "5-year pace" / "5-year average" means
    # so the term isn't opaque on first read.
    base_lo, base_hi = BASELINE_YEARS[0], BASELINE_YEARS[-1]
    def_line = (
        f"“5-year pace” and “5-year average” refer to the typical "
        f"cumulative NIH funding through this same date over FY{base_lo}–FY{base_hi}."
    )
    ax.text(pad_x, 0.18, def_line, fontsize=8, color=GRAY,
            transform=ax.transAxes, family=SANS, va="center")


def _signed_pct(v: float | None) -> str:
    """Format a deviation %: '−12.3%' / '+4.5%' / '—' (with proper minus glyph)."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—"
    if v >= 0:
        return f"+{v:.1f}%"
    return f"−{abs(v):.1f}%"


def _draw_summary_table(ax, title: str, metrics: dict, latest_date_str: str):
    """Site-style 'awards summary' mini-table.

    Columns: blank | To Date (May 14) | Avg at This Point | vs. Avg
    Rows:    Award Count | Award Dollars
    """
    ax.axis("off")
    # Title (sans, weight 700 to match site headings)
    ax.text(0.0, 1.00, title, fontsize=11, fontweight="bold", color=INK,
            transform=ax.transAxes, ha="left", va="top", family=SANS)

    # Column right-edges for the three numeric columns.
    # Headers are kept short so they don't crowd at small font sizes;
    # the "at the same fy_day" semantics are spelled out in the footer.
    col_to_date_x = 0.54
    col_avg_x = 0.82
    col_vs_x = 1.00

    header_y = 0.72
    sep_y = 0.56
    row_y_top = 0.46
    row_h = 0.28

    ax.text(col_to_date_x, header_y, "TO DATE", fontsize=7.5,
            color=GRAY, transform=ax.transAxes, ha="right", va="top",
            fontweight="bold", family=SANS)
    ax.text(col_avg_x, header_y, "5-YR AVG", fontsize=7.5,
            color=GRAY, transform=ax.transAxes, ha="right", va="top",
            fontweight="bold", family=SANS)
    ax.text(col_vs_x, header_y, "VS. AVG", fontsize=7.5, color=GRAY,
            transform=ax.transAxes, ha="right", va="top",
            fontweight="bold", family=SANS)
    # Header underline
    ax.plot([0, 1], [sep_y, sep_y], color=LIGHT_GRAY, linewidth=0.6,
            transform=ax.transAxes)

    cumul_d = metrics.get("cumul_dollars")
    cumul_c = metrics.get("cumul_count")
    mean_d = metrics.get("mean_dollars")
    mean_c = metrics.get("mean_count")
    vs_mean_d = metrics.get("vs_mean_pct")
    vs_mean_c = metrics.get("vs_mean_count_pct")

    rows = [
        ("Award Dollars", fmt_dollars(cumul_d), fmt_dollars(mean_d), vs_mean_d),
        ("Award Count", fmt_count(cumul_c), fmt_count(mean_c), vs_mean_c),
    ]
    for r, (label, cur, avg, pct) in enumerate(rows):
        y = row_y_top - r * row_h
        ax.text(0.0, y, label, fontsize=9.5, color=INK,
                transform=ax.transAxes, ha="left", va="top", family=SANS)
        ax.text(col_to_date_x, y, cur, fontsize=10.5, color=INK,
                transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", family=SANS)
        ax.text(col_avg_x, y, avg, fontsize=10, color=INK,
                transform=ax.transAxes, ha="right", va="top", family=SANS)
        if pct is None:
            pct_str, pct_color = "N/A", GRAY
        else:
            pct_str = fmt_pct(pct)
            pct_color = POSITIVE if pct >= 0 else NEGATIVE
        ax.text(col_vs_x, y, pct_str, fontsize=10, color=pct_color,
                transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", family=SANS)


def _draw_table(ax, title, df: pd.DataFrame, columns: list[tuple[str, str, str]]):
    """Render a simple table.

    columns is a list of (df_col, header_label, fmt) — fmt is "dollars",
    "count", or "text" (truncated to 36 chars).
    """
    ax.axis("off")
    ax.text(0.0, 1.0, title, fontsize=10, fontweight="bold",
            color=INK, transform=ax.transAxes, ha="left", va="top")

    if df is None or df.empty:
        ax.text(0.0, 0.85, "No FY{} data".format(CURRENT_FY), fontsize=9,
                color=GRAY, transform=ax.transAxes, va="top")
        return

    n_rows = len(df)
    # Lay out rows below the title with a fixed row height so sparse
    # tables (small states with 1-2 recipients) sit at the top rather
    # than getting stretched across the panel.
    top = 0.86
    bottom = 0.02
    row_h = min(0.08, (top - bottom) / max(n_rows + 1, 2))
    n_cols = len(columns)
    # First-column is text-like (institution or IC); reserve the leftmost
    # ~58% of the row for it, with the remaining columns right-aligned.
    text_first = columns[0][2] in ("text", "ic")
    if text_first:
        text_right = 0.64
        # Right-edge x for each numeric column
        n_num = n_cols - 1
        col_w = (1.0 - text_right) / n_num if n_num > 0 else 0
        x_right_edges = [text_right + col_w * (i + 1) for i in range(n_num)]
        aligns = ["left"] + ["right"] * n_num
        x_positions = [0.0] + x_right_edges
        max_chars = 34
    else:
        col_w = 1.0 / n_cols
        x_positions = [col_w * (i + 0.5) for i in range(n_cols)]
        aligns = ["center"] * n_cols
        max_chars = 38

    # Header
    y = top
    for i, (_, header, _) in enumerate(columns):
        ax.text(x_positions[i], y, header, fontsize=7.5, color=GRAY,
                transform=ax.transAxes, ha=aligns[i], va="top",
                fontweight="bold")
    # Separator
    ax.plot([0, 1], [y - row_h * 0.35, y - row_h * 0.35], color=LIGHT_GRAY,
            linewidth=0.6, transform=ax.transAxes)

    for r in range(n_rows):
        y = top - row_h * (r + 1)
        row = df.iloc[r]
        for i, (col, _, fmt) in enumerate(columns):
            val = row[col]
            if fmt == "dollars":
                s = fmt_dollars(val)
            elif fmt == "count":
                s = fmt_count(val)
            elif fmt == "ic":
                # IC code first, then a short trailing label
                code = str(val)
                long = NIH_IC_DISPLAY_NAMES.get(code, "")
                if long and long != code:
                    s = f"{code} — {long}"
                else:
                    s = code
                if len(s) > max_chars:
                    s = s[:max_chars - 1] + "…"
            else:
                s = smart_title(str(val))
                if len(s) > max_chars:
                    s = s[:max_chars - 1] + "…"
            ax.text(x_positions[i], y, s, fontsize=8.5, color=INK,
                    transform=ax.transAxes, ha=aligns[i], va="top")


def _draw_footer(fig):
    fig.text(0.5, 0.024,
             "Source: NIH RePORTER · Extramural project costs (intramural Z-coded "
             "records excluded). Comparisons are at the same point in the fiscal year.",
             ha="center", fontsize=7, color=GRAY, family=SANS)
    fig.text(0.5, 0.011,
             f"5-yr average covers FY{BASELINE_YEARS[0]}–FY{BASELINE_YEARS[-1]}. "
             "Tracking Science Spending · sciencespending.org",
             ha="center", fontsize=7, color=GRAY, style="italic", family=SANS)


def render_state_pdf(state_code: str, new_df: pd.DataFrame, all_df: pd.DataFrame,
                     out_path: Path):
    state_name = US_STATES.get(state_code, state_code)

    new_series = build_state_series(new_df, state_code)
    all_series = build_state_series(all_df, state_code)
    new_metrics = compute_metrics(new_series) if not new_series.empty else {}
    all_metrics = compute_metrics(all_series) if not all_series.empty else {}

    # Determine "as-of" date label from latest FY26 record
    cur_new = new_df[(new_df["state"] == state_code) & (new_df["fiscal_year"] == CURRENT_FY)]
    if not cur_new.empty:
        try:
            latest_iso = max(d for d in cur_new["date"].tolist() if d)
            latest_date = datetime.strptime(latest_iso, "%Y-%m-%d")
            latest_date_str = latest_date.strftime("%b %-d, %Y")
        except ValueError:
            latest_date_str = ""
    else:
        latest_date_str = ""

    recipients = top_recipients(
        all_df, state_code,
        latest_fy_day=all_metrics.get("latest_fy_day"), n=10,
    )
    districts = district_breakdown(
        all_df, state_code, latest_fy_day=all_metrics.get("latest_fy_day"),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_path) as pdf:
        # ---------- Page 1 ----------
        fig = plt.figure(figsize=(8.5, 11), constrained_layout=False)
        gs = GridSpec(
            nrows=6, ncols=2,
            figure=fig,
            left=0.07, right=0.93, top=0.97, bottom=0.05,
            hspace=0.45, wspace=0.20,
            height_ratios=[0.55, 0.75, 1.15, 1.45, 1.45, 2.0],
        )
        # Row 0 — slim hero
        ax_hero = fig.add_subplot(gs[0, :])
        _draw_hero(ax_hero, state_code, state_name, latest_date_str)

        # Row 1 — site-style callout: state deviation + definition
        ax_take = fig.add_subplot(gs[1, :])
        _draw_takeaway(
            ax_take, state_name, latest_date_str,
            state_new_pct=new_metrics.get("vs_mean_pct"),
            state_all_pct=all_metrics.get("vs_mean_pct"),
        )

        # Row 2 — two site-style summary tables, one per dataset
        ax_sum_new = fig.add_subplot(gs[2, 0])
        _draw_summary_table(ax_sum_new, "New Awards (Types 1+2)",
                            new_metrics, latest_date_str)
        ax_sum_all = fig.add_subplot(gs[2, 1])
        _draw_summary_table(ax_sum_all, "All Awards (incl. continuations)",
                            all_metrics, latest_date_str)

        # Row 3 — dollar charts (unit shown in title since y-label removed)
        ax_dn = fig.add_subplot(gs[3, 0])
        _draw_series_chart(ax_dn, new_series, "New award dollars ($M)",
                           y_col="cumulative_dollars", y_scale=1e6)
        ax_da = fig.add_subplot(gs[3, 1])
        _draw_series_chart(ax_da, all_series, "All award dollars ($M)",
                           y_col="cumulative_dollars", y_scale=1e6,
                           show_legend=False)

        # Row 4 — count charts
        ax_cn = fig.add_subplot(gs[4, 0])
        _draw_series_chart(ax_cn, new_series, "New award count",
                           y_col="cumulative_count", y_scale=1,
                           show_legend=False)
        ax_ca = fig.add_subplot(gs[4, 1])
        _draw_series_chart(ax_ca, all_series, "All award count",
                           y_col="cumulative_count", y_scale=1,
                           show_legend=False)

        # Row 5 — top recipients (full width)
        ax_recip = fig.add_subplot(gs[5, :])
        _draw_recipients_table(
            ax_recip, f"Top recipients — FY{CURRENT_FY} (all awards)", recipients,
        )

        _draw_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ---------- Page 2: districts (if more than 1) ----------
        if len(districts) > 1:
            fig = plt.figure(figsize=(8.5, 11))
            gs2 = GridSpec(
                nrows=2, ncols=1, figure=fig,
                left=0.07, right=0.93, top=0.96, bottom=0.06,
                hspace=0.1, height_ratios=[0.45, 5.0],
            )
            ax_head = fig.add_subplot(gs2[0, 0])
            ax_head.axis("off")
            ax_head.text(0.0, 0.72, f"{state_name.upper()}", fontsize=20,
                         fontweight="bold", color=NIH_BLUE,
                         transform=ax_head.transAxes, family=SERIF)
            ax_head.text(0.0, 0.34,
                         "NIH all-awards funding by congressional district",
                         fontsize=11, color=INK, transform=ax_head.transAxes,
                         family=SERIF, style="italic")
            if latest_date_str:
                ax_head.text(0.0, 0.05,
                             f"All comparisons are point-in-time through "
                             f"fy_day {all_metrics.get('latest_fy_day','?')} "
                             f"(equivalent to {latest_date_str} in FY{CURRENT_FY}). "
                             f"5-yr avg covers FY{BASELINE_YEARS[0]}–FY{BASELINE_YEARS[-1]}.",
                             fontsize=8.5, color=GRAY,
                             transform=ax_head.transAxes, family=SANS)

            ax_d = fig.add_subplot(gs2[1, 0])
            disp = districts.copy()
            disp["vs_avg_pct_d"] = np.where(
                disp["dollars_mean"] > 0,
                (disp["dollars_cur"] - disp["dollars_mean"]) / disp["dollars_mean"] * 100,
                np.nan,
            )
            disp["vs_avg_pct_c"] = np.where(
                disp["count_mean"] > 0,
                (disp["count_cur"] - disp["count_mean"]) / disp["count_mean"] * 100,
                np.nan,
            )
            cols = [
                ("cong_dist", "DISTRICT", "text"),
                ("dollars_cur", f"$ FY{CURRENT_FY}", "dollars"),
                ("dollars_mean", "5-YR AVG $", "dollars"),
                ("vs_avg_pct_d", "VS AVG", "pct"),
                ("count_cur", f"# AWARDS FY{CURRENT_FY}", "count"),
                ("count_mean", "5-YR AVG #", "count"),
                ("vs_avg_pct_c", "VS AVG", "pct"),
            ]
            _draw_district_table(ax_d, disp, cols)
            _draw_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)


def _draw_recipients_table(ax, title: str, df: pd.DataFrame):
    """Top recipients spanning the full page width.

    Columns: INSTITUTION (wide left) | $ FY26 | 5-YR AVG $ | # FY26 | 5-YR AVG #

    Percent-diff columns are intentionally omitted to keep the table
    readable; the reader can eyeball the deviation.
    """
    ax.axis("off")
    ax.text(0.0, 1.00, title, fontsize=11, fontweight="bold", color=INK,
            transform=ax.transAxes, ha="left", va="top", family=SANS)
    if df is None or df.empty:
        ax.text(0.0, 0.80, f"No FY{CURRENT_FY} data", fontsize=9, color=GRAY,
                transform=ax.transAxes, va="top", family=SANS)
        return

    header_y = 0.86
    sep_y = 0.78
    first_row_y = 0.70

    n_rows = len(df)
    avail = first_row_y - 0.04
    row_h = min(0.07, avail / max(n_rows, 1))

    # Right-edge x positions for the four numeric columns.
    # Gaps between columns must accommodate the widest header text:
    # "5-YR AVG $" and "5-YR AVG #" are ~10 characters each.
    col_dollars_x = 0.62
    col_dollars_avg_x = 0.78
    col_count_x = 0.89
    col_count_avg_x = 1.00

    headers = [
        (col_dollars_x,     f"$ FY{CURRENT_FY}"),
        (col_dollars_avg_x, "5-YR AVG $"),
        (col_count_x,       f"# FY{CURRENT_FY}"),
        (col_count_avg_x,   "5-YR AVG #"),
    ]
    ax.text(0.0, header_y, "INSTITUTION", fontsize=7.5, color=GRAY,
            transform=ax.transAxes, ha="left", va="top",
            fontweight="bold", family=SANS)
    for x, label in headers:
        ax.text(x, header_y, label, fontsize=7.5, color=GRAY,
                transform=ax.transAxes, ha="right", va="top",
                fontweight="bold", family=SANS)
    ax.plot([0, 1], [sep_y, sep_y], color=LIGHT_GRAY, linewidth=0.6,
            transform=ax.transAxes)

    for r in range(n_rows):
        y = first_row_y - row_h * r
        row = df.iloc[r]
        raw_name = str(row["org_name"])
        name = smart_title(raw_name)
        # Truncate to leave breathing room before the dollar column
        if len(name) > 48:
            name = name[:46] + "…"
        ax.text(0.0, y, name, fontsize=9.5, color=INK,
                transform=ax.transAxes, ha="left", va="top", family=SANS)
        ax.text(col_dollars_x, y, fmt_dollars(row["dollars_cur"]),
                fontsize=9.5, color=INK, transform=ax.transAxes,
                ha="right", va="top", fontweight="bold", family=SANS)
        ax.text(col_dollars_avg_x, y, fmt_dollars(row["dollars_mean"]),
                fontsize=9.5, color=INK, transform=ax.transAxes,
                ha="right", va="top", family=SANS)
        ax.text(col_count_x, y, fmt_count(row["count_cur"]),
                fontsize=9.5, color=INK, transform=ax.transAxes,
                ha="right", va="top", fontweight="bold", family=SANS)
        ax.text(col_count_avg_x, y, fmt_count(row["count_mean"]),
                fontsize=9.5, color=INK, transform=ax.transAxes,
                ha="right", va="top", family=SANS)


def _draw_district_table(ax, df: pd.DataFrame, columns):
    ax.axis("off")
    n_rows = len(df)
    if n_rows == 0:
        ax.text(0.0, 0.95, "No district data available.",
                fontsize=10, color=GRAY, transform=ax.transAxes, family=SANS)
        return

    # Explicit header / separator / first-row spacing so the line
    # doesn't run into the header text. All in axes coords.
    header_y = 0.985
    sep_y = 0.95
    first_row_y = 0.91
    # Each row uses fixed height; pack densely for tall states
    n_cols = len(columns)
    avail = first_row_y - 0.02
    row_h = min(0.030, avail / max(n_rows, 1))

    # Column 0 narrower (district code), others equal
    first_w = 0.14
    rest = (1.0 - first_w) / (n_cols - 1)
    # Right-edge x for each numeric column
    x_right = [first_w + rest * (i + 1) - 0.005 for i in range(n_cols - 1)]

    # Header
    ax.text(0.0, header_y, columns[0][1], fontsize=7.5, fontweight="bold",
            color=GRAY, transform=ax.transAxes, ha="left", va="top",
            family=SANS)
    for i in range(1, n_cols):
        ax.text(x_right[i - 1], header_y, columns[i][1], fontsize=7.5,
                fontweight="bold", color=GRAY, transform=ax.transAxes,
                ha="right", va="top", family=SANS)
    ax.plot([0, 1], [sep_y, sep_y], color=LIGHT_GRAY, linewidth=0.6,
            transform=ax.transAxes)

    # Body rows
    for r in range(n_rows):
        y = first_row_y - row_h * r
        row = df.iloc[r]
        # District column
        ax.text(0.0, y, str(row[columns[0][0]]), fontsize=8.5, color=INK,
                transform=ax.transAxes, ha="left", va="top", family=SANS)
        # Numeric columns
        for i in range(1, n_cols):
            col_name, _, fmt = columns[i]
            val = row[col_name]
            if fmt == "dollars":
                s = fmt_dollars(val)
            elif fmt == "count":
                s = fmt_count(val)
            elif fmt == "pct":
                s = "—" if pd.isna(val) else fmt_pct(float(val))
            else:
                s = str(val)
            color = INK
            if fmt == "pct" and not pd.isna(val):
                color = POSITIVE if float(val) >= 0 else NEGATIVE
            ax.text(x_right[i - 1], y, s, fontsize=8.5, color=color,
                    transform=ax.transAxes, ha="right", va="top", family=SANS)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main(state_filter: list[str] | None = None, limit: int | None = None):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_fonts()

    new_df, all_df = load_all_records()

    states = sorted(US_STATES.keys()) if not state_filter else state_filter
    if limit:
        states = states[:limit]

    print(f"\nRendering PDFs for {len(states)} states → {OUTPUT_DIR.relative_to(ROOT)}/")
    summary = []
    for code in states:
        out_path = OUTPUT_DIR / f"NIH_{code}.pdf"
        try:
            render_state_pdf(code, new_df, all_df, out_path)
            size_kb = out_path.stat().st_size / 1024
            summary.append((code, size_kb))
            print(f"  {code} ({US_STATES[code]}): {size_kb:.0f} KB")
        except Exception as exc:
            print(f"  {code}: FAILED — {exc}")
            raise

    print(f"\nDone. {len(summary)} PDFs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate per-state NIH funding PDFs")
    parser.add_argument("--state", nargs="+", default=None,
                        help="Two-letter state codes (default: all 50 + DC)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N states (for testing)")
    args = parser.parse_args()
    main(state_filter=args.state, limit=args.limit)
