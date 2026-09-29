# Site Update Guide

## Quick Reference

| Task | Command |
|------|---------|
| New awards only | `python3 -m awards.preprocess && python3 build.py` |
| All awards (new + continuing) | `python3 -m awards.preprocess_all && python3 build.py` |
| Both awards pipelines | `python3 -m awards.preprocess && python3 -m awards.preprocess_all && python3 build.py` |
| Check for new obligations data | `python3 data/download.py --check` |
| Full update (obligations + awards) | See [Step-by-Step Update](#step-by-step-update) |
| Fiscal year rollover | Automatic — see [Fiscal Year Rollover](#fiscal-year-rollover) |
| Automated weekly updates | See [Automated Weekly Updates](#automated-weekly-updates) |
| Validate a build before publishing | `python3 scripts/validate_update.py` |

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

## Fiscal Year Rollover

The rollover is automatic — nothing needs editing on October 1. `config.CURRENT_FY`
is derived from the date, and the FY ranges, highlight years, and historical-band
years all follow from it. Set `SCISPEND_TODAY=YYYY-MM-DD` to simulate another date
(e.g. `SCISPEND_TODAY=2026-10-05 python3 build.py`).

The obligations and awards views roll over at different times, because SF-133 has
no October report:

| When | Awards tabs | Obligations tab |
|------|-------------|-----------------|
| Oct 1 | Switch to the new FY (starts at $0 with a zero point "as of yesterday") | Stay on the prior FY, which keeps filling in (Aug, then final Sep report) |
| ~Late Dec (first SF-133 report, November) | — | Switch to the new FY (`data.transform.get_obligations_fy` = latest FY with SF-133 data) |

What handles each piece:

- **Registry:** `data/download.py --check` discovers the new FY's attachment ID on
  its OMB MAX page and adds it to `file_registry.json` once OMB posts it.
- **Prior-FY data:** caches for the prior FY keep refreshing for
  `PRIOR_FY_REFRESH_DAYS` (120) after Oct 1 (`config.is_fy_frozen`), so late
  SF-133 reports, NIH Reporter backfill, and USASpending lag are captured.
- **Appropriation denominator:** until the new FY's first SF-133 report exists, the
  awards views use the prior FY's appropriation (≈ the CR rate) for "% of appropriation".
- **Frontend:** `config.current_fy` / `highlight_years` / `band_years_exclude` in
  `site_data.json` describe the obligations views; `awards_current_fy` /
  `awards_highlight_years` / `awards_band_years_exclude` describe the awards views.
  Methodology FY ranges are filled in from the data (`fillFyText` in `app.js`).

**Verify after each rollover stage:** the new FY appears as the highlighted line,
the prior FY moves to gray, and the band gains the prior-prior year.

---

## Automated Weekly Updates

A launchd job runs `scripts/auto_update.sh` every **Monday at 7:00 AM** (or at next
wake, if the Mac was asleep). It runs Steps 1–3, validates the result, and commits +
pushes `data update` to `main` (GitHub Pages redeploys). If any step fails, nothing
is published and the site keeps its last good data.

| Item | Detail |
|------|--------|
| Runs from | `~/ScienceSpending-auto` — a dedicated clone. macOS blocks launchd jobs from reading `~/Documents`, so it can't use this repo. It holds its own copy of the API caches and resets to `origin/main` at the start of each run. |
| Schedule | `~/Library/LaunchAgents/org.sciencespending.update.plist` (template in `scripts/`) |
| Logs | `~/Library/Logs/sciencespending/` — `STATUS.txt` has the last result; one log per run |
| Guardrails | `scripts/validate_update.py`: completed FYs must not change; NSF completed-FY % of appropriation 48–65%; all agencies present; files didn't shrink; obligations period never goes backwards. An NSF current-FY drop triggers a clean NSF re-fetch; if it reproduces, it's published as real. |
| Dry run | `SCISPEND_DRY_RUN=1 ~/ScienceSpending-auto/scripts/auto_update.sh` |
| Run now | `launchctl kickstart gui/$(id -u)/org.sciencespending.update` |
| Pause / resume | `launchctl bootout gui/$(id -u)/org.sciencespending.update` / `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.sciencespending.update.plist` |

After a stretch of automated runs, `git pull` this repo before working in it.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `download.py` returns 403/404 | Attachment ID changed on MAX portal | Find new ID on portal page, update `file_registry.json` |
| Awards API timeout | Transient network issue | Retry; pipeline uses caching so partial progress is saved |
| Missing months in charts | SF-133 file doesn't have that period yet | Wait for OMB to publish; check with `--check` |
| Appropriation looks off during CR | Line 1100 reports the CR's annualized rate, not the enacted level | No fix needed; values correct once full-year bill enacted |
| Automated update didn't publish | See `~/Library/Logs/sciencespending/STATUS.txt` and the latest log | Fix the cause, then run it now (see [Automated Weekly Updates](#automated-weekly-updates)) |
| `openpyxl` error reading Excel | Corrupt download | Delete cached file, re-download with `--force` |
| Awards data empty for agency | API changed or CFDA codes updated | Check API directly; verify CFDA codes in `config.py` |
| Build fails on missing CSV | Preprocess step was skipped | Run `python3 data/preprocess.py` and/or `python3 -m awards.preprocess` first |
| Need to refresh one agency's cache | Stale or corrupt cache for specific agency | Delete that agency's cache files (e.g., `rm awards/cache/nih/fy2026_*.json`), then rerun pipeline |
