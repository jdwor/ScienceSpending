# Red Team Audit: Spending on Science Tracker

This document presents a rigorous adversarial audit of the tracker, organized by severity. Each finding describes what an opponent would say, how legitimate the criticism is, and a recommendation for how to respond.

---

## Critical: Issues That Could Undermine Core Claims

### 1. Appropriation denominator choice during Continuing Resolutions

**The attack:** "The tracker uses Line 1100 (raw discretionary appropriation) as the denominator for percent-obligated calculations. During a Continuing Resolution, Line 1100 reflects the *annualized rate* of the prior year's appropriation, not the actual spending authority. The real available authority is Line 1160 (net discretionary appropriation), which accounts for CR preclusions (Line 1134). For NIH in FY2026, Line 1100 = $46.5B but Line 1160 = $15.6B. The tracker shows NIH at 13.9% obligated, making it look like spending has stalled. But against actual available authority, NIH has obligated 41.7% — which is *faster* than normal. The tracker manufactures the appearance of a slowdown."

**Legitimacy:** Mixed. The code's rationale (in `transform.py:27-29`) is sound: Line 1100 is more stable across years, and once a full-year bill passes, 1100 equals the enacted level. Using 1160 during CRs would make agencies appear to be spending at 200-300% of their appropriation, which is also misleading. However, the *transition* — years with full-year bills (high denominator) vs. years mid-CR (same denominator but restricted authority) — creates an asymmetry in cross-year comparisons that consistently makes CR periods look worse. The actual data shows this clearly: for DOE, FY2025 at January shows 52% vs. FY2026 at 30% — but FY2025 had already received its full-year bill by January.

**Recommendation:** **Partially address.** The current approach is defensible for cross-year consistency, but the site should explicitly state when agencies are operating under a CR and note that spending authority is restricted. Add a CR indicator to the data badge and/or a conditional callout: "Note: FY2026 agencies are currently operating under a Continuing Resolution. Obligation rates will appear lower than usual because the appropriation denominator reflects the full-year annualized rate, while actual spending authority is restricted by the CR." Also consider adding a sentence to the Data & Methods noting the specific Line 1100 vs 1160 choice and why.

---

### 2. NSF award dollars use `estimatedTotalAmt`, not `fundsObligatedAmt`

**The attack:** "The tracker counts NSF award *estimated total amounts* — the full multi-year projected value of each grant — as if they were obligated in the year the award was made. A 5-year NSF grant worth $500K would be counted as $500K in the award year, even though only $100K might be obligated. This grossly overstates the first-year financial commitment. Meanwhile, NIH Reporter gives annual award amounts, and USASpending gives monthly obligations. The three agencies on the New Awards tab are measuring fundamentally different things but displayed as if they are comparable."

**Legitimacy:** High. This is a real measurement inconsistency. `fetch_nsf.py:121` uses `estimatedTotalAmt` and the field `fundsObligatedAmt` is fetched but only stored — never used for the cumulative dollar metric. The site normalizes by putting everything as "% of appropriation," which helps with cross-agency comparison, but within-NSF year-over-year dollar comparisons are inflated. Critically, if NSF shifted from many small awards to fewer large multi-year awards (or vice versa), the metric would show a change that doesn't reflect actual spending commitments.

**Recommendation:** **Address.** Switch to `fundsObligatedAmt` for NSF dollar totals, or explicitly document that NSF uses estimated total award values. The methodology section currently says only that awards are "dated by the award decision date" without disclosing the dollar metric difference. At minimum, add a clear note in the Data & Methods section. Better: use `fundsObligatedAmt` for dollars and keep `estimatedTotalAmt` as a secondary metric, since `fundsObligatedAmt` is more comparable to how NIH and USASpending measure dollars.

---

### 3. Red/green color coding embeds a normative judgment

**The attack:** "The metric cards show year-over-year changes in *red* (negative) when spending is slower and *green* (positive) when it's faster. This encodes the assumption that slower spending is bad. An administration could be deliberately slowing spending to impose fiscal discipline, or spending might slow during a CR for structural reasons outside any agency's control. The color framing makes any deviation from prior-year pace look like a failure."

**Legitimacy:** High. This is a straightforward framing choice that a critic would immediately identify. The CSS uses `--color-negative: #9b2226` (red) and `--color-positive: #2d6a4f` (green) for the metric deltas. The code at `app.js:567-572` assigns `negative` class when `yoy_diff < 0`. This is not neutral visualization — it assigns moral valence to a directional change.

**Recommendation:** **Address.** Replace red/green with a neutral color scheme (e.g., different shades of blue or gray for direction). The comparison itself is valuable; the *interpretation* should be left to the viewer. Alternatively, use directional arrows without color connotation. If you keep directional coloring, be explicit about the assumption: "Color indicates direction of change from the historical average, not a quality judgment."

---

## Serious: Issues That Would Require a Nuanced Defense

### 4. Editorializing language in the site subtitle and callouts

**The attack:** "The site claims to 'transparently track the pace of spending on science' but its own subtitle says spending 'follows a relatively predictable schedule, which ensures agencies are able to efficiently allocate resources to the most effective and meritorious research teams.' This is an opinion — it assumes the historical pace is optimal and that deviations are harmful. The word 'disruptions' in the obligations callout implies changes are abnormal. A neutral tracker would describe what is happening, not what should be happening."

**Legitimacy:** Moderate to high. The subtitle's causal claim ("ensures agencies are able to efficiently allocate...") is an assertion about the benefits of predictable spending. While most science policy experts would agree, it is editorializing. The word "disruptions" in the callout text is similarly loaded.

**Recommendation:** **Address.** Revise the subtitle to be descriptive rather than prescriptive. For example: "This spending follows a relatively predictable schedule. This site tracks both total obligation rates and new award activity at five major science agencies to provide transparency into the pace of spending on science." Remove "which ensures agencies are able to efficiently allocate resources to the most effective and meritorious research teams" — this is a policy claim. Replace "disruptions" with "changes" in the callout text.

---

### 5. FY2016-2017 have missing months, distorting the historical band

**The attack:** "FY2016 data has only 8 of 12 months (missing the quarterly months: Dec, Mar, Jun, Sep). FY2017 has the same 8 months. FY2018+ have all 12. When the historical band is computed at month 3 (December), FY2016 and FY2017 contribute no data — so the 'historical average' at Q1 is really the FY2018-2024 average. But at month 2 (November), FY2016-2024 all contribute. The number of years in the baseline silently changes from month to month, which can create discontinuities in the envelope and shift the average."

**Legitimacy:** Moderate. The `compute_prior_year_envelope()` function in `build.py:57-67` skips years that lack data at a given month, so the band does indeed have a variable composition. For the quarterly months (3, 6, 9, 12), the band is based on 7 years (FY2018-2024) instead of 9 (FY2016-2024). This is a subtle effect but could shift the mean by a few percentage points, especially if FY2016-2017 were outlier years.

**Recommendation:** **Partially address.** The current code handles this gracefully (missing years are simply omitted from the band at that month). Document this behavior: "FY2016-2017 data is available at non-quarterly months only; the historical range at quarterly reporting periods (December, March, June, September) uses FY2018-2024." Consider either interpolating FY2016-2017 to fill quarterly gaps, or starting the band at FY2018 consistently.

---

### 6. No inflation adjustment for dollar-denominated views

**The attack:** "The dollar-mode charts compare FY2016 obligations in nominal 2016 dollars to FY2026 obligations in nominal 2026 dollars. Cumulative inflation over this period is roughly 30-35%. A flat real budget appears as growth in the chart. This makes historical spending look systematically lower than it actually was in purchasing-power terms, exaggerating the gap between past and present — or between present and past, depending on the direction of the narrative."

**Legitimacy:** Moderate. The default view is percent-obligated (which normalizes by appropriation and is inflation-immune), so most users see the correct picture. But the dollar toggle view and the metric card showing raw obligation dollars do not adjust for inflation. The appropriation-normalized views partly address this, but the raw dollar data tables also use nominal terms.

**Recommendation:** **Partially address.** Add a note to the dollar-mode view: "Dollar amounts are nominal (not adjusted for inflation)." Consider adding a GDP deflator or CPI adjustment toggle for advanced users. The percent-of-appropriation view is already the right metric for most analyses, so elevating it as the primary/default view (which it already is) is the key mitigation.

---

### 7. COVID-era supplemental funding (FY2020) inflates the historical baseline

**The attack:** "FY2020 included billions in emergency supplemental appropriations (CARES Act, etc.) that dramatically increased both appropriations and obligations. NIH's FY2020 appropriation jumped from $37B to $41.4B with budget authority reaching $46B. Including FY2020 in the 'historical average' makes the pre-COVID and post-COVID pace look slower by comparison. The tracker doesn't flag or control for this extraordinary year."

**Legitimacy:** Moderate. FY2020 is included in the band (FY2016-2024). Because the tracker uses percent-obligated (obligations / appropriation), the appropriation increase partially offsets the obligation increase. But the *pace* of spending was genuinely different in FY2020 due to emergency disbursements, which could skew the average at certain months.

**Recommendation:** **Document but don't exclude.** Adding a note about FY2020's COVID supplementals would be transparent. Excluding it from the band would be a judgment call that could itself be criticized. Consider offering an optional "exclude FY2020" toggle, or noting in the methodology: "FY2020 included emergency supplemental appropriations (CARES Act) that affected both appropriation levels and spending pace. This year is included in the historical baseline."

---

### 8. Agency scope choices are consequential but buried in config

**The attack:** "The tracker's scope decisions determine what gets measured. NIH excludes three TRACCTs (Management Fund, Services & Supply, Buildings & Facilities). NSF tracks only TRACCT 100 (Research & Related), excluding Education and TIP directorates. USDA includes only three TRACCTs. These are reasonable choices, but they're arbitrary in the sense that different scoping would tell a different story. NSF TIP spending has grown rapidly; excluding it understates NSF's total activity. These choices are documented only in a Python config file, not in the public methodology."

**Legitimacy:** Moderate. The scope choices are defensible (they target the research-specific functions), but they do involve judgment. The methodology section mentions "specific TRACCT codes" without listing them or explaining why particular codes were included/excluded.

**Recommendation:** **Address.** Add the specific TRACCT/CFDA filters to the Data & Methods page. For each agency, list what is included and what is excluded, and briefly state why. For example: "NSF: TRACCT 100 (Research & Related Activities). Excludes STEM Education (TRACCT 200) and Technology, Innovation, and Partnerships (TRACCT 300)."

---

## Moderate: Issues That Are Defensible but Should Be Documented

### 9. The auto-exclusion of "unreliable" USASpending years is opaque

**The attack:** "The `_detect_reliable_years()` function silently excludes any fiscal year where cumulative award dollars are less than 25% of the peak year. For DOE, this excludes FY2016-2018; for USDA, FY2016-2017. The 25% threshold is arbitrary. If an agency genuinely had very low awards in early years (perhaps because the program was ramping up), that's real data being discarded. Users see different baseline periods for different agencies with no explanation."

**Legitimacy:** Low to moderate. The exclusion is a reasonable data quality measure — USASpending coverage genuinely improved over time and early years have incomplete data. But the 25% threshold and automated nature mean the behavior is unpredictable.

**Recommendation:** **Document.** The methodology section does note that "years with incomplete data are automatically excluded from the historical baseline." Strengthen this by listing the excluded years explicitly per agency, and consider making the threshold configurable or replacing automation with a manually curated list of valid years per agency/source.

---

### 10. Deduplication logic for NIH awards is first-come, first-served

**The attack:** "When an NIH award is funded by multiple ICs (institutes), it appears in multiple API queries. The tracker keeps only the first IC that returns the record (`keep='first'`). The order of IC queries is hard-coded alphabetically. This means multi-IC awards are systematically attributed to the IC that appears earliest alphabetically, which could bias per-IC analyses (if those are ever exposed)."

**Legitimacy:** Low for the current tracker (which doesn't show per-IC breakdowns), but worth noting. The deduplication is done on `project_num` at `fetch_nih.py:150`, and the IC iteration order in `config.py:129-134` is not strictly alphabetical but is a fixed list. This doesn't affect total NIH counts, only the `ic_code` field — which is not used in the final output.

**Recommendation:** **No change needed** for the current scope. If per-IC analysis is ever added, switch to using the administrative IC from the API response (which is already the `agency_ic_admin` field being captured).

---

### 11. The "% of average pace" metric can produce misleading early-FY values

**The attack:** "In October (month 1), all agencies start at 100% of average pace by construction (0/0 → forced to 100%). In November, with only one month of data, small absolute differences in obligations produce large percentage swings. The tracker fades the Oct-Nov segment, but the visual effect is that all agencies appear to diverge sharply from 100% starting in December, potentially overstating early-year deviations."

**Legitimacy:** Low to moderate. The fading is an appropriate mitigation. The callout text explains this. But the visual transition from dashed-faded to solid can still create a misleading impression of sudden divergence.

**Recommendation:** **Already partially addressed.** The callout explains the fading. Consider starting the solid line at month 3 (December/Q1) instead of month 2 to further reduce early-month noise. Alternatively, note that small absolute differences early in the year produce large percentage differences.

---

### 12. The site presents a snapshot but may be read as real-time

**The attack:** "The tracker shows a 'build date' and 'obligations through [month]' badge, but there's no indication of how stale the awards data might be. The API caches expire after 24 hours, but the site_data.json is static and only updated when someone manually runs the pipeline. Between builds, the site could be days or weeks behind the latest API data."

**Legitimacy:** Low to moderate. The build date is displayed, which is more transparent than many similar trackers. But the awards data may have been fetched days before the build date, with no per-source timestamp.

**Recommendation:** **Minor improvement.** Add an "Awards data as of [date]" note derived from the actual fetch timestamps of the cache files, or at minimum the build date suffices if the pipeline is run consistently.

---

### 13. USDA scope: ARS + NIFA combined may obscure divergent trends

**The attack:** "USDA's tracked accounts combine ARS (Agricultural Research Service, TRACCT 1400) and NIFA (National Institute of Food and Agriculture, TRACCTs 1500/1502). These are fundamentally different: ARS is an intramural research agency (labs), while NIFA is an extramural grant-making agency. Combining them could mask opposing trends — e.g., NIFA grants might be accelerating while ARS lab spending slows, but the combined metric shows flat."

**Legitimacy:** Moderate. This is a genuine scoping question. The display name says "USDA (ARS + NIFA)" which is transparent about what's included, but doesn't allow users to see the components separately.

**Recommendation:** **Document but don't split.** Splitting would add complexity. Note in methodology: "USDA tracking combines intramural (ARS) and extramural (NIFA) research accounts. Trends may differ between these components."

---

### 14. Awards data for USASpending agencies (DOE, NASA, USDA) shows `cumulative_count = 0`

**The attack:** "The award count metric is zero for DOE, NASA, and USDA because USASpending's spending_over_time API returns dollar aggregates, not individual award counts. Yet the data structure includes a `cumulative_count` field set to 0, which could confuse data consumers who download the CSV."

**Legitimacy:** Low. The UI correctly hides the count toggle for USASpending agencies (`awards/transform.py:109`), and the methodology notes the difference. But the CSV export includes the zero-count column.

**Recommendation:** **Minor improvement.** Set `cumulative_count` to `null`/`NaN` instead of 0 for USASpending agencies to avoid ambiguity in exported data.

---

## Low: Potential Criticisms That Are Easily Defended

### 15. Selection of agencies appears targeted

**The attack:** "Why these five agencies? NIH, NSF, DOE Science, NASA Science, and USDA Research are all basic-science-heavy agencies that have been publicly discussed in the context of spending freezes. The tracker ignores DOD basic research (the largest federal R&D funder), EPA, NOAA, USGS, and other agencies. The selection seems designed to highlight agencies where spending slowdowns would be most politically salient."

**Legitimacy:** Low. These are the five major civilian science agencies that have publicly available SF-133 data with clearly identifiable research accounts. DOD research spans dozens of account codes across multiple files and would be much harder to track accurately. The selection is defensible on data-availability and scope grounds.

**Recommendation:** **No change needed**, but consider adding a note: "These five agencies represent the major civilian federal science funding agencies. Department of Defense research is excluded due to the complexity of isolating research accounts across multiple budget lines."

---

### 16. Only unexpired accounts (STAT=U) are included

**The attack:** "The tracker filters to STAT='U' (unexpired accounts), excluding expired accounts. Expired accounts can still have upward adjustments and deobligations. Excluding them may miss meaningful fiscal activity."

**Legitimacy:** Very low. Expired accounts are legacy balances; the active fiscal year's execution is properly measured in unexpired accounts. This is standard budget analysis practice.

**Recommendation:** **No change needed.** The methodology section could briefly note that expired accounts are excluded, consistent with standard federal budget execution analysis.

---

## Summary of Recommendations

| # | Finding | Severity | Action |
|---|---------|----------|--------|
| 1 | CR denominator effect | Critical | Add CR indicator + methodology note |
| 2 | NSF `estimatedTotalAmt` vs `fundsObligatedAmt` | Critical | Switch metric or document prominently |
| 3 | Red/green color coding | Critical | Switch to neutral colors |
| 4 | Editorializing language | Serious | Revise subtitle and callout text |
| 5 | FY2016-17 missing months | Serious | Document or standardize band start |
| 6 | No inflation adjustment | Serious | Add note to dollar views |
| 7 | FY2020 COVID supplementals | Serious | Add methodology note |
| 8 | Agency scope buried in config | Serious | List filters in Data & Methods |
| 9 | Auto-exclusion of USASpending years | Moderate | Document excluded years explicitly |
| 10 | NIH dedup ordering | Moderate | No change needed |
| 11 | Early-FY % of average noise | Moderate | Already addressed via fading |
| 12 | Data staleness | Moderate | Minor timestamp improvement |
| 13 | USDA ARS+NIFA combined | Moderate | Document in methodology |
| 14 | Zero award counts for USASpending | Moderate | Use null instead of 0 |
| 15 | Agency selection bias | Low | Optional note |
| 16 | Unexpired-only filter | Low | No change needed |

### Priority Order for Fixes

1. **Revise language** (subtitle, callouts) — easiest win, removes most obvious attack surface
2. **Neutralize color coding** — small CSS/JS change, big credibility improvement
3. **Add CR context** — conditional callout when agencies are under a CR
4. **Document NSF dollar metric** — if not switching fields, at minimum disclose
5. **Expand Data & Methods** — list TRACCT/CFDA filters, baseline year composition, excluded years, FY2020 note
6. **Add inflation note** to dollar-mode views
