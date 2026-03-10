"""
Award-tracking charts: cumulative new-award counts and dollars over the
fiscal year, with prior-year envelope and multi-agency comparison.

Mirrors the structure of charts/spenddown.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import (
    AGENCIES,
    AWARDS_CONFIG,
    BAND_YEARS_EXCLUDE,
    CURRENT_FY,
    FY_MONTH_LABELS,
    HIGHLIGHT_YEARS,
)

# Reuse the editorial style from spenddown
PRIOR_RANGE_COLOR = "rgba(170, 185, 210, 0.18)"
HIGHLIGHT_COLORS = {2025: "#7b8a9d"}
_FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
_TITLE_FONT = "Source Serif 4, Georgia, serif"
_TEXT_COLOR = "#1b2128"
_MUTED_COLOR = "#6b7580"
_GRID_COLOR = "rgba(0,0,0,0.05)"

# Approximate fy_day for each month label on the x-axis
_FY_MONTH_DAYS = {
    1: 15, 2: 46, 3: 76, 4: 107, 5: 135, 6: 166,
    7: 196, 8: 227, 9: 258, 10: 288, 11: 319, 12: 350,
}


def _fy_day_ticks():
    """Return tick positions (fy_day) and labels (month names) for x-axis."""
    tick_days = [_FY_MONTH_DAYS[m] for m in range(1, 13)]
    tick_labels = [FY_MONTH_LABELS[m] for m in range(1, 13)]
    return tick_days, tick_labels


def _build_envelope(
    series: pd.DataFrame,
    agency_key: str,
    y_col: str,
) -> tuple | None:
    """Compute min/max/median envelope from band-eligible fiscal years."""
    agency_data = series[series["agency"] == agency_key]
    fiscal_years = sorted(agency_data["fiscal_year"].unique())
    band_fys = [fy for fy in fiscal_years if fy not in BAND_YEARS_EXCLUDE]
    if not band_fys:
        return None

    # Build a lookup: {fy: {fy_day: value}}
    fy_lookup = {}
    for fy in band_fys:
        fy_data = agency_data[agency_data["fiscal_year"] == fy].sort_values("fy_day")
        fy_lookup[fy] = dict(zip(fy_data["fy_day"], fy_data[y_col]))

    # Sample at regular intervals (every 7 days, or at whatever days exist)
    all_days = sorted(set(
        d for mapping in fy_lookup.values() for d in mapping
    ))
    if not all_days:
        return None

    sample_days = list(range(1, max(all_days) + 1, 7))
    if sample_days[-1] != max(all_days):
        sample_days.append(max(all_days))

    min_vals, max_vals, med_vals = [], [], []
    valid_days = []

    for day in sample_days:
        vals = []
        for fy in band_fys:
            mapping = fy_lookup[fy]
            # Find the closest day <= this day
            closest = None
            for d in sorted(mapping):
                if d <= day:
                    closest = d
            if closest is not None:
                vals.append(mapping[closest])
        if vals:
            min_vals.append(min(vals))
            max_vals.append(max(vals))
            med_vals.append(float(np.median(vals)))
            valid_days.append(day)

    return valid_days, min_vals, max_vals, med_vals, band_fys


def plotly_awards_cumulative(
    series: pd.DataFrame,
    agency_key: str,
    show_dollars: bool = False,
    compact: bool = False,
) -> go.Figure:
    """Cumulative award count (or dollar) chart for one agency."""
    agency_cfg = AGENCIES[agency_key]
    awards_cfg = AWARDS_CONFIG[agency_key]
    agency_data = series[series["agency"] == agency_key].copy()

    if agency_data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data available", showarrow=False)
        return fig

    y_col = "cumulative_dollars" if show_dollars else "cumulative_count"
    y_suffix = "" if show_dollars else ""
    y_prefix = "$" if show_dollars else ""
    is_dollars = show_dollars

    fig = go.Figure()
    fiscal_years = sorted(agency_data["fiscal_year"].unique())
    tick_days, tick_labels = _fy_day_ticks()

    # Prior-year envelope
    envelope = _build_envelope(series, agency_key, y_col)
    if envelope:
        days, min_v, max_v, med_v, band_fys = envelope
        if is_dollars:
            min_v = [v / 1e6 for v in min_v]
            max_v = [v / 1e6 for v in max_v]
            med_v = [v / 1e6 for v in med_v]
        band_label = (
            f"FY{min(band_fys)}\u2013{max(band_fys)} range"
            if len(band_fys) > 1
            else f"FY{band_fys[0]}"
        )
        fig.add_trace(go.Scatter(
            x=days + list(reversed(days)),
            y=max_v + list(reversed(min_v)),
            fill="toself",
            fillcolor=PRIOR_RANGE_COLOR,
            line=dict(width=0),
            showlegend=True,
            name=band_label,
            hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=days, y=med_v,
            mode="lines",
            line=dict(color="rgba(110, 125, 150, 0.5)", width=1.5, dash="dot"),
            name=f"FY{min(band_fys)}\u2013{max(band_fys)} median",
            hovertemplate="%{y:,.0f}" + ("<extra>Median</extra>"),
        ))

    # Highlighted prior years
    for fy in sorted(HIGHLIGHT_YEARS):
        if fy == CURRENT_FY or fy not in fiscal_years:
            continue
        fy_data = agency_data[agency_data["fiscal_year"] == fy].sort_values("fy_day")
        if fy_data.empty:
            continue
        y_vals = fy_data[y_col].values
        if is_dollars:
            y_vals = y_vals / 1e6
        color = HIGHLIGHT_COLORS.get(fy, "#8d9aaa")
        fig.add_trace(go.Scatter(
            x=fy_data["fy_day"].tolist(),
            y=list(y_vals),
            mode="lines",
            name=f"FY{fy}",
            line=dict(color=color, width=1.8),
            hovertemplate=f"FY{fy}: " + "%{y:,.0f}<extra></extra>",
        ))

    # Current FY
    if CURRENT_FY in fiscal_years:
        fy_data = agency_data[agency_data["fiscal_year"] == CURRENT_FY].sort_values("fy_day")
        if not fy_data.empty:
            y_vals = fy_data[y_col].values
            if is_dollars:
                y_vals = y_vals / 1e6
            fig.add_trace(go.Scatter(
                x=fy_data["fy_day"].tolist(),
                y=list(y_vals),
                mode="lines+markers",
                name=f"FY{CURRENT_FY}",
                line=dict(color=agency_cfg["color"], width=3.5),
                marker=dict(size=7, color=agency_cfg["color"]),
                hovertemplate=f"FY{CURRENT_FY}: " + "%{y:,.0f}<extra></extra>",
            ))

    metric_label = awards_cfg["metric_label"]
    title_text = f"{agency_cfg['display_name']}: {metric_label}"
    subtitle = f"Source: {awards_cfg['source'].replace('_', ' ').title()}"

    height = 340 if compact else 500
    fig.update_layout(
        title=dict(
            text=(
                f"<b>{title_text}</b><br>"
                f"<span style='font-size:11px;color:{_MUTED_COLOR}'>{subtitle}</span>"
            ) if not compact else title_text,
            font=dict(family=_TITLE_FONT, size=13 if compact else 16, color=_TEXT_COLOR),
            x=0 if compact else 0.01,
        ),
        xaxis=dict(
            tickvals=tick_days,
            ticktext=tick_labels,
            range=[0, 370],
            gridcolor=_GRID_COLOR,
            zeroline=False,
            title=None,
            tickfont=dict(family=_FONT_FAMILY, size=11, color=_MUTED_COLOR),
        ),
        yaxis=dict(
            title=None,
            ticksuffix="M" if is_dollars else "",
            tickprefix="$" if is_dollars else "",
            gridcolor=_GRID_COLOR,
            zeroline=False,
            rangemode="tozero",
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
        margin=dict(l=55, r=16, t=65 if not compact else 44, b=65 if compact else 85),
    )

    return fig


def plotly_awards_multi(
    series: pd.DataFrame,
    fiscal_year: int = CURRENT_FY,
) -> go.Figure:
    """
    Multi-agency comparison: current FY award count as % of historical
    median at the same point in the fiscal year.
    """
    fig = go.Figure()
    tick_days, tick_labels = _fy_day_ticks()

    # 100% reference line
    fig.add_hline(
        y=100, line_dash="dot", line_color="rgba(0,0,0,0.2)", line_width=1,
        annotation_text="Historical median pace",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color="rgba(0,0,0,0.35)",
        annotation_font_family=_FONT_FAMILY,
    )

    for agency_key in AWARDS_CONFIG:
        cfg = AGENCIES[agency_key]
        awards_cfg = AWARDS_CONFIG[agency_key]
        agency_data = series[series["agency"] == agency_key]

        # Use count for nih_reporter/nsf_awards, dollars for usaspending
        y_col = (
            "cumulative_dollars"
            if awards_cfg["source"] == "usaspending"
            else "cumulative_count"
        )

        current = agency_data[agency_data["fiscal_year"] == fiscal_year].sort_values("fy_day")
        if current.empty:
            continue

        # Build median lookup from band-eligible years
        band_fys = [
            fy for fy in agency_data["fiscal_year"].unique()
            if fy not in BAND_YEARS_EXCLUDE and fy != fiscal_year
        ]
        if not band_fys:
            continue

        # For each day in current FY, compute median of prior years at same day
        x_vals = []
        y_vals = []

        for _, row in current.iterrows():
            day = row["fy_day"]
            curr_val = row[y_col]
            if curr_val == 0:
                continue

            prior_vals = []
            for fy in band_fys:
                fy_data = agency_data[
                    (agency_data["fiscal_year"] == fy)
                    & (agency_data["fy_day"] <= day)
                ]
                if not fy_data.empty:
                    prior_vals.append(fy_data[y_col].max())

            if prior_vals:
                median_val = float(np.median(prior_vals))
                if median_val > 0:
                    x_vals.append(day)
                    y_vals.append(curr_val / median_val * 100)

        if not x_vals:
            continue

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines+markers",
            name=cfg["display_name"],
            line=dict(color=cfg["color"], width=2.8),
            marker=dict(size=6, color=cfg["color"]),
            hovertemplate=(
                f"{cfg['display_name']}: "
                + "%{y:.0f}% of median pace<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text=(
                f"<b>FY{fiscal_year} Award-Making Pace vs. Historical Median</b><br>"
                f"<span style='font-size:11px;color:{_MUTED_COLOR}'>"
                "NIH/NSF: new award counts; DOE/NASA/USDA: grant obligation dollars"
                "</span>"
            ),
            font=dict(family=_TITLE_FONT, size=16, color=_TEXT_COLOR),
            x=0.01,
        ),
        xaxis=dict(
            tickvals=tick_days,
            ticktext=tick_labels,
            range=[0, 370],
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
        margin=dict(l=55, r=16, t=70, b=85),
    )

    return fig
