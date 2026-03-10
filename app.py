"""
Multi-Agency Science R&D Spend-Down Tracker

A Streamlit dashboard showing cumulative obligation patterns for major
US science agencies using OMB SF-133 budget execution data.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import AGENCIES, CURRENT_FY, FY_MONTH_LABELS
from data.transform import get_latest_period
from charts.spenddown import plotly_spenddown, plotly_multi_agency
from charts.summary import compute_agency_summary, format_dollars, format_pct

PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"

st.set_page_config(
    page_title="Science R&D Spend-Down Tracker",
    page_icon="$",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Custom CSS ---
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
    /* ── Global ── */
    html, body, .main, .block-container,
    .stApp, [data-testid="stAppViewContainer"] {
        background-color: #f8f9fb !important;
    }
    .main .block-container {
        padding-top: 2.5rem;
        padding-bottom: 2rem;
        max-width: 1180px;
    }

    /* ── Typography ── */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: #1b2128;
    }
    h1, h2, h3, h4, .tracker-header h1, .section-heading {
        font-family: 'Source Serif 4', 'Georgia', serif !important;
        color: #1b2128;
    }

    /* ── Header ── */
    .tracker-header {
        padding-bottom: 1.8rem;
        margin-bottom: 2rem;
        border-bottom: none;
    }
    .tracker-header h1 {
        font-size: 2.4rem;
        font-weight: 700;
        color: #1b2128;
        margin-bottom: 0.5rem;
        line-height: 1.15;
        letter-spacing: -0.01em;
    }
    .tracker-header .subtitle {
        font-family: 'Inter', sans-serif;
        font-size: 1rem;
        color: #4f5a68;
        margin: 0;
        line-height: 1.55;
        max-width: 680px;
    }
    .tracker-header .rule {
        width: 60px;
        height: 3px;
        background: #1f77b4;
        border: none;
        margin: 1.2rem 0 0 0;
        border-radius: 2px;
    }

    /* ── Metric cards ── */
    .metric-card {
        background: #ffffff;
        border: 1px solid #d5dae2;
        border-radius: 10px;
        padding: 1.1rem 1rem;
        text-align: center;
        transition: border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #a8b2bf;
    }
    .metric-card .label {
        font-family: 'Inter', sans-serif;
        font-size: 0.68rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #6b7580;
        margin-bottom: 0.45rem;
    }
    .metric-card .value {
        font-family: 'Source Serif 4', Georgia, serif;
        font-size: 1.35rem;
        font-weight: 600;
        color: #1b2128;
        line-height: 1.25;
    }
    .metric-card .delta {
        font-family: 'Inter', sans-serif;
        font-size: 0.78rem;
        font-weight: 500;
        margin-top: 0.25rem;
    }
    .metric-card .delta.negative { color: #b83d3d; }
    .metric-card .delta.positive { color: #2e7d4f; }

    /* ── Section headings ── */
    .section-heading {
        font-family: 'Source Serif 4', Georgia, serif !important;
        font-size: 1.35rem !important;
        font-weight: 600 !important;
        color: #1b2128 !important;
        margin-top: 2.2rem !important;
        margin-bottom: 1rem !important;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e0e4ea;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #d5dae2;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        font-family: 'Inter', sans-serif;
        padding: 0.7rem 1.6rem;
        font-size: 0.88rem;
        font-weight: 500;
        color: #6b7580;
        border-bottom: 2px solid transparent;
        transition: color 0.15s ease, border-color 0.15s ease;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #1b2128;
        font-weight: 600;
        border-bottom-color: #1b2128;
    }

    /* ── Chart containers ── */
    [data-testid="stPlotlyChart"] {
        background: #ffffff;
        border: 1px solid #e0e4ea;
        border-radius: 10px;
        padding: 0.6rem;
        overflow: hidden;
    }

    /* ── Selectbox ── */

    /* ── Toggle ── */
    .stToggle label span {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        color: #4f5a68;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        font-weight: 500;
        color: #4f5a68;
    }

    /* ── Data tables ── */
    .stDataFrame {
        border: 1px solid #e0e4ea;
        border-radius: 10px;
        overflow: hidden;
    }

    /* ── Footer ── */
    .source-footer {
        text-align: center;
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        color: #8b95a3;
        border-top: 1px solid #e0e4ea;
        padding-top: 1.5rem;
        margin-top: 3rem;
        line-height: 1.7;
    }
    .source-footer a {
        color: #5a6878;
        text-decoration: underline;
        text-decoration-color: #c0c8d2;
        text-underline-offset: 2px;
        transition: color 0.15s ease;
    }
    .source-footer a:hover { color: #1b2128; }

    /* ── Hide Streamlit chrome ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Loading data...")
def load_data():
    if not (PROCESSED_DIR / "obligation_series.csv").exists():
        st.error(
            "Preprocessed data not found. Run the preprocessing step first:\n\n"
            "```bash\npython3 data/preprocess.py\n```"
        )
        return None, None, None
    obligation_series = pd.read_csv(PROCESSED_DIR / "obligation_series.csv")
    approp_summary = pd.read_csv(PROCESSED_DIR / "approp_summary.csv")
    yoy = pd.read_csv(PROCESSED_DIR / "yoy_comparison.csv")
    return obligation_series, approp_summary, yoy


def render_metric_card(label: str, value: str, delta: str = None, delta_dir: str = None):
    delta_html = ""
    if delta and delta != "N/A":
        css_class = "negative" if delta_dir == "negative" else "positive"
        delta_html = f'<div class="delta {css_class}">{delta}</div>'
    st.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def render_agency_detail(obligation_series, approp_summary, agency_key):
    """Render the detail view for a single agency."""
    summary = compute_agency_summary(obligation_series, approp_summary, agency_key)

    if "error" in summary:
        st.warning(summary["error"])
        return

    # Metric cards row
    cols = st.columns(5, gap="medium")
    with cols[0]:
        render_metric_card(
            f"FY{CURRENT_FY} Appropriations",
            format_dollars(summary["appropriations"]),
        )
    with cols[1]:
        render_metric_card(
            f"Obligated thru {summary['latest_period']}",
            format_dollars(summary["obligations_to_date"]),
        )
    with cols[2]:
        pct = summary["pct_obligated"]
        render_metric_card(
            "% of Approps Obligated",
            f"{pct:.1f}%" if pct is not None else "N/A",
        )
    with cols[3]:
        yoy_diff = summary.get("yoy_diff")
        yoy_rel = summary.get("yoy_rel")
        yoy_dir = "negative" if (yoy_diff or 0) < 0 else "positive"
        if yoy_diff is not None and yoy_rel is not None:
            val_str = f"{yoy_diff:+.1f}pp ({yoy_rel:+.1f}%)"
        else:
            val_str = "N/A"
        render_metric_card(
            f"vs. FY{CURRENT_FY - 1} Same Period",
            val_str,
            delta_dir=yoy_dir,
        )
    with cols[4]:
        median_diff = summary.get("median_diff")
        median_rel = summary.get("median_rel")
        if median_diff is not None and median_rel is not None:
            diff_dir = "negative" if median_diff < 0 else "positive"
            val_str = f"{median_diff:+.1f}pp ({median_rel:+.1f}%)"
            render_metric_card(
                "vs. FY2016–2024 Median",
                val_str,
                delta_dir=diff_dir,
            )
        else:
            render_metric_card("vs. FY2016–2024 Median", "N/A")

    st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)

    # Chart with toggle
    col_chart, col_toggle = st.columns([6, 1])
    with col_toggle:
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        show_dollars = st.toggle("Show $", value=False, key=f"toggle_{agency_key}")

    fig = plotly_spenddown(obligation_series, agency_key, show_pct=not show_dollars)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Export row
    with st.expander("Export data & charts"):
        col_png, col_csv = st.columns(2)
        with col_png:
            from charts.spenddown import matplotlib_spenddown
            import matplotlib
            matplotlib.use("Agg")
            mpl_fig = matplotlib_spenddown(obligation_series, agency_key, show_pct=not show_dollars)
            buf = io.BytesIO()
            mpl_fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            buf.seek(0)
            st.download_button(
                "Download chart (PNG)",
                buf,
                file_name=f"{agency_key}_spenddown.png",
                mime="image/png",
            )
            import matplotlib.pyplot as plt
            plt.close(mpl_fig)
        with col_csv:
            agency_data = obligation_series[
                obligation_series["agency"] == agency_key
            ].sort_values(["fiscal_year", "period_month"])
            csv_buf = io.StringIO()
            agency_data.to_csv(csv_buf, index=False)
            st.download_button(
                "Download data (CSV)",
                csv_buf.getvalue(),
                file_name=f"{agency_key}_obligations.csv",
                mime="text/csv",
            )


def main():
    # Header
    st.markdown("""
    <div class="tracker-header">
        <h1>Science Agency Spend-Down Tracker</h1>
        <p class="subtitle">Tracking how quickly federal science agencies obligate their
        appropriated funds each fiscal year, using OMB SF-133 budget execution data.</p>
        <hr class="rule">
    </div>
    """, unsafe_allow_html=True)

    obligation_series, approp_summary, yoy = load_data()

    if obligation_series is None or obligation_series.empty:
        st.error(
            "No data found. Download SF-133 files first:\n\n"
            "```bash\npython data/download.py\n```"
        )
        return

    available_agencies = [k for k in AGENCIES if k in obligation_series["agency"].unique()]
    available_years = sorted(obligation_series["fiscal_year"].unique())

    tab_overview, tab_agency, tab_data = st.tabs([
        "Overview", "Agency Detail", "Data"
    ])

    # === Tab 1: Overview — all agencies on one chart + small multiples ===
    with tab_overview:
        fig_compare = plotly_multi_agency(obligation_series, fiscal_year=CURRENT_FY)
        st.plotly_chart(fig_compare, use_container_width=True, config={"displayModeBar": False})

        st.markdown(f'<div class="section-heading">FY{CURRENT_FY} vs. FY2016–2024</div>', unsafe_allow_html=True)
        ncols = min(len(available_agencies), 3)
        rows_needed = (len(available_agencies) + ncols - 1) // ncols
        for row_idx in range(rows_needed):
            cols = st.columns(ncols, gap="medium")
            for col_idx in range(ncols):
                agency_idx = row_idx * ncols + col_idx
                if agency_idx >= len(available_agencies):
                    break
                ak = available_agencies[agency_idx]
                with cols[col_idx]:
                    mini_fig = plotly_spenddown(obligation_series, ak, show_pct=True, compact=True)
                    st.plotly_chart(mini_fig, use_container_width=True, config={"displayModeBar": False})

    # === Tab 2: Agency Detail ===
    with tab_agency:
        st.markdown('<div class="section-heading" style="margin-top: 0.5rem;">Select Agency</div>', unsafe_allow_html=True)
        col_select, _ = st.columns([2, 3])
        with col_select:
            agency_key = st.selectbox(
                "Select an agency to view detailed spend-down data",
                available_agencies,
                format_func=lambda k: AGENCIES[k]["display_name"],
                label_visibility="collapsed",
            )
        st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
        render_agency_detail(obligation_series, approp_summary, agency_key)

    # === Tab 3: Data ===
    with tab_data:
        st.markdown('<div class="section-heading">Appropriations &amp; Obligations Summary</div>', unsafe_allow_html=True)
        if approp_summary is not None and not approp_summary.empty:
            display = approp_summary.copy()
            display["Agency"] = display["agency"].map(
                lambda k: AGENCIES.get(k, {}).get("display_name", k)
            )
            display["FY"] = display["fiscal_year"]
            dollar_cols = [
                "approp_disc_raw", "approp_mand_raw", "approp_disc_net",
                "budget_authority", "obligations_total", "outlays_net",
            ]
            rename_map = {
                "approp_disc_raw": "Disc. Approp",
                "approp_mand_raw": "Mand. Approp",
                "approp_disc_net": "Net Disc. (after CR)",
                "budget_authority": "Budget Authority",
                "obligations_total": "Total Obligations",
                "outlays_net": "Net Outlays",
            }
            for col in dollar_cols:
                if col in display.columns:
                    display[rename_map.get(col, col)] = display[col].apply(
                        lambda x: format_dollars(x) if pd.notna(x) else "—"
                    )
            show_cols = ["Agency", "FY"] + [rename_map.get(c, c) for c in dollar_cols if c in display.columns]
            st.dataframe(
                display[show_cols].sort_values(["Agency", "FY"], ascending=[True, False]),
                use_container_width=True,
                hide_index=True,
                height=400,
            )

        st.markdown(f'<div class="section-heading">FY{CURRENT_FY} vs. FY{CURRENT_FY - 1} Spend-Down Comparison</div>', unsafe_allow_html=True)
        if yoy is not None and not yoy.empty:
            yoy_display = yoy.copy()
            yoy_display["Agency"] = yoy_display["display_name"]
            yoy_display["Period"] = yoy_display["period_label"]
            for col in ["current_pct", "prior_year_pct", "yoy_diff", "median_prior_pct"]:
                if col in yoy_display.columns:
                    yoy_display[col] = yoy_display[col].apply(
                        lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
                    )
            st.dataframe(
                yoy_display[["Agency", "Period", "current_pct",
                             "prior_year_pct", "yoy_diff",
                             "median_prior_pct"]].rename(columns={
                    "current_pct": f"FY{CURRENT_FY} % Obligated",
                    "prior_year_pct": f"FY{CURRENT_FY-1} % Obligated",
                    "yoy_diff": "YoY Diff (pp)",
                    "median_prior_pct": "FY16–24 Median %",
                }),
                use_container_width=True,
                hide_index=True,
            )

    # Footer
    st.markdown("""
    <div class="source-footer">
        Data from <a href="https://portal.max.gov/portal/document/SF133/Budget/FACTS%20II%20-%20SF%20133%20Report%20on%20Budget%20Execution%20and%20Budgetary%20Resources.html"
        target="_blank">OMB SF-133 Reports on Budget Execution and Budgetary Resources</a><br>
        Obligations: Line 2190 (total new obligations)&ensp;&middot;&ensp;Appropriations: Line 1100 (disc.) + Line 1200 (mand.)
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
