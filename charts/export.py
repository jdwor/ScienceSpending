"""
Static chart export for sharing (PNG/SVG).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import AGENCIES
from charts.spenddown import matplotlib_spenddown

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def export_all_agencies(
    obligation_series: pd.DataFrame,
    output_dir: Path | None = None,
    formats: list[str] | None = None,
) -> list[Path]:
    """
    Export spend-down charts for all agencies as static images.

    Returns list of exported file paths.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR
    if formats is None:
        formats = ["png", "svg"]

    output_dir.mkdir(parents=True, exist_ok=True)
    exported = []

    for agency_key in AGENCIES:
        for show_pct in [False, True]:
            suffix = "pct" if show_pct else "dollars"
            fig = matplotlib_spenddown(obligation_series, agency_key, show_pct=show_pct)

            for fmt in formats:
                filename = f"{agency_key}_spenddown_{suffix}.{fmt}"
                filepath = output_dir / filename
                fig.savefig(filepath, dpi=300, bbox_inches="tight")
                exported.append(filepath)

            fig.clf()
            import matplotlib.pyplot as plt
            plt.close(fig)

    return exported
