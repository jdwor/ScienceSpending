"""
Spend-down line charts: cumulative obligations over the fiscal year.

Produces both interactive (plotly) and static (matplotlib) versions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from config import (
    AGENCIES, CURRENT_FY, HIGHLIGHT_YEARS, BAND_YEARS_EXCLUDE, FY_MONTH_LABELS,
)

# Color palette
PRIOR_RANGE_COLOR = "rgba(170, 185, 210, 0.18)"
HIGHLIGHT_COLORS = {
    2025: "#7b8a9d",
}

# Shared layout defaults for a clean, editorial chart style
_FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
_TITLE_FONT = "Source Serif 4, Georgia, serif"
_TEXT_COLOR = "#1b2128"
_MUTED_COLOR = "#6b7580"
_GRID_COLOR = "rgba(0,0,0,0.05)"


def _fy_month_ticks():
    months = list(range(1, 13))
    labels = [FY_MONTH_LABELS[m] for m in months]
    return months, labels


def _prepend_oct_zero(x_vals, y_vals):
    """Prepend an Oct (month 1) point at 0 if the series doesn't already start there."""
    x_list = list(x_vals)
    y_list = list(y_vals)
    if not x_list or x_list[0] != 1:
        x_list.insert(0, 1)
        y_list.insert(0, 0.0)
    return x_list, y_list


def _build_prior_year_envelope(agency_data, fiscal_years, y_col, show_pct):
    """Compute min/max/median band from band-eligible fiscal years only."""
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    if not band_fys:
        return None

    all_months = list(range(1, 13))
    min_vals, max_vals, med_vals = [], [], []

    for m in all_months:
        vals = []
        for fy in band_fys:
            if m == 1:
                # Oct is always 0 (FY starts Oct 1, first report is Nov)
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
            min_vals.append(min(vals))
            max_vals.append(max(vals))
            med_vals.append(float(np.median(vals)))
        else:
            min_vals.append(None)
            max_vals.append(None)
            med_vals.append(None)

    return all_months, min_vals, max_vals, med_vals, band_fys


def _compute_median_lookup(agency_data, fiscal_years, y_col, show_pct):
    """Build a dict of {month: median_value} from band-eligible years."""
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    medians = {}
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
            medians[m] = float(np.median(vals))
    return medians


def plotly_spenddown(
    obligation_series: pd.DataFrame,
    agency_key: str,
    show_pct: bool = True,
    compact: bool = False,
) -> go.Figure:
    """Create an interactive plotly spend-down chart for one agency."""
    agency_cfg = AGENCIES[agency_key]
    agency_data = obligation_series[obligation_series["agency"] == agency_key].copy()

    if agency_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", showarrow=False)
        return fig

    y_col = "pct_obligated" if show_pct else "obligations"

    fig = go.Figure()
    fiscal_years = sorted(agency_data["fiscal_year"].unique())
    tick_vals, tick_labels = _fy_month_ticks()

    # Draw prior-year range as a shaded band (excludes BAND_YEARS_EXCLUDE)
    envelope = _build_prior_year_envelope(agency_data, fiscal_years, y_col, show_pct)
    if envelope:
        months, min_v, max_v, med_v, band_fys = envelope
        valid = [(m, lo, hi, md) for m, lo, hi, md in zip(months, min_v, max_v, med_v)
                 if lo is not None]
        if valid:
            vm, vlo, vhi, vmd = zip(*valid)
            band_label = (f"FY{min(band_fys)}–{max(band_fys)} range"
                          if len(band_fys) > 1 else f"FY{band_fys[0]}")
            fig.add_trace(go.Scatter(
                x=list(vm) + list(reversed(vm)),
                y=list(vhi) + list(reversed(vlo)),
                fill="toself",
                fillcolor=PRIOR_RANGE_COLOR,
                line=dict(width=0),
                showlegend=True,
                name=band_label,
                hoverinfo="skip",
            ))
            fig.add_trace(go.Scatter(
                x=list(vm), y=list(vmd),
                mode="lines",
                line=dict(color="rgba(110, 125, 150, 0.5)", width=1.5, dash="dot"),
                name=f"FY{min(band_fys)}–{max(band_fys)} median",
                hovertemplate="%{y:.1f}" + ("%" if show_pct else "B") + "<extra>Median</extra>",
            ))

    # Draw individual highlighted prior years (e.g. FY2025)
    for fy in sorted(HIGHLIGHT_YEARS):
        if fy == CURRENT_FY or fy not in fiscal_years:
            continue
        fy_data = agency_data[agency_data["fiscal_year"] == fy].sort_values("period_month")
        if fy_data.empty:
            continue
        y_vals = fy_data[y_col].values
        if not show_pct:
            y_vals = y_vals / 1e9
        x_vals, y_vals = _prepend_oct_zero(fy_data["period_month"].values, list(y_vals))
        color = HIGHLIGHT_COLORS.get(fy, "#8d9aaa")
        fig.add_trace(go.Scatter(
            x=x_vals, y=y_vals,
            mode="lines",
            name=f"FY{fy}",
            line=dict(color=color, width=1.8),
            hovertemplate=f"FY{fy}: " + "%{y:.1f}" + ("%" if show_pct else "B") + "<extra></extra>",
        ))

    # Draw current FY (bold, on top)
    if CURRENT_FY in fiscal_years:
        fy_data = agency_data[agency_data["fiscal_year"] == CURRENT_FY].sort_values("period_month")
        if not fy_data.empty:
            y_vals = fy_data[y_col].values
            if not show_pct:
                y_vals = y_vals / 1e9
            x_vals, y_vals = _prepend_oct_zero(fy_data["period_month"].values, list(y_vals))
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals,
                mode="lines+markers",
                name=f"FY{CURRENT_FY}",
                line=dict(color=agency_cfg["color"], width=3.5),
                marker=dict(size=7, color=agency_cfg["color"]),
                hovertemplate=(
                    f"FY{CURRENT_FY}: "
                    + "%{y:.1f}" + ("%" if show_pct else "B")
                    + "<extra></extra>"
                ),
            ))

    height = 340 if compact else 500
    fig.update_layout(
        title=dict(
            text=agency_cfg["display_name"],
            font=dict(family=_TITLE_FONT, size=13 if compact else 18, color=_TEXT_COLOR),
            x=0 if compact else 0.01,
        ),
        xaxis=dict(
            tickvals=tick_vals,
            ticktext=tick_labels,
            range=[0.5, 12.5],
            gridcolor=_GRID_COLOR,
            zeroline=False,
            title=None,
            tickfont=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        yaxis=dict(
            title=None,
            ticksuffix="%" if show_pct else "B",
            tickprefix="" if show_pct else "$",
            gridcolor=_GRID_COLOR,
            zeroline=False,
            rangemode="tozero",
            tick0=0,
            range=[-4 if show_pct else -0.5, None],
            tickfont=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.08 if compact else -0.13,
            xanchor="center",
            x=0.5,
            font=dict(family=_FONT_FAMILY, size=10, color=_MUTED_COLOR),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=_FONT_FAMILY, size=12)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=height,
        margin=dict(l=55, r=16, t=44 if compact else 52, b=65 if compact else 85),
    )

    return fig


def plotly_multi_agency(
    obligation_series: pd.DataFrame,
    fiscal_year: int = CURRENT_FY,
) -> go.Figure:
    """
    Multi-agency comparison for a single fiscal year.
    Y-axis = obligations as % of that agency's prior-year median at each month.
    100% means on pace with the median prior year; below means behind.
    """
    fig = go.Figure()
    tick_vals, tick_labels = _fy_month_ticks()

    fy_data = obligation_series[obligation_series["fiscal_year"] == fiscal_year]

    # Add 100% reference line
    fig.add_hline(
        y=100, line_dash="dot", line_color="rgba(0,0,0,0.2)", line_width=1,
        annotation_text="FY2016–2024 median pace",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color="rgba(0,0,0,0.35)",
        annotation_font_family=_FONT_FAMILY,
    )

    for agency_key in AGENCIES:
        cfg = AGENCIES[agency_key]
        agency_all = obligation_series[obligation_series["agency"] == agency_key]
        all_fys = sorted(agency_all["fiscal_year"].unique())
        agency_fy = fy_data[fy_data["agency"] == agency_key].sort_values("period_month")
        if agency_fy.empty:
            continue

        # Compute median spend-down rate (% of approp) at each month
        medians = _compute_median_lookup(agency_all, all_fys, "pct_obligated", show_pct=True)

        x_vals = [1]
        y_vals = [100.0]  # Oct is 0/0, define as 100% (on pace)
        for _, row in agency_fy.iterrows():
            m = row["period_month"]
            med = medians.get(m)
            curr_pct = row["pct_obligated"]
            if med and med > 0 and curr_pct is not None:
                pct_of_median = curr_pct / med * 100
            else:
                pct_of_median = None
            if pct_of_median is not None:
                x_vals.append(m)
                y_vals.append(pct_of_median)

        # Split into faded lead-in (Oct–Nov) and solid main segment (Nov onward)
        # to de-emphasize the artificial 100% starting point
        lead_x = [x for x in x_vals if x <= 2]
        lead_y = y_vals[:len(lead_x)]
        main_x = [x for x in x_vals if x >= 2]
        main_y = y_vals[len(lead_x) - 1:]  # overlap at Nov for continuity

        if len(lead_x) >= 2:
            fig.add_trace(go.Scatter(
                x=lead_x, y=lead_y,
                mode="lines",
                line=dict(color=cfg["color"], width=1.5, dash="dot"),
                opacity=0.4,
                showlegend=False,
                hoverinfo="skip",
            ))
        fig.add_trace(go.Scatter(
            x=main_x, y=main_y,
            mode="lines+markers",
            name=cfg["display_name"],
            line=dict(color=cfg["color"], width=2.8),
            marker=dict(size=6, color=cfg["color"]),
            hovertemplate=f"{cfg['display_name']}: " + "%{y:.0f}% of median pace<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text=f"FY{fiscal_year} Obligation Pace vs. FY2016–2024 Median",
            font=dict(family=_TITLE_FONT, size=18, color=_TEXT_COLOR),
            x=0.01,
        ),
        xaxis=dict(
            tickvals=tick_vals,
            ticktext=tick_labels,
            range=[0.5, 12.5],
            gridcolor=_GRID_COLOR,
            zeroline=False,
            tickfont=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        yaxis=dict(
            title=None,
            ticksuffix="%",
            gridcolor=_GRID_COLOR,
            zeroline=False,
            tickfont=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.13,
            xanchor="center",
            x=0.5,
            font=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        hovermode="x unified",
        hoverlabel=dict(font=dict(family=_FONT_FAMILY, size=12)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=500,
        margin=dict(l=55, r=16, t=52, b=85),
    )

    return fig


def matplotlib_spenddown(
    obligation_series: pd.DataFrame,
    agency_key: str,
    show_pct: bool = True,
) -> plt.Figure:
    """Publication-quality matplotlib spend-down chart for static export."""
    agency_cfg = AGENCIES[agency_key]
    agency_data = obligation_series[obligation_series["agency"] == agency_key].copy()

    fig, ax = plt.subplots(figsize=(10, 6))

    if agency_data.empty:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                transform=ax.transAxes, fontsize=14)
        return fig

    y_col = "pct_obligated" if show_pct else "obligations"
    fiscal_years = sorted(agency_data["fiscal_year"].unique())
    tick_vals, tick_labels = _fy_month_ticks()

    # Draw prior-year range band (excludes BAND_YEARS_EXCLUDE)
    envelope = _build_prior_year_envelope(agency_data, fiscal_years, y_col, show_pct)
    if envelope:
        months, min_v, max_v, med_v, band_fys = envelope
        valid = [(m, lo, hi, md) for m, lo, hi, md in zip(months, min_v, max_v, med_v)
                 if lo is not None]
        if valid:
            vm, vlo, vhi, vmd = zip(*valid)
            band_label = (f"FY{min(band_fys)}–{max(band_fys)} range"
                          if len(band_fys) > 1 else f"FY{band_fys[0]}")
            ax.fill_between(vm, vlo, vhi, alpha=0.15, color="#6b89a8", label=band_label)
            ax.plot(vm, vmd, color="#6b89a8", linewidth=1.2, linestyle=":",
                    alpha=0.6, label=f"FY{min(band_fys)}–{max(band_fys)} median")

    # Draw highlighted years (e.g. FY2025)
    for fy in sorted(HIGHLIGHT_YEARS):
        if fy == CURRENT_FY or fy not in fiscal_years:
            continue
        fy_data = agency_data[agency_data["fiscal_year"] == fy].sort_values("period_month")
        if fy_data.empty:
            continue
        y_vals = fy_data[y_col].values
        if not show_pct:
            y_vals = y_vals / 1e9
        x_vals, y_vals = _prepend_oct_zero(fy_data["period_month"].values, list(y_vals))
        ax.plot(x_vals, y_vals,
                color="#6b7b8d", linewidth=1.3, alpha=0.6, label=f"FY{fy}", zorder=5)

    # Draw current FY
    if CURRENT_FY in fiscal_years:
        fy_data = agency_data[agency_data["fiscal_year"] == CURRENT_FY].sort_values("period_month")
        if not fy_data.empty:
            y_vals = fy_data[y_col].values
            if not show_pct:
                y_vals = y_vals / 1e9
            x_vals, y_vals = _prepend_oct_zero(fy_data["period_month"].values, list(y_vals))
            ax.plot(x_vals, y_vals,
                    color=agency_cfg["color"], linewidth=3, marker="o",
                    markersize=5, label=f"FY{CURRENT_FY}", zorder=10)

    ax.set_xticks(tick_vals)
    ax.set_xticklabels(tick_labels, fontsize=10)
    ax.set_xlim(0.5, 12.5)

    if show_pct:
        ax.set_ylabel("% of Appropriations Obligated", fontsize=11, color="#333")
        ax.yaxis.set_major_formatter(mticker.PercentFormatter())
    else:
        ax.set_ylabel("Cumulative Obligations ($ Billions)", fontsize=11, color="#333")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"${x:,.1f}B"
        ))

    ax.set_title(f"{agency_cfg['display_name']}", fontsize=16, fontweight="bold",
                 color="#1a1a2e", pad=12)
    ax.legend(loc="upper left", fontsize=8, ncol=3, framealpha=0.9,
              edgecolor="none", facecolor="white")
    ax.grid(True, alpha=0.15, color="#000")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#ccc")
    ax.spines["bottom"].set_color("#ccc")
    ax.tick_params(colors="#555")

    fig.tight_layout()
    fig.text(0.99, 0.01, "Source: OMB SF-133 via portal.max.gov",
             ha="right", va="bottom", fontsize=7, color="#aaa")

    return fig
