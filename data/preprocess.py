"""
Preprocess SF-133 Excel files into analysis-ready CSVs.

Run this once after downloading new data:
    python3 data/preprocess.py

Produces three files in data/processed/:
    - obligation_series.csv
    - approp_summary.csv
    - yoy_comparison.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.parse import parse_all_files
from data.transform import (
    build_obligation_series,
    build_appropriations_summary,
    compute_yoy_comparison,
)

PROCESSED_DIR = Path(__file__).resolve().parent / "processed"


def preprocess():
    PROCESSED_DIR.mkdir(exist_ok=True)

    print("Parsing all SF-133 files...")
    start = time.time()
    raw = parse_all_files()
    print(f"  Parsed {len(raw)} raw rows in {time.time() - start:.1f}s")

    if raw.empty:
        print("No data parsed. Have you downloaded the files?")
        print("  python3 data/download.py")
        sys.exit(1)

    print("Building obligation series...")
    obligation_series = build_obligation_series(raw)
    obligation_series.to_csv(PROCESSED_DIR / "obligation_series.csv", index=False)
    print(f"  Wrote {len(obligation_series)} rows")

    print("Building appropriations summary...")
    approp_summary = build_appropriations_summary(raw)
    approp_summary.to_csv(PROCESSED_DIR / "approp_summary.csv", index=False)
    print(f"  Wrote {len(approp_summary)} rows")

    print("Computing year-over-year comparison...")
    yoy = compute_yoy_comparison(obligation_series)
    yoy.to_csv(PROCESSED_DIR / "yoy_comparison.csv", index=False)
    print(f"  Wrote {len(yoy)} rows")

    print(f"\nDone. Preprocessed files in {PROCESSED_DIR}/")


if __name__ == "__main__":
    preprocess()
