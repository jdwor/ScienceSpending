# Spending on Science

Static website tracking federal science spending via SF-133 obligation reports and new award data from NIH Reporter, NSF Awards, and USASpending APIs. The site is served from `docs/` as a GitHub Pages-style static site.

## Key Commands

```bash
# Check for new SF-133 data
python3 data/download.py --check

# Update awards data (auto-fetches if cache >24h old)
python3 -m awards.preprocess

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

## Agencies Tracked

| Key | Name | SF-133 Source | Awards Source |
|-----|------|--------------|--------------|
| NIH | NIH (Institutes + OD) | HHS file, bureau filter | NIH Reporter API |
| NSF | NSF (Research & Related) | NSF file, TRACCT 100 | NSF Awards API |
| DOE_SC | DOE (Office of Science) | DOE file, TRACCT 222 | USASpending (CFDA 81.049) |
| NASA_SCI | NASA (Science) | NASA file, TRACCT 120 | USASpending (CFDA 43.001, 43.013) |
| USDA_RD | USDA (ARS + NIFA) | USDA file, TRACCT 1400/1500/1502 | USASpending (CFDA 10.310) |
