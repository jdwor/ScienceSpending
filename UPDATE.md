# Site Update Guide

## Quick Reference

| Task | Command |
|------|---------|
| New awards only | `python3 -m awards.preprocess && python3 build.py` |
| All awards (new + continuing) | `python3 -m awards.preprocess_all && python3 build.py` |
| Both awards pipelines | `python3 -m awards.preprocess && python3 -m awards.preprocess_all && python3 build.py` |
| Check for new obligations data | `python3 data/download.py --check` |
| Full update (obligations + awards) | See [Step-by-Step Update](#step-by-step-update) |
| Fiscal year rollover | See [Annual FY Rollover](#annual-fiscal-year-rollover) |

---

## Step-by-Step Update

### Step 1: Update awards data

Awards caches auto-expire after 24 hours for the current FY, so this always fetches fresh data.

**Important:** Always run these with no flags. The `--agencies` and `--years` flags overwrite the full output CSVs, destroying data for unselected agencies/years. Caching makes the full run fast anyway.

```bash
# New awards (NIH Reporter types 1+2, NSF Awards API, USASpending)
python3 -m awards.preprocess

# All awards (NIH Reporter types 1+2+5, USASpending for NSF/DOE/NASA/USDA)
python3 -m awards.preprocess_all
```

### Step 2: Check for new SF-133 obligations data

```bash
python3 data/download.py --check
```

This command:
1. Reads `docs/data/site_data.json` to see what month the site currently shows
2. Compares to today's date — if the site already has last month's data, it skips the check
3. If a check is warranted, downloads the current FY's Excel files from the OMB MAX portal
4. Quick-parses the HHS file to find the latest month with data
5. Reports whether new data is available

If new data **is** found:

```bash
python3 data/preprocess.py
```

This re-parses all cached SF-133 files and regenerates the processed CSVs.

### Step 3: Rebuild the site

```bash
python3 build.py
```

Outputs `docs/data/site_data.json`. The build script prints the latest period and a file size summary.

### Step 4: Verify

- Check the build output for the latest period label (e.g., "Latest period: Feb")
- Open `docs/index.html` in a browser and confirm charts render correctly
- Spot-check summary tables for reasonable values
- If committing, `git diff docs/data/site_data.json` to review what changed

---

## Data Sources

### SF-133 Obligations (monthly)

| Item | Detail |
|------|--------|
| Source | OMB MAX Portal — SF-133 Reports on Budget Execution |
| URL | `https://portal.max.gov/portal/document/SF133/Budget/attachments/{attachment_id}/{filename}` |
| Format | Excel (.xlsx), "Raw Data" sheet |
| Cadence | Monthly. Quarterly reports (Dec, Mar, Jun, Sep) are official; others preliminary. |
| Lag | ~2–4 weeks after month-end |
| Registry | `file_registry.json` maps FY → attachment_id → filenames |
| Cache | `data/cache/FY{year}/` — downloaded Excel files |
| Processed | `data/processed/obligation_series.csv`, `approp_summary.csv`, `yoy_comparison.csv` |

The same Excel files are updated in place by OMB each month — new monthly columns get populated. The attachment IDs and filenames in `file_registry.json` typically don't change within a fiscal year.

**If a download returns 403/404:** The attachment ID may have changed. Visit the [OMB SF-133 page](https://portal.max.gov/portal/document/SF133/Budget/FACTS%20II%20-%20SF%20133%20Report%20on%20Budget%20Execution%20and%20Budgetary%20Resources.html), find the current FY's attachment page, note the new ID from the URL, and update `file_registry.json`.

### NIH Reporter API (daily)

| Item | Detail |
|------|--------|
| Source | NIH Reporter — extramural awards |
| URL | `https://api.reporter.nih.gov/v2/projects/search` |
| New Awards | Type 1 (new) + Type 2 (competing renewal), excluding subprojects and intramural (Z codes) |
| All Awards | Type 1 + Type 2 + Type 5 (non-competing continuation) |
| Partitioning | By IC code (~25 institutes) to stay under 15k-record API limit |
| Rate limit | 1 request/second |
| Cache (new) | `awards/cache/nih/fy{year}_{ic}.json` — current FY expires after 24h |
| Cache (all) | `awards/cache/nih_all/fy{year}_{ic}.json` — separate cache for types 1+2+5 |

**Note:** FY2016 is excluded from the all-awards pipeline (`NIH_ALL_AWARDS_FISCAL_YEARS` in config.py) because Type 5 records are significantly underreported for that year in NIH Reporter.

### NSF Awards API (daily)

| Item | Detail |
|------|--------|
| Source | NSF Awards Search |
| URL | `https://api.nsf.gov/services/v1/awards.json` |
| Filter | CFDAs 47.041, .049, .050, .070, .074, .075, .076, .083, .084 |
| Partitioning | By calendar month to stay under 3k-result limit |
| Cache | `awards/cache/nsf/fy{year}_d{yearmonth}.json` — current FY expires after 24h |
| Used for | New Awards tab only. All Awards tab uses USASpending for NSF. |

### USASpending API (monthly)

| Item | Detail |
|------|--------|
| Source | USASpending.gov — spending over time |
| URL | `https://api.usaspending.gov/api/v2/search/spending_over_time/` |
| Award types | 04 (project grants) + 05 (cooperative agreements) |

**New awards** (`new_awards_only` filter):

| Agency | CFDAs |
|--------|-------|
| DOE (Office of Science + ARPA-E) | 81.049, 81.135 |
| NASA Science | 43.001, 43.013 |
| USDA (ARS + NIFA) | 10.310 |

Cache: `awards/cache/usaspending/{agency}_fy{year}.json`

**All awards** (`action_date` filter — captures continuations, modifications, renewals):

| Agency | CFDAs |
|--------|-------|
| NSF (topline) | 47.041, .049, .050, .070, .074, .075, .076, .083, .084 |
| NSF directorates | Individual CFDAs (e.g., NSF_ENG = 47.041, NSF_EDU_AWD = 47.076) |
| DOE (Office of Science + ARPA-E) | 81.049, 81.135 |
| DOE sub-agencies | DOE_SC_SCI = 81.049, DOE_ARPA_E = 81.135 |
| NASA Science | 43.001, 43.013 |
| USDA (ARS + NIFA) | 10.310 |
| USDA sub-agency | USDA_NIFA = 10.310 |

Cache: `awards/cache/usaspending_all/{agency}_fy{year}.json`

---

## Annual Fiscal Year Rollover

When a new fiscal year begins (October 1):

### 1. Update `config.py`

```python
CURRENT_FY = 2027                    # was 2026
FISCAL_YEARS = list(range(2016, 2028))        # extend by 1
AWARDS_FISCAL_YEARS = list(range(2016, 2028)) # extend by 1
NIH_ALL_AWARDS_FISCAL_YEARS = list(range(2017, 2028))  # extend by 1 (starts FY2017)
HIGHLIGHT_YEARS = [2027, 2026]                # shift forward
BAND_YEARS_EXCLUDE = {2027, 2026}             # shift forward
```

### 2. Update `file_registry.json`

Add a new entry for the new FY. The attachment ID and filenames must be obtained from the OMB MAX portal:

```json
"2027": {
    "attachment_id": "XXXXXXXXXX",
    "files": {
        "hhs": "FY2027_SF133_MONTHLY_Department_of_Health_and_Human_Services.xlsx",
        "nsf": "FY2027_SF133_MONTHLY_National_Science_Foundation.xlsx",
        "doe": "FY2027_SF133_MONTHLY_Department_of_Energy.xlsx",
        "nasa": "FY2027_SF133_MONTHLY_National_Aeronautics_and_Space_Administration.xlsx",
        "usda": "FY2027_SF133_MONTHLY_Department_of_Agriculture.xlsx"
    }
}
```

### 3. Run full pipeline

```bash
python3 data/download.py --years 2027
python3 data/preprocess.py
python3 -m awards.preprocess
python3 -m awards.preprocess_all
python3 build.py
```

### 4. Update hardcoded FY ranges in `docs/index.html`

Search for `MAINTENANCE: Update FY range` comments in the HTML. Update the hardcoded range text (e.g., "FY2016–FY2024" → "FY2016–FY2025") to match the new `BAND_YEARS_EXCLUDE` setting.

### 5. Verify

- New FY appears as highlighted line on charts
- Previous FY moves from highlighted to band-year
- Summary tables show new FY values
- Historical envelope band now includes the prior-prior year
- Methodology text shows correct FY range for historical band

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `download.py` returns 403/404 | Attachment ID changed on MAX portal | Find new ID on portal page, update `file_registry.json` |
| Awards API timeout | Transient network issue | Retry; pipeline uses caching so partial progress is saved |
| Missing months in charts | SF-133 file doesn't have that period yet | Wait for OMB to publish; check with `--check` |
| Appropriation shows 0 during CR | Normal — Line 1100 is 0 under Continuing Resolution | No fix needed; values correct once full-year bill enacted |
| `openpyxl` error reading Excel | Corrupt download | Delete cached file, re-download with `--force` |
| Awards data empty for agency | API changed or CFDA codes updated | Check API directly; verify CFDA codes in `config.py` |
| Build fails on missing CSV | Preprocess step was skipped | Run `python3 data/preprocess.py` and/or `python3 -m awards.preprocess` first |
| Need to refresh one agency's cache | Stale or corrupt cache for specific agency | Delete that agency's cache files (e.g., `rm awards/cache/nih/fy2026_*.json`), then rerun pipeline |
