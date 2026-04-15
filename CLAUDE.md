# Spending on Science

Static website tracking federal science spending via SF-133 obligation reports and new award data from NIH Reporter, NSF Awards, and USASpending APIs. The site is served from `docs/` as a GitHub Pages-style static site.

## Key Commands

```bash
# Check for new SF-133 data
python3 data/download.py --check

# Update new-awards data (auto-fetches if cache >24h old)
# IMPORTANT: Never use --agencies or --years flags — they overwrite full output CSVs
python3 -m awards.preprocess

# Update all-awards data (new + continuing; separate cache)
# Uses NIH Reporter (types 1+2+5) for NIH, USASpending for all others
python3 -m awards.preprocess_all

# Full obligations pipeline (download + parse + transform)
python3 data/download.py --years 2026 --force
python3 data/preprocess.py

# Build site JSON from processed CSVs
python3 build.py
```

## Project Structure

- `config.py` — Agency definitions, API URLs, FY settings, SF-133 line items
- `file_registry.json` — OMB MAX portal attachment IDs and filenames per FY
- `build.py` — Assembles `docs/data/site_data.json` from processed CSVs
- `data/` — SF-133 obligations pipeline (download, parse, transform, preprocess)
- `awards/` — Awards pipeline (fetch from 3 APIs, transform, preprocess)
- `charts/summary.py` — Summary metric computations used by build
- `docs/` — Static site (index.html, js/app.js, css/style.css, data/site_data.json)

## Site Updates

Follow `UPDATE.md` for the complete step-by-step update workflow, including:
- Quick awards-only updates
- Full obligation + awards updates
- How to detect new SF-133 data
- Annual fiscal year rollover procedure
- Troubleshooting common issues

## Critical: NSF Dollar Extraction (New Awards Tab)

The NSF Awards API is used for the **New Awards tab only** (the All Awards tab uses USASpending for NSF). The API offers several dollar fields per award. **Only one is correct:**

- **Use:** The **first entry** of the `fundsObligated` per-year array (e.g., `['FY 2024 = $29,000.00']`). Take entry `[0]` unconditionally — do NOT try to match by fiscal year. FY-matching fails badly: ~7% of awards have funds tagged to a different FY than their decision date, and for awards with multiple FY entries, matching picks up later-year increments instead of the initial obligation. FY-matching produced 32.6% for FY2025 vs the correct 54%.
- **Do not use:** `estimatedTotalAmt` (includes projected multi-year costs — inflates continuing grants by 2-3x) or `fundsObligatedAmt` (cumulative lifetime obligations — grows retroactively across years).
- **`_PRINT_FIELDS`** in `fetch_nsf.py` must include `fundsObligated` (the per-year array), not `fundsObligatedAmt` (the scalar).
- **Validation:** End-of-year NSF pct_of_approp should be 55-60% for all completed FYs. If you see values above 70% or a sudden collapse in the current FY, the wrong dollar field is being used.
- **Do not refactor** the extraction logic in `_extract_records()`. The current approach was validated against all three alternatives and is the only one that produces stable, defensible numbers.

## Agencies Tracked

| Key | Name | SF-133 Source | New Awards Source | All Awards Source |
|-----|------|--------------|-------------------|-------------------|
| NIH | NIH (Institutes + OD) | HHS file, bureau filter | NIH Reporter (types 1+2) | NIH Reporter (types 1+2+5, FY2017+) |
| NSF | NSF (R&RA + EDU) | NSF file, TRACCTs 100, 106 | NSF Awards API | USASpending (action_date) |
| DOE_SC | DOE (Science + ARPA-E) | DOE file, TRACCTs 222, 337 | USASpending (CFDA 81.049, 81.135) | USASpending (action_date) |
| NASA_SCI | NASA (Science) | NASA file, TRACCT 120 | USASpending (CFDA 43.001, 43.013) | USASpending (action_date) |
| USDA_RD | USDA (ARS + NIFA) | USDA file, TRACCTs 1400/1500/1502 | USASpending (CFDA 10.310) | USASpending (action_date) |

Sub-agency detail views are available: NIH by IC (~25), NSF by directorate (9 CFDAs), DOE by Office of Science vs ARPA-E, USDA by ARS vs NIFA. Sub-agencies are defined in `config.py` with a `parent` field and filtered at transform time from shared parent data.
