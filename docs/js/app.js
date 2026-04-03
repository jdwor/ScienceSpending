/* ================================================================
   Science Agency Spend-Down Tracker — Frontend
   ================================================================ */

(function () {
    'use strict';

    // ── Shared chart styling ──
    const FONT_SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif";
    const FONT_SERIF = "Source Serif 4, Georgia, serif";
    const TEXT_COLOR = "#0f1419";
    const MUTED_COLOR = "#6b7280";
    const GRID_COLOR = "rgba(217,214,208,0.15)";
    const AXIS_LINE_COLOR = "#d9d6d0";
    const PRIOR_RANGE_COLOR = "rgba(160, 175, 200, 0.15)";
    const HIGHLIGHT_COLORS = { 2025: "#94a3b8" };

    // ── Source type display names ──
    const SOURCE_LABELS = {
        nih_reporter: 'NIH Reporter',
        nsf_awards: 'NSF Awards',
        usaspending: 'USASpending',
    };

    // ── Agency Descriptions ──
    let DATA = null;

    // ── Utilities ──

    // ── Segmented Control Helpers ──

    function initSegmentedControl(containerId, callback) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll('.seg-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.disabled) return;
                container.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                callback(btn.dataset.mode);
            });
        });
    }

    function getActiveMode(containerId) {
        const active = document.querySelector('#' + containerId + ' .seg-btn.active');
        return active ? active.dataset.mode : 'pct';
    }

    function formatDollars(amount) {
        if (amount == null) return "N/A";
        const abs = Math.abs(amount);
        if (abs >= 1e9) return "$" + (amount / 1e9).toFixed(2) + "B";
        if (abs >= 1e6) return "$" + (amount / 1e6).toFixed(1) + "M";
        return "$" + amount.toLocaleString('en-US', { maximumFractionDigits: 0 });
    }

    function fmtSigned(v) {
        var s = Math.abs(v).toFixed(1);
        return v > 0 ? '+' + s + '%' : v < 0 ? '\u2212' + s + '%' : '0.0%';
    }

    function fyMonthLabels() {
        return { 1: "Oct", 2: "Nov", 3: "Dec", 4: "Jan", 5: "Feb", 6: "Mar",
                 7: "Apr", 8: "May", 9: "Jun", 10: "Jul", 11: "Aug", 12: "Sep" };
    }

    function tickArrays() {
        // Tick marks at month BOUNDARIES: 0 = start of Oct, 1 = end of Oct /
        // start of Nov, ..., 12 = end of Sep.
        // ticktext carries month names for hover headers (invisible on the axis
        // via transparent tickfont); annotations provide visible labels at midpoints.
        const labels = fyMonthLabels();
        const vals = [];
        const texts = [];
        for (let i = 0; i <= 12; i++) {
            vals.push(i);
            texts.push(i >= 1 && i <= 12 ? labels[i] : '');
        }
        return { vals, texts };
    }

    function obligationMonthLabels(compact) {
        // Month name annotations centered between boundary ticks.
        // On mobile, show only every other month to avoid crowding.
        const labels = fyMonthLabels();
        const mobile = isMobile();
        const annots = [];
        for (let i = 1; i <= 12; i++) {
            if (mobile && !compact && i % 2 === 0) continue;
            annots.push({
                text: labels[i],
                x: i - 0.5,
                xref: 'x',
                y: 0,
                yref: 'paper',
                yanchor: 'top',
                yshift: -4,
                xanchor: 'center',
                showarrow: false,
                font: { family: FONT_SANS, size: compact ? 10 : (mobile ? 9 : 11), color: MUTED_COLOR },
            });
        }
        return annots;
    }

    function sourceAnnotation(text, yOffset) {
        if (isMobile()) return null;
        return {
            text: text || "Source: OMB SF-133",
            xref: 'paper',
            yref: 'paper',
            x: 1,
            y: yOffset || -0.28,
            xanchor: 'right',
            yanchor: 'top',
            showarrow: false,
            font: { family: FONT_SANS, size: 9, color: '#9ca3af' },
        };
    }

    // Mobile detection
    function isMobile() { return window.innerWidth < 768; }

    // Plotly config for full-size charts (shows camera icon on hover)
    const PLOTLY_CONFIG_EXPORT = {
        displayModeBar: 'hover',
        modeBarButtonsToRemove: [
            'zoom2d', 'pan2d', 'select2d', 'lasso2d',
            'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d',
        ],
        toImageButtonOptions: {
            format: 'png',
            width: 1200,
            height: 700,
            scale: 2,
        },
        responsive: true,
        scrollZoom: false,
    };

    // Plotly config for small multiples (no mode bar, no drag-zoom on mobile)
    function plotlyConfigCompact() {
        return {
            displayModeBar: false,
            responsive: true,
            scrollZoom: false,
            staticPlot: isMobile(),
        };
    }

    // Plotly config for full-size charts on mobile (no drag-zoom)
    function plotlyConfigFull() {
        var cfg = Object.assign({}, PLOTLY_CONFIG_EXPORT);
        if (isMobile()) {
            cfg.staticPlot = true;
        }
        return cfg;
    }

    function baseAxisStyle() {
        return {
            gridcolor: GRID_COLOR,
            zeroline: false,
            showline: true,
            linecolor: AXIS_LINE_COLOR,
            linewidth: 1,
            tickfont: { family: FONT_SANS, size: 11, color: MUTED_COLOR },
        };
    }

    // ── Data Badge ──

    function renderDataBadge() {
        const badge = document.getElementById('data-badge');
        const buildEl = document.getElementById('footer-build');
        if (!badge) return;

        const cfg = DATA.config;
        const parts = [];

        if (cfg.latest_period_label) {
            parts.push('Obligations through ' + cfg.latest_period_label + ' ' + cfg.current_fy);
        }

        // Find latest awards date across all agencies
        if (DATA.awards_summary) {
            let latestAwardDate = null;
            for (const key of Object.keys(DATA.awards_summary)) {
                const d = DATA.awards_summary[key].latest_date;
                if (d && (!latestAwardDate || d > latestAwardDate)) latestAwardDate = d;
            }
            if (latestAwardDate) {
                const dt = new Date(latestAwardDate + 'T00:00:00');
                const monthName = dt.toLocaleString('en-US', { month: 'short' });
                const fyMonth = dt.getMonth() >= 9 ? dt.getMonth() - 8 : dt.getMonth() + 4;
                parts.push('Awards through ' + monthName + ' ' + cfg.current_fy);
            }
        }

        if (cfg.build_date) {
            parts.push('Updated ' + cfg.build_date);
        }

        if (parts.length > 0) {
            badge.textContent = parts.join('  \u00b7  ');
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }

        if (buildEl) {
            buildEl.innerHTML = 'Built by Jordan Dworkin\u2002<a href="mailto:jordan.dworkin@coefficientgiving.org" title="Contact" style="text-decoration:none;">&#9993;</a>';
        }
    }

    // ── Tab Navigation ──

    function initTabs() {
        const btns = document.querySelectorAll('.tab-btn');
        const panels = document.querySelectorAll('.tab-panel');

        function activateTab(tabName) {
            const btn = document.querySelector('.tab-btn[data-tab="' + tabName + '"]');
            if (!btn) return;
            btns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            panels.forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            document.getElementById('tab-' + tabName).classList.add('active');
            setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
        }

        // Map between URL hashes and internal tab names
        const tabToHash = { obligations: 'obligations', awards: 'awards', data: 'methods', unified: 'unified' };
        const hashToTab = {};
        for (const k in tabToHash) hashToTab[tabToHash[k]] = k;

        btns.forEach(btn => {
            btn.addEventListener('click', () => {
                activateTab(btn.dataset.tab);
                history.replaceState(null, '', '#' + (tabToHash[btn.dataset.tab] || btn.dataset.tab));
            });
        });

        // Activate tab from URL hash on load
        const hash = location.hash.replace('#', '');
        const tabFromHash = hashToTab[hash] || hash;
        if (tabFromHash && document.querySelector('.tab-btn[data-tab="' + tabFromHash + '"]')) {
            activateTab(tabFromHash);
        }
    }

    // ── Data & Methods Section Toggle ──

    function initDataSectionToggle() {
        const select = document.getElementById('data-section-select');
        if (!select) return;

        select.addEventListener('change', () => {
            const val = select.value;
            document.getElementById('data-section-obligations').style.display = val === 'obligations' ? '' : 'none';
            document.getElementById('data-section-awards').style.display = val === 'awards' ? '' : 'none';
        });
    }

    // ── Multi-Agency Overview Chart ──

    function renderMultiAgencyChart() {
        const cfg = DATA.config;
        const multiData = DATA.multi_agency;
        const ticks = tickArrays();
        const traces = [];

        // 0% "on pace" reference line — spans full FY (start of Oct to end of Sep)
        traces.push({
            x: [0, 12],
            y: [0, 0],
            mode: 'lines',
            line: { color: '#9ca3af', width: 1, dash: 'dot' },
            showlegend: false,
            hoverinfo: 'skip',
        });

        const agencyKeys = Object.keys(cfg.agencies);
        for (const key of agencyKeys) {
            const agency = cfg.agencies[key];
            const trace = multiData[key];
            if (!trace) continue;

            const months = trace.months;
            const vals = trace.pct_of_mean;

            const labels = fyMonthLabels();

            // Dashed lead-in from start of Oct (x=0) at midpoint to first real data point
            if (months.length > 0) {
                traces.push({
                    x: [0, months[0]],
                    y: [0, vals[0]],
                    mode: 'lines',
                    line: { color: agency.color, width: 1.5, dash: 'dot' },
                    opacity: 0.35,
                    showlegend: false,
                    hoverinfo: 'skip',
                });
            }

            const mainText = months.map(m => labels[m] || '');

            traces.push({
                x: months,
                y: vals,
                text: mainText,
                mode: 'lines+markers',
                name: agency.display_name,
                line: { color: agency.color, width: 2.5 },
                marker: { size: 5, color: agency.color },
                customdata: vals.map(v => fmtSigned(v)),
                hovertemplate: '<b>' + agency.display_name + '</b><br>%{text}: %{customdata} vs. avg. pace<extra></extra>',
                hoverlabel: { bordercolor: agency.color },
            });
        }

        const bandFys = DATA.config.band_years_exclude;
        const allFys = Object.values(DATA.spenddown).flatMap(a => a.fiscal_years);
        const priorFys = [...new Set(allFys)].filter(y => !bandFys.includes(y)).sort();
        const bandLabel = priorFys.length > 1
            ? `FY${priorFys[0]}\u2013${priorFys[priorFys.length - 1]}`
            : `FY${priorFys[0]}`;

        // Set HTML chart title
        const titleEl = document.getElementById('overview-chart-title');
        if (titleEl) {
            titleEl.textContent = `FY${cfg.current_fy} Obligation Pace vs. ${bandLabel} Average`;
        }

        const layout = {
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals,
                ticktext: ticks.texts,
                tickfont: { size: 0.1, color: 'rgba(0,0,0,0)' },
                ticks: '',
                range: [-0.5, 12.5],
                showgrid: true,
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: '%',
                tickformat: '+d',
                range: [-106, 106],
                dtick: 20,
                title: { text: 'vs. Avg. Pace', font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: 11, color: MUTED_COLOR },
            },
            hovermode: 'closest',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#d9d6d0',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: '#fafaf9',
            paper_bgcolor: 'white',
            height: isMobile() ? 340 : 460,
            margin: { l: 60, r: 12, t: 8, b: 95 },
            annotations: [
                {
                    text: 'On pace (' + bandLabel + ' avg.)',
                    x: 12,
                    y: 0,
                    xanchor: 'right',
                    yanchor: 'bottom',
                    yshift: 4,
                    showarrow: false,
                    font: { family: FONT_SANS, size: 11, color: '#9ca3af' },
                },
                sourceAnnotation("Source: OMB SF-133", -0.30),
                ...obligationMonthLabels(false),
            ].filter(Boolean),
        };

        Plotly.newPlot('chart-multi-agency', traces, layout, plotlyConfigCompact());
    }

    // ── Single-Agency Spend-Down Chart ──

    function renderSpenddownChart(agencyKey, targetDiv, showPct, compact) {
        const cfg = DATA.config;
        const agency = cfg.agencies[agencyKey];
        const agencyData = DATA.spenddown[agencyKey];
        if (!agencyData) return;

        const ticks = tickArrays();
        const traces = [];
        const envelope = showPct ? agencyData.envelope_pct : agencyData.envelope_dollar;
        const highlightYears = cfg.highlight_years;
        const currentFy = cfg.current_fy;

        // Prior-year band
        if (envelope) {
            const months = envelope.months;
            const minV = envelope.min;
            const maxV = envelope.max;
            const medV = envelope.mean;
            const bandFys = envelope.band_fys;

            const validIdx = [];
            for (let i = 0; i < months.length; i++) {
                if (minV[i] != null) validIdx.push(i);
            }

            if (validIdx.length > 0) {
                const vm = validIdx.map(i => months[i]);
                const vlo = validIdx.map(i => minV[i]);
                const vhi = validIdx.map(i => maxV[i]);
                const vmd = validIdx.map(i => medV[i]);

                const bandLabel = bandFys.length > 1
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} range`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vm.concat([...vm].reverse()),
                    y: vhi.concat([...vlo].reverse()),
                    fill: 'toself',
                    fillcolor: PRIOR_RANGE_COLOR,
                    line: { width: 0 },
                    showlegend: true,
                    name: bandLabel,
                    hoverinfo: 'skip',
                });

                const medLabel = bandFys.length > 1
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} avg.`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vm,
                    y: vmd,
                    mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true,
                    name: medLabel,
                    hovertemplate: showPct ? '<b>Avg.</b>: %{y:.1f}% obligated<extra></extra>' : '<b>Avg.</b>: $%{y:.1f}B<extra></extra>',
                });
            }
        }

        // Highlighted prior years
        for (const fy of highlightYears.sort()) {
            if (fy === currentFy) continue;
            const yearData = agencyData.years[String(fy)];
            if (!yearData) continue;

            const yVals = showPct ? yearData.pct : yearData.dollars_b;
            const color = HIGHLIGHT_COLORS[fy] || '#94a3b8';
            const suffix = showPct ? '% obligated' : 'B';
            const prefix = showPct ? '' : '$';

            traces.push({
                x: yearData.months,
                y: yVals,
                mode: 'lines',
                name: `FY ${fy}`,
                line: { color: color, width: 1.8 },
                hovertemplate: `<b>FY ${fy}</b>: ${prefix}%{y:.1f}${suffix}<extra></extra>`,
            });
        }

        // Current FY
        const currentData = agencyData.years[String(currentFy)];
        if (currentData) {
            const yVals = showPct ? currentData.pct : currentData.dollars_b;
            const suffix = showPct ? '% obligated' : 'B';
            const prefix = showPct ? '' : '$';
            traces.push({
                x: currentData.months,
                y: yVals,
                mode: 'lines+markers',
                name: `FY ${currentFy}`,
                line: { color: agency.color, width: 3 },
                marker: { size: 6, color: agency.color },
                hovertemplate: `<b>FY ${currentFy}</b>: ${prefix}%{y:.1f}${suffix}<extra></extra>`,
            });
        }

        // Compute y-axis buffer as 3% of the data max so it's consistent across agencies
        let yMax = 0;
        for (const t of traces) {
            if (!t.y) continue;
            for (const v of t.y) {
                if (v != null && v > yMax) yMax = v;
            }
        }
        const yBuffer = Math.max(yMax * 0.03, 0.1);

        const height = compact ? 310 : (isMobile() ? 340 : 500);
        const yAxisLabel = showPct ? '% of Appropriation Obligated' : 'Cumulative Obligations ($B)';
        const detailSubtitle = showPct
            ? 'Cumulative obligations as a percentage of full-year appropriations.'
            : 'Cumulative obligations in billions of dollars by fiscal year month.';
        const mobile = isMobile();
        const detailTitle = mobile
            ? agency.display_name + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + detailSubtitle + '</span>'
            : agency.display_name + ' \u2014 Obligation Spend-Down'
            + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + detailSubtitle + '</span>';
        const annotations = compact ? [] : [sourceAnnotation("Source: OMB SF-133")].filter(Boolean);
        annotations.push(...obligationMonthLabels(compact));

        const layout = {
            title: compact ? {
                text: agency.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02,
                xanchor: 'left',
            } : {
                text: detailTitle,
                font: { family: FONT_SERIF, size: mobile ? 14 : 16, weight: 600, color: TEXT_COLOR },
                x: 0.01,
                xanchor: 'left',
            },
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals,
                ticktext: ticks.texts,
                tickfont: { size: 0.1, color: 'rgba(0,0,0,0)' },
                ticks: '',
                range: [-0.5, 12.5],
                showgrid: true,
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: showPct ? '%' : 'B',
                tickprefix: showPct ? '' : '$',
                tick0: 0,
                range: [-yBuffer, null],
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
                title: compact ? undefined : { text: yAxisLabel, font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: compact ? 9 : 11, color: MUTED_COLOR },
                bgcolor: 'rgba(0,0,0,0)',
            },
            hovermode: compact ? 'closest' : 'x unified',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#d9d6d0',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: '#fafaf9',
            paper_bgcolor: 'white',
            height: height,
            margin: {
                l: compact ? 45 : 60,
                r: 12,
                t: compact ? 38 : 72,
                b: compact ? 65 : 110,
            },
            annotations: annotations,
        };

        Plotly.newPlot(targetDiv, traces, layout, compact ? plotlyConfigCompact() : plotlyConfigFull());
    }

    // ── Small Multiples ──

    function renderSmallMultiples() {
        const cfg = DATA.config;
        const container = document.getElementById('agency-small-multiples');
        container.innerHTML = '';

        const bandFys = cfg.band_years_exclude;
        const allFys = Object.values(DATA.spenddown).flatMap(a => a.fiscal_years);
        const priorFys = [...new Set(allFys)].filter(y => !bandFys.includes(y)).sort();
        const bandLabel = priorFys.length > 1
            ? `FY${priorFys[0]}\u2013${priorFys[priorFys.length - 1]}`
            : `FY${priorFys[0]}`;

        const heading = document.getElementById('overview-agency-heading');
        heading.textContent = `Individual Agency Obligation Trends`;

        for (const key of Object.keys(cfg.agencies)) {
            if (!DATA.spenddown[key]) continue;

            const card = document.createElement('div');
            card.className = 'chart-card';
            const chartDiv = document.createElement('div');
            chartDiv.id = 'chart-mini-' + key;
            card.appendChild(chartDiv);
            container.appendChild(card);

            renderSpenddownChart(key, chartDiv.id, true, true);
        }
    }

    // ── Metric Cards ──

    function renderMetrics(agencyKey) {
        const summary = DATA.summaries[agencyKey];
        const container = document.getElementById('agency-metrics');
        const cfg = DATA.config;

        if (!summary || summary.error) {
            container.innerHTML = '';
            return;
        }

        function relPct(current, benchmark) {
            if (current == null || benchmark == null || benchmark === 0) return null;
            const rel = (current / benchmark - 1) * 100;
            const sign = rel >= 0 ? '+' : '';
            return { str: sign + rel.toFixed(0) + '%', dir: rel < 0 ? 'negative' : 'positive' };
        }

        const rows = [];

        // Row: % of appropriation
        if (summary.pct_obligated != null) {
            const r = summary.mean_prior_pct > 0 ? relPct(summary.pct_obligated, summary.mean_prior_pct) : null;
            rows.push({
                label: '% of Appropriation',
                current: summary.pct_obligated.toFixed(1) + '%',
                avg: summary.mean_prior_pct != null ? summary.mean_prior_pct.toFixed(1) + '%' : 'N/A',
                vs: r,
            });
        }

        // Row: obligated dollars
        if (summary.obligations_to_date != null) {
            const meanDollars = summary.mean_obligations || null;
            const r = meanDollars > 0 ? relPct(summary.obligations_to_date, meanDollars) : null;
            rows.push({
                label: 'Obligated',
                current: formatDollars(summary.obligations_to_date),
                avg: meanDollars != null ? formatDollars(meanDollars) : 'N/A',
                vs: r,
                vsSup: '†',
                footnote: true,
            });
        }

        const periodLabel = summary.latest_period || '';
        let html = `<table class="awards-summary-table">
            <thead><tr>
                <th></th>
                <th>To Date${periodLabel ? ' (' + periodLabel + ')' : ''}</th>
                <th>Avg at This Point</th>
                <th>vs. Avg</th>
            </tr></thead><tbody>`;

        for (const row of rows) {
            const vsClass = row.vs ? (row.vs.dir === 'negative' ? 'metric-neg' : 'metric-pos') : '';
            const vsStr = row.vs ? row.vs.str : '';
            const sup = row.vsSup ? '<sup>' + row.vsSup + '</sup>' : '';
            html += `<tr>
                <td class="awards-summary-label">${row.label}</td>
                <td>${row.current}</td>
                <td>${row.avg}</td>
                <td class="${vsClass}">${vsStr}${sup}</td>
            </tr>`;
        }

        html += '</tbody></table>';
        if (rows.some(r => r.footnote)) {
            html += '<div class="summary-table-footnotes"><p><sup>†</sup> Affected by changes in annual appropriations</p></div>';
        }
        container.innerHTML = html;
    }

    // ── Agency Detail (within Obligations tab) ──

    function renderAgencyDetail() {
        const select = document.getElementById('agency-select');
        const agencyKey = select.value;
        const mode = getActiveMode('obligations-view-mode');
        const showPct = mode === 'pct';

        renderMetrics(agencyKey);
        renderSpenddownChart(agencyKey, 'chart-agency-detail', showPct, false);
    }

    function initAgencySelect() {
        const select = document.getElementById('agency-select');
        const cfg = DATA.config;

        for (const key of Object.keys(cfg.agencies)) {
            if (!DATA.spenddown[key]) continue;
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = cfg.agencies[key].display_name;
            select.appendChild(opt);
        }

        select.addEventListener('change', renderAgencyDetail);
        initSegmentedControl('obligations-view-mode', function() { renderAgencyDetail(); });
    }

    // ── Export Buttons ──

    function initExport() {
        document.getElementById('btn-download-png').addEventListener('click', () => {
            const agencyKey = document.getElementById('agency-select').value;
            Plotly.downloadImage(document.getElementById('chart-agency-detail'), {
                format: 'png',
                width: 1200,
                height: 600,
                scale: 2,
                filename: agencyKey + '_spenddown',
            });
        });

        document.getElementById('btn-download-csv').addEventListener('click', () => {
            const agencyKey = document.getElementById('agency-select').value;
            const agencyData = DATA.spenddown[agencyKey];
            if (!agencyData) return;

            let csv = 'fiscal_year,period_month,obligations_pct,obligations_dollars_b\n';
            for (const [fy, yearData] of Object.entries(agencyData.years)) {
                for (let i = 0; i < yearData.months.length; i++) {
                    csv += `${fy},${yearData.months[i]},${yearData.pct[i]},${yearData.dollars_b[i]}\n`;
                }
            }

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = agencyKey + '_obligations.csv';
            a.click();
            URL.revokeObjectURL(url);
        });
    }

    function initAwardsExport() {
        document.getElementById('btn-awards-download-png').addEventListener('click', () => {
            const agencyKey = document.getElementById('awards-agency-select').value;
            Plotly.downloadImage(document.getElementById('chart-awards-detail'), {
                format: 'png',
                width: 1200,
                height: 600,
                scale: 2,
                filename: agencyKey + '_awards',
            });
        });

        document.getElementById('btn-awards-download-csv').addEventListener('click', () => {
            const agencyKey = document.getElementById('awards-agency-select').value;
            const agencyAwards = DATA.awards[agencyKey];
            if (!agencyAwards) return;

            const hasCounts = agencyAwards.source_type !== 'usaspending';
            let csv = hasCounts
                ? 'fiscal_year,fy_day,cumulative_count,cumulative_dollars_m\n'
                : 'fiscal_year,fy_day,cumulative_dollars_m\n';
            for (const [fy, yearData] of Object.entries(agencyAwards.years)) {
                for (let i = 0; i < yearData.fy_days.length; i++) {
                    const dollars = yearData.cumulative_dollars_m ? yearData.cumulative_dollars_m[i] : '';
                    if (hasCounts) {
                        const count = yearData.cumulative_count ? yearData.cumulative_count[i] : '';
                        csv += `${fy},${yearData.fy_days[i]},${count},${dollars}\n`;
                    } else {
                        csv += `${fy},${yearData.fy_days[i]},${dollars}\n`;
                    }
                }
            }

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = agencyKey + '_awards.csv';
            a.click();
            URL.revokeObjectURL(url);
        });
    }

    // ── Data Tables ──

    function renderTables() {
        const cfg = DATA.config;

        // Obligation time series — complete data for chart reproduction
        const table = document.getElementById('table-obligations-series');
        if (!table) return;
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const labels = fyMonthLabels();

        const cols = [
            { key: 'agency', label: 'Agency', format: v => cfg.agencies[v] ? cfg.agencies[v].display_name : v },
            { key: 'fy', label: 'FY', format: v => v, cls: 'number' },
            { key: 'month', label: 'Month', format: v => labels[v] || v },
            { key: 'obligations', label: 'Obligations ($)', format: v => v != null ? formatDollars(v * 1e9) : '\u2014', cls: 'number' },
            { key: 'appropriations', label: 'Appropriation ($)', format: v => v != null ? formatDollars(v * 1e9) : '\u2014', cls: 'number' },
            { key: 'pct', label: '% Obligated', format: v => v != null ? v.toFixed(1) + '%' : '\u2014', cls: 'number' },
        ];

        thead.innerHTML = '<tr>' + cols.map(c => '<th>' + c.label + '</th>').join('') + '</tr>';

        // Build rows from spenddown data
        const rows = [];
        for (const [agencyKey, agencyData] of Object.entries(DATA.spenddown)) {
            if (!cfg.agencies[agencyKey]) continue;
            for (const [fy, yearData] of Object.entries(agencyData.years)) {
                // Use per-year appropriation from build data
                var approp = yearData.appropriation;
                for (let i = 0; i < yearData.months.length; i++) {
                    if (yearData.months[i] === 1 && yearData.pct[i] === 0) continue; // skip anchor
                    rows.push({
                        agency: agencyKey,
                        fy: parseInt(fy),
                        month: yearData.months[i],
                        obligations: yearData.dollars_b[i],
                        appropriations: approp,
                        pct: yearData.pct[i],
                    });
                }
            }
        }

        rows.sort(function(a, b) {
            var cmp = (a.agency || '').localeCompare(b.agency || '');
            if (cmp !== 0) return cmp;
            cmp = a.fy - b.fy;
            if (cmp !== 0) return cmp;
            return a.month - b.month;
        });

        tbody.innerHTML = rows.map(function(row) {
            return '<tr>' + cols.map(function(c) {
                var val = row[c.key];
                var formatted = val != null ? c.format(val) : '\u2014';
                return '<td class="' + (c.cls || '') + '">' + formatted + '</td>';
            }).join('') + '</tr>';
        }).join('');
    }

    // ── Awards Data Tables ──

    function renderAwardsSeriesTable() {
        const awards = DATA.awards;
        const cfg = DATA.config;
        const table = document.getElementById('table-awards-series');
        if (!table || !awards) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        const cols = [
            { key: 'agency', label: 'Agency', format: function(v) { var a = cfg.agencies[v]; return a ? a.display_name : v; } },
            { key: 'fiscal_year', label: 'FY', format: function(v) { return v; }, cls: 'number' },
            { key: 'date', label: 'Date', format: function(v) { return v; } },
            { key: 'fy_day', label: 'FY Day', format: function(v) { return v; }, cls: 'number' },
            { key: 'count', label: 'Cumul. Awards', format: function(v) { return v != null && v > 0 ? v.toLocaleString() : '\u2014'; }, cls: 'number' },
            { key: 'dollars_m', label: 'Cumul. Dollars ($M)', format: function(v) { return v != null ? '$' + v.toFixed(1) + 'M' : '\u2014'; }, cls: 'number' },
            { key: 'pct_approp', label: '% of Approp', format: function(v) { return v != null ? v.toFixed(2) + '%' : '\u2014'; }, cls: 'number' },
        ];

        thead.innerHTML = '<tr>' + cols.map(function(c) { return '<th>' + c.label + '</th>'; }).join('') + '</tr>';

        // Build rows from all year traces, sampling at month boundaries for daily data
        var rows = [];
        for (var agencyKey in awards) {
            if (!cfg.agencies[agencyKey]) continue;
            var agencyData = awards[agencyKey];
            var isDaily = agencyData.source_type !== 'usaspending';

            for (var fi = 0; fi < agencyData.fiscal_years.length; fi++) {
                var fy = agencyData.fiscal_years[fi];
                var yearData = agencyData.years[String(fy)];
                if (!yearData) continue;

                if (isDaily && yearData.fy_days.length > 24) {
                    // Sample at month boundaries to keep table manageable
                    for (var m = 1; m <= 12; m++) {
                        var targetDay = AWARDS_FY_MONTH_ENDS[m];
                        var idx = -1;
                        for (var k = 0; k < yearData.fy_days.length; k++) {
                            if (yearData.fy_days[k] <= targetDay) idx = k;
                            else break;
                        }
                        if (idx < 0) continue;
                        rows.push({
                            agency: agencyKey,
                            fiscal_year: fy,
                            date: yearData.dates[idx],
                            fy_day: yearData.fy_days[idx],
                            count: yearData.cumulative_count ? yearData.cumulative_count[idx] : null,
                            dollars_m: yearData.cumulative_dollars_m[idx],
                            pct_approp: yearData.pct_of_approp ? yearData.pct_of_approp[idx] : null,
                        });
                    }
                } else {
                    // Monthly data — include all points
                    for (var i = 0; i < yearData.fy_days.length; i++) {
                        if (yearData.fy_days[i] === 1 && yearData.cumulative_dollars_m[i] === 0) continue;
                        rows.push({
                            agency: agencyKey,
                            fiscal_year: fy,
                            date: yearData.dates[i],
                            fy_day: yearData.fy_days[i],
                            count: yearData.cumulative_count ? yearData.cumulative_count[i] : null,
                            dollars_m: yearData.cumulative_dollars_m[i],
                            pct_approp: yearData.pct_of_approp ? yearData.pct_of_approp[i] : null,
                        });
                    }
                }
            }
        }

        rows.sort(function(a, b) {
            var cmp = (a.agency || '').localeCompare(b.agency || '');
            if (cmp !== 0) return cmp;
            cmp = a.fiscal_year - b.fiscal_year;
            if (cmp !== 0) return cmp;
            return a.fy_day - b.fy_day;
        });

        tbody.innerHTML = rows.map(function(row) {
            return '<tr>' + cols.map(function(c) {
                var val = row[c.key];
                var formatted = c.format(val);
                return '<td class="' + (c.cls || '') + '">' + formatted + '</td>';
            }).join('') + '</tr>';
        }).join('');
    }

    // ── Data Table CSV Downloads ──

    function downloadTableCSV(tableId, filename) {
        const table = document.getElementById(tableId);
        if (!table) return;
        const rows = table.querySelectorAll('tr');
        let csv = '';
        rows.forEach(function(row) {
            const cells = row.querySelectorAll('th, td');
            const vals = [];
            cells.forEach(function(cell) {
                let text = cell.textContent.trim();
                // Escape quotes and wrap if contains comma
                if (text.indexOf(',') !== -1 || text.indexOf('"') !== -1) {
                    text = '"' + text.replace(/"/g, '""') + '"';
                }
                vals.push(text);
            });
            csv += vals.join(',') + '\n';
        });
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }

    var obligTableBtn = document.getElementById('btn-obligations-table-csv');
    if (obligTableBtn) {
        obligTableBtn.addEventListener('click', function() {
            downloadTableCSV('table-obligations-series', 'obligation_series.csv');
        });
    }

    var awardsTableBtn = document.getElementById('btn-awards-table-csv');
    if (awardsTableBtn) {
        awardsTableBtn.addEventListener('click', function() {
            downloadTableCSV('table-awards-series', 'award_series.csv');
        });
    }

    // ── Awards: FY Day Ticks ──

    // fy_day for the 1st of each fiscal-year month (Oct 1 = day 1, Nov 1 = day 32, etc.)
    const AWARDS_FY_MONTH_DAYS = {
        1: 1, 2: 32, 3: 62, 4: 93, 5: 124, 6: 152,
        7: 183, 8: 213, 9: 244, 10: 274, 11: 305, 12: 336,
    };

    // fy_day for the last day of each fiscal-year month
    const AWARDS_FY_MONTH_ENDS = {
        1: 31, 2: 61, 3: 92, 4: 123, 5: 151, 6: 182,
        7: 212, 8: 243, 9: 273, 10: 304, 11: 335, 12: 365,
    };

    function awardTickArrays() {
        // Tick marks at month BOUNDARIES for the overview chart (fy_day scale).
        // ticktext is empty; visible labels come from annotations at midpoints.
        const vals = [];
        for (let i = 1; i <= 12; i++) {
            vals.push(AWARDS_FY_MONTH_DAYS[i]);
        }
        vals.push(AWARDS_FY_MONTH_ENDS[12] + 1); // 366 = boundary after Sep 30
        return { vals, texts: vals.map(() => '') };
    }

    function awardMonthLabels(compact) {
        // Month name annotations centered between boundary ticks.
        // On mobile, show only every other month to avoid crowding.
        const labels = fyMonthLabels();
        const mobile = isMobile();
        const annots = [];
        for (let i = 1; i <= 12; i++) {
            if (mobile && !compact && i % 2 === 0) continue;
            annots.push({
                text: labels[i],
                x: (AWARDS_FY_MONTH_DAYS[i] + AWARDS_FY_MONTH_ENDS[i]) / 2,
                xref: 'x',
                y: 0,
                yref: 'paper',
                yanchor: 'top',
                yshift: -4,
                xanchor: 'center',
                showarrow: false,
                font: { family: FONT_SANS, size: compact ? 10 : (mobile ? 9 : 11), color: MUTED_COLOR },
            });
        }
        return annots;
    }

    function fyDayToMonth(day) {
        const labels = fyMonthLabels();
        for (let i = 12; i >= 1; i--) {
            if (day >= AWARDS_FY_MONTH_DAYS[i]) return labels[i];
        }
        return '';
    }

    // Map fy_day (1–366) to a date string in a fixed reference fiscal year
    // (FY2001: Oct 2000 – Sep 2001).  Using real dates lets the Plotly date
    // axis format hover headers as month names automatically.
    function fyDayToRefDate(day) {
        const d = new Date(Date.UTC(2000, 9, 1)); // Oct 1, 2000
        d.setUTCDate(d.getUTCDate() + day - 1);
        return d.toISOString().slice(0, 10);
    }

    // ── Awards: Multi-Agency Pace Chart ──

    function renderAwardsMultiChart() {
        const awards = DATA.awards;
        const cfg = DATA.config;
        if (!awards) return;

        const ticks = awardTickArrays();
        const traces = [];
        const currentFy = cfg.current_fy;

        // 0% "on pace" reference line — spans full FY (Oct 1 = day 1 to Sep 30 = day 365)
        traces.push({
            x: [1, 365],
            y: [0, 0],
            mode: 'lines',
            line: { color: '#9ca3af', width: 1, dash: 'dot' },
            showlegend: false,
            hoverinfo: 'skip',
        });

        for (const agencyKey of Object.keys(awards)) {
            const agencyAwards = awards[agencyKey];
            const agencyCfg = cfg.agencies[agencyKey];
            if (!agencyCfg) continue;

            const currentData = agencyAwards.years[String(currentFy)];
            if (!currentData) continue;

            // Use pct_of_approp for cross-agency comparison (normalizes by budget size)
            const envelope = agencyAwards.envelope_pct || agencyAwards.envelope_dollars;
            const yCol = agencyAwards.envelope_pct ? 'pct_of_approp' : 'cumulative_dollars_m';

            if (!envelope) continue;

            const xVals = [];
            const yVals = [];

            for (let i = 0; i < currentData.fy_days.length; i++) {
                const day = currentData.fy_days[i];
                const currVal = currentData[yCol] ? currentData[yCol][i] : null;
                if (currVal == null) continue;

                // Interpolate envelope mean at this day
                let closestMean = null;
                const eDays = envelope.fy_days;
                const eMean = envelope.mean;
                if (day <= eDays[0]) {
                    closestMean = eMean[0];
                } else if (day >= eDays[eDays.length - 1]) {
                    closestMean = eMean[eMean.length - 1];
                } else {
                    for (let j = 0; j < eDays.length - 1; j++) {
                        if (eDays[j] <= day && day <= eDays[j + 1]) {
                            const frac = (day - eDays[j]) / (eDays[j + 1] - eDays[j]);
                            closestMean = eMean[j] + frac * (eMean[j + 1] - eMean[j]);
                            break;
                        }
                    }
                }

                // Skip when mean is below 0.05% (ratio is noisy with tiny denominators)
                if (closestMean == null || closestMean < 0.05) continue;

                xVals.push(day);
                yVals.push(Math.round((currVal / closestMean * 100 - 100) * 100) / 100);
            }

            if (xVals.length === 0) continue;

            // Downsample daily data (NIH/NSF) to ~4 evenly spaced points per month
            const isDaily = agencyAwards.source_type !== 'usaspending';
            let plotX = xVals;
            let plotY = yVals;
            let tailX = null, tailY = null;
            if (isDaily && xVals.length > 14) {
                // Build target days: month boundaries + quartiles within each month
                const targets = [];
                for (let m = 1; m <= 12; m++) {
                    const s = AWARDS_FY_MONTH_DAYS[m];
                    const e = AWARDS_FY_MONTH_ENDS[m];
                    targets.push(s); // 1st day
                    targets.push(Math.round(s + (e - s) * 0.25));
                    targets.push(Math.round(s + (e - s) * 0.5));
                    targets.push(Math.round(s + (e - s) * 0.75));
                }
                // Interpolate at each target milestone day
                plotX = [];
                plotY = [];
                for (const t of targets) {
                    if (t < xVals[0] || t > xVals[xVals.length - 1]) continue;
                    // Find surrounding points
                    let lo = 0;
                    for (let k = 0; k < xVals.length; k++) {
                        if (xVals[k] <= t) lo = k; else break;
                    }
                    if (xVals[lo] === t || lo === xVals.length - 1) {
                        plotX.push(xVals[lo]);
                        plotY.push(yVals[lo]);
                    } else {
                        const hi = lo + 1;
                        const frac = (t - xVals[lo]) / (xVals[hi] - xVals[lo]);
                        plotX.push(t);
                        plotY.push(yVals[lo] + frac * (yVals[hi] - yVals[lo]));
                    }
                }
                // If latest data extends past the last milestone, add a line-only tail
                const lastX = xVals[xVals.length - 1];
                const lastY = yVals[yVals.length - 1];
                if (plotX.length > 0 && plotX[plotX.length - 1] !== lastX) {
                    tailX = [plotX[plotX.length - 1], lastX];
                    tailY = [plotY[plotY.length - 1], lastY];
                }
            }

            // For monthly USASpending with a provisional last point, split off the tail
            const provIdx = currentData.provisional_index;
            if (!isDaily && provIdx != null && plotX.length > 1) {
                tailX = [plotX[plotX.length - 2], plotX[plotX.length - 1]];
                tailY = [plotY[plotY.length - 2], plotY[plotY.length - 1]];
                plotX = plotX.slice(0, -1);
                plotY = plotY.slice(0, -1);
            }

            // Dashed lead-in from Oct 1 (day 1) at midpoint to first real data point
            if (plotX.length > 0) {
                traces.push({
                    x: [1, plotX[0]],
                    y: [0, plotY[0]],
                    mode: 'lines',
                    line: { color: agencyCfg.color, width: 1.5, dash: 'dot' },
                    opacity: 0.35,
                    showlegend: false,
                    hoverinfo: 'skip',
                });
            }

            traces.push({
                x: plotX,
                y: plotY,
                mode: 'lines+markers',
                name: agencyCfg.display_name,
                line: { color: agencyCfg.color, width: 2.5 },
                marker: { size: isDaily ? 4 : 5, color: agencyCfg.color },
                text: plotX.map(d => fyDayToMonth(d)),
                customdata: plotY.map(v => fmtSigned(v)),
                hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{customdata} vs. avg. pace<extra></extra>',
                hoverlabel: { bordercolor: agencyCfg.color },
            });
            // Line-only tail extending beyond last milestone (no dot)
            if (tailX) {
                traces.push({
                    x: tailX,
                    y: tailY,
                    mode: 'lines',
                    name: agencyCfg.display_name,
                    line: { color: agencyCfg.color, width: 2.5 },
                    text: tailX.map(d => fyDayToMonth(d)),
                    customdata: tailY.map(v => fmtSigned(v)),
                    hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{customdata} vs. avg. pace<extra></extra>',
                    hoverlabel: { bordercolor: agencyCfg.color },
                    showlegend: false,
                });
            }
        }

        // Set HTML chart title
        const awardsTitleEl = document.getElementById('awards-multi-title');
        if (awardsTitleEl) {
            awardsTitleEl.textContent = `FY${currentFy} Award-Making Pace vs. Historical Average`;
        }

        const layout = {
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals,
                ticktext: ticks.texts,
                ticks: '',
                range: [-15, 380],
                showgrid: true,
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: '%',
                tickformat: '+d',
                range: [-106, 106],
                dtick: 20,
                title: { text: 'vs. Avg. Pace', font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: 11, color: MUTED_COLOR },
            },
            hovermode: 'closest',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#d9d6d0',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: '#fafaf9',
            paper_bgcolor: 'white',
            height: isMobile() ? 340 : 460,
            margin: { l: 60, r: 12, t: 8, b: 95 },
            annotations: [
                {
                    text: 'On pace (historical avg.)',
                    x: 365,
                    y: 0,
                    xanchor: 'right',
                    yanchor: 'bottom',
                    yshift: 4,
                    showarrow: false,
                    font: { family: FONT_SANS, size: 11, color: '#9ca3af' },
                },
                sourceAnnotation('Source: NIH Reporter, NSF Awards, USASpending', -0.30),
                ...awardMonthLabels(false),
            ].filter(Boolean),
        };

        Plotly.newPlot('chart-awards-multi', traces, layout, plotlyConfigCompact());
    }

    // ── Awards: Cumulative Chart (Single Agency) ──
    // mode: 'pct' (% of appropriation), 'dollars', or 'counts'

    function renderAwardsCumulativeChart(agencyKey, targetDiv, mode, compact) {
        const awards = DATA.awards;
        const cfg = DATA.config;
        if (!awards || !awards[agencyKey]) return;

        const agencyAwards = awards[agencyKey];
        const agencyCfg = cfg.agencies[agencyKey];
        // Use the obligations tick scheme (0–12 month indices) so x-unified
        // hover headers show month names.  All fy_day x-data is converted to
        // Convert fy_day x-data to reference dates via fyDayToRefDate() so the
        // Plotly date axis formats hover headers as month names automatically.
        const traces = [];
        const currentFy = cfg.current_fy;

        const yCol = mode === 'counts' ? 'cumulative_count'
                   : mode === 'dollars' ? 'cumulative_dollars_m'
                   : 'pct_of_approp';
        const envelope = mode === 'counts' ? agencyAwards.envelope_count
                       : mode === 'dollars' ? agencyAwards.envelope_dollars
                       : agencyAwards.envelope_pct;
        const isPct = mode === 'pct';
        const isDollars = mode === 'dollars';

        // Envelope band
        if (envelope) {
            const days = envelope.fy_days.map(fyDayToRefDate);
            const minV = envelope.min;
            const maxV = envelope.max;
            const medV = envelope.mean;
            const bandFys = envelope.band_fys;

            const validIdx = [];
            for (let i = 0; i < days.length; i++) {
                if (minV[i] != null) validIdx.push(i);
            }

            if (validIdx.length > 0) {
                const vd = validIdx.map(i => days[i]);
                const vlo = validIdx.map(i => minV[i]);
                const vhi = validIdx.map(i => maxV[i]);
                const vmd = validIdx.map(i => medV[i]);

                const bandLabel = bandFys.length > 1
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} range`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vd.concat([...vd].reverse()),
                    y: vhi.concat([...vlo].reverse()),
                    fill: 'toself',
                    fillcolor: PRIOR_RANGE_COLOR,
                    line: { width: 0 },
                    showlegend: true,
                    name: bandLabel,
                    hoverinfo: 'skip',
                });

                const medLabel = bandFys.length > 1
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} avg.`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vd,
                    y: vmd,
                    mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true,
                    name: medLabel,
                    hovertemplate: isPct ? '<b>Avg.</b>: %{y:.2f}% of approp<extra></extra>'
                        : isDollars ? '<b>Avg.</b>: $%{y:,.0f}M awarded<extra></extra>'
                        : '<b>Avg.</b>: %{y:,.0f} awards<extra></extra>',
                });
            }
        }

        const hoverFmt = isPct ? '%{y:.2f}% of approp' : isDollars ? '$%{y:,.0f}M awarded' : '%{y:,.0f} awards';

        // Daily sources (NIH, NSF) have many points — use lines only, no markers
        const isDaily = agencyAwards.source_type !== 'usaspending';

        // Highlighted prior years
        const highlightYears = cfg.highlight_years || [];
        for (const fy of highlightYears.sort()) {
            if (fy === currentFy) continue;
            const yearData = agencyAwards.years[String(fy)];
            if (!yearData) continue;

            const color = HIGHLIGHT_COLORS[fy] || '#94a3b8';
            traces.push({
                x: yearData.fy_days.map(fyDayToRefDate),
                y: yearData[yCol],
                mode: 'lines',
                name: `FY ${fy}`,
                line: { color: color, width: 1.8 },
                hovertemplate: `<b>FY ${fy}</b>: ${hoverFmt}<extra></extra>`,
            });
        }

        // Current FY
        const currentData = agencyAwards.years[String(currentFy)];
        if (currentData) {
            const provIdx = currentData.provisional_index;
            const allX = currentData.fy_days.map(fyDayToRefDate);
            const allY = currentData[yCol];

            if (provIdx != null && provIdx > 0) {
                // Split into complete portion (with markers) and provisional tail (line only)
                traces.push({
                    x: allX.slice(0, provIdx),
                    y: allY.slice(0, provIdx),
                    mode: isDaily ? 'lines' : 'lines+markers',
                    name: `FY ${currentFy}`,
                    line: { color: agencyCfg.color, width: 3 },
                    marker: { size: isDaily ? 0 : 6, color: agencyCfg.color },
                    hovertemplate: `<b>FY ${currentFy}</b>: ${hoverFmt}<extra></extra>`,
                });
                // Provisional tail — connects last complete point to provisional point
                traces.push({
                    x: allX.slice(provIdx - 1, provIdx + 1),
                    y: allY.slice(provIdx - 1, provIdx + 1),
                    mode: 'lines',
                    name: `FY ${currentFy}`,
                    line: { color: agencyCfg.color, width: 3 },
                    hovertemplate: `<b>FY ${currentFy}</b>: ${hoverFmt}<extra></extra>`,
                    showlegend: false,
                });
            } else {
                traces.push({
                    x: allX,
                    y: allY,
                    mode: isDaily ? 'lines' : 'lines+markers',
                    name: `FY ${currentFy}`,
                    line: { color: agencyCfg.color, width: 3 },
                    marker: { size: isDaily ? 0 : 6, color: agencyCfg.color },
                    hovertemplate: `<b>FY ${currentFy}</b>: ${hoverFmt}<extra></extra>`,
                });
            }
        }

        // Compute y-axis buffer as 3% of the data max so it's consistent across agencies
        let yMaxAward = 0;
        for (const t of traces) {
            if (!t.y) continue;
            for (const v of t.y) {
                if (v != null && v > yMaxAward) yMaxAward = v;
            }
        }
        const yBufferAward = Math.max(yMaxAward * 0.03, 0.01);

        const height = compact ? 310 : (isMobile() ? 340 : 500);
        const sourceLabel = SOURCE_LABELS[agencyAwards.source_type] || agencyAwards.source_type;
        const awardAnnotations = compact ? [] : [sourceAnnotation('Source: ' + sourceLabel)].filter(Boolean);

        const awardYLabel = isPct ? '% of Appropriation Awarded' : isDollars ? 'Cumulative Awards ($M)' : 'Cumulative Award Count';
        const awardsDetailSubtitle = mode === 'counts'
            ? 'Cumulative new award count over the fiscal year.'
            : isDollars ? 'Cumulative new award dollars over the fiscal year.'
            : 'Cumulative grant dollars as a percentage of the full-year appropriation.';
        const mobileAwd = isMobile();
        const awardsDetailTitle = mobileAwd
            ? agencyCfg.display_name + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + awardsDetailSubtitle + '</span>'
            : agencyCfg.display_name + ' \u2014 New Awards'
            + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + awardsDetailSubtitle + '</span>';

        const layout = {
            title: compact ? {
                text: agencyCfg.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02,
                xanchor: 'left',
            } : {
                text: awardsDetailTitle,
                font: { family: FONT_SERIF, size: mobileAwd ? 14 : 16, weight: 600, color: TEXT_COLOR },
                x: 0.01,
                xanchor: 'left',
            },
            xaxis: Object.assign({}, baseAxisStyle(), {
                type: 'date',
                dtick: 'M1',
                tickformat: '%b',
                ticklabelmode: 'period',
                hoverformat: '%b',
                range: ['2000-09-25', '2001-10-05'],
                showgrid: true,
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: isPct ? '%' : isDollars ? 'M' : '',
                tickprefix: isDollars ? '$' : '',
                range: [-yBufferAward, null],
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
                title: compact ? undefined : { text: awardYLabel, font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: compact ? 9 : 11, color: MUTED_COLOR },
                bgcolor: 'rgba(0,0,0,0)',
            },
            hovermode: compact ? 'closest' : 'x unified',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#d9d6d0',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: '#fafaf9',
            paper_bgcolor: 'white',
            height: height,
            margin: {
                l: compact ? 45 : 60,
                r: 12,
                t: compact ? 38 : 72,
                b: compact ? 65 : 110,
            },
            annotations: awardAnnotations,
        };

        Plotly.newPlot(targetDiv, traces, layout, compact ? plotlyConfigCompact() : plotlyConfigFull());
    }

    // ── Awards: Small Multiples ──

    function renderAwardsSmallMultiples() {
        const awards = DATA.awards;
        if (!awards) return;

        const container = document.getElementById('awards-small-multiples');
        container.innerHTML = '';

        for (const key of Object.keys(awards)) {
            if (!DATA.config.agencies[key]) continue;

            const card = document.createElement('div');
            card.className = 'chart-card';
            const chartDiv = document.createElement('div');
            chartDiv.id = 'chart-awards-mini-' + key;
            card.appendChild(chartDiv);
            container.appendChild(card);

            // Default to pct_of_approp in small multiples
            renderAwardsCumulativeChart(key, chartDiv.id, 'pct', true);
        }
    }

    // ── Awards: Metric Cards ──

    function renderAwardsMetrics(agencyKey) {
        const container = document.getElementById('awards-metrics');
        const awards = DATA.awards;
        const summary = DATA.awards_summary;
        const cfg = DATA.config;

        if (!awards || !awards[agencyKey]) {
            container.innerHTML = '';
            return;
        }

        const agencyAwards = awards[agencyKey];
        const hasCounts = agencyAwards && agencyAwards.source_type !== 'usaspending';
        const summ = summary ? summary[agencyKey] : null;

        if (!summ) {
            container.innerHTML = '';
            return;
        }

        function relPct(current, benchmark) {
            if (current == null || benchmark == null || benchmark === 0) return null;
            const rel = (current / benchmark - 1) * 100;
            const sign = rel >= 0 ? '+' : '';
            return { str: sign + rel.toFixed(0) + '%', dir: rel < 0 ? 'negative' : 'positive' };
        }

        const rows = [];

        // Row: % of appropriation
        if (summ.cumul_pct_approp != null) {
            const r = summ.mean_pct_approp > 0 ? relPct(summ.cumul_pct_approp, summ.mean_pct_approp) : null;
            rows.push({
                label: '% of Appropriation',
                current: summ.cumul_pct_approp.toFixed(1) + '%',
                avg: summ.mean_pct_approp != null ? summ.mean_pct_approp.toFixed(1) + '%' : 'N/A',
                vs: r,
            });
        }

        // Row: award count (NIH/NSF only)
        if (hasCounts && summ.cumul_count != null) {
            const r = summ.mean_count > 0 ? relPct(summ.cumul_count, summ.mean_count) : null;
            rows.push({
                label: 'Award Count',
                current: summ.cumul_count.toLocaleString(),
                avg: summ.mean_count != null ? Math.round(summ.mean_count).toLocaleString() : 'N/A',
                vs: r,
                vsSup: '†',
            });
        }

        // Row: award dollars
        if (summ.cumul_dollars != null) {
            const r = summ.mean_dollars > 0 ? relPct(summ.cumul_dollars, summ.mean_dollars) : null;
            rows.push({
                label: 'Award Dollars',
                current: formatDollars(summ.cumul_dollars),
                avg: summ.mean_dollars != null ? formatDollars(summ.mean_dollars) : 'N/A',
                vs: r,
                vsSup: '‡',
            });
        }

        let dateLabel = '';
        if (summ.latest_date) {
            const [y, m, d] = summ.latest_date.split('-');
            const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            dateLabel = months[parseInt(m, 10) - 1] + ' ' + parseInt(d, 10);
        }
        let html = `<table class="awards-summary-table">
            <thead><tr>
                <th></th>
                <th>To Date${dateLabel ? ' (' + dateLabel + ')' : ''}</th>
                <th>Avg at This Point</th>
                <th>vs. Avg</th>
            </tr></thead><tbody>`;

        for (const row of rows) {
            const vsClass = row.vs ? (row.vs.dir === 'negative' ? 'metric-neg' : 'metric-pos') : '';
            const vsStr = row.vs ? row.vs.str : 'N/A';
            const sup = row.vsSup ? '<sup>' + row.vsSup + '</sup>' : '';
            html += `<tr>
                <td class="awards-summary-label">${row.label}</td>
                <td>${row.current}</td>
                <td>${row.avg}</td>
                <td class="${vsClass}">${vsStr}${sup}</td>
            </tr>`;
        }

        html += '</tbody></table>';
        html += '<div class="summary-table-footnotes">';
        if (hasCounts) html += '<p><sup>†</sup> Affected by changes in prevalence of multi-year funding</p>';
        html += '<p><sup>‡</sup> Affected by changes in annual appropriations</p>';
        html += '</div>';
        container.innerHTML = html;
    }

    // ── Awards: Detail View ──

    function renderAwardsDetail() {
        const awards = DATA.awards;
        if (!awards) return;

        const select = document.getElementById('awards-agency-select');
        const agencyKey = select.value;
        const agencyAwards = awards[agencyKey];

        // Only NIH/NSF have meaningful counts
        const hasCounts = agencyAwards && agencyAwards.source_type !== 'usaspending';
        const mode = getActiveMode('awards-view-mode');

        // Disable/enable counts button based on agency
        const countsBtn = document.querySelector('#awards-view-mode .seg-btn[data-mode="counts"]');
        if (countsBtn) {
            countsBtn.disabled = !hasCounts;
            countsBtn.style.display = hasCounts ? '' : 'none';
        }

        // If counts is selected but not available, fallback to pct
        const effectiveMode = (mode === 'counts' && !hasCounts) ? 'pct' : mode;

        renderAwardsMetrics(agencyKey);
        renderAwardsCumulativeChart(agencyKey, 'chart-awards-detail', effectiveMode, false);
    }

    // ── Awards: Tab Init ──

    function initAwardsTab() {
        const awards = DATA.awards;
        if (!awards) {
            // Hide tab button if no awards data
            const btn = document.querySelector('.tab-btn[data-tab="awards"]');
            if (btn) btn.style.display = 'none';
            // Hide awards option in data selector
            const dataSelect = document.getElementById('data-section-select');
            if (dataSelect) {
                const opt = dataSelect.querySelector('option[value="awards"]');
                if (opt) opt.style.display = 'none';
            }
            return;
        }

        const select = document.getElementById('awards-agency-select');
        for (const key of Object.keys(awards)) {
            const agencyCfg = DATA.config.agencies[key];
            if (!agencyCfg) continue;
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = agencyCfg.display_name;
            select.appendChild(opt);
        }

        select.addEventListener('change', () => {
            // Reset to pct when switching agencies (counts may not be available)
            const agencyAwards = awards[select.value];
            const hasCounts = agencyAwards && agencyAwards.source_type !== 'usaspending';
            if (!hasCounts && getActiveMode('awards-view-mode') === 'counts') {
                const pctBtn = document.querySelector('#awards-view-mode .seg-btn[data-mode="pct"]');
                if (pctBtn) {
                    document.querySelectorAll('#awards-view-mode .seg-btn').forEach(b => b.classList.remove('active'));
                    pctBtn.classList.add('active');
                }
            }
            renderAwardsDetail();
        });
        initSegmentedControl('awards-view-mode', function() { renderAwardsDetail(); });

        renderAwardsMultiChart();
        renderAwardsSmallMultiples();
        renderAwardsDetail();
    }

    // ── USASpending Unified Comparison Tab ──

    function initUnifiedTab() {
        var unified = DATA.awards_unified;
        var summary = DATA.awards_unified_summary;
        if (!unified) return;

        // Tab button stays hidden (style="display:none" in HTML)
        // To re-enable, uncomment: document.getElementById('tab-btn-unified').style.display = '';

        var cfg = DATA.config;
        var currentFy = cfg.current_fy;

        // Populate agency select
        var select = document.getElementById('unified-agency-select');
        for (var key of Object.keys(unified)) {
            if (!cfg.agencies[key]) continue;
            var opt = document.createElement('option');
            opt.value = key;
            opt.textContent = cfg.agencies[key].display_name;
            select.appendChild(opt);
        }

        function renderDetail() {
            var agencyKey = select.value;
            var mode = getActiveMode('unified-view-mode');
            // Render metrics
            renderUnifiedMetrics(agencyKey);
            // Render detail chart — reuse awards cumulative renderer with unified data
            renderUnifiedCumulativeChart(agencyKey, 'chart-unified-detail', mode, false);
        }

        select.addEventListener('change', renderDetail);
        initSegmentedControl('unified-view-mode', renderDetail);

        // Multi-agency chart
        renderUnifiedMultiChart();
        // Small multiples
        renderUnifiedSmallMultiples();
        // Detail
        renderDetail();
    }

    function renderUnifiedMultiChart() {
        var unified = DATA.awards_unified;
        var cfg = DATA.config;
        if (!unified) return;

        var ticks = awardTickArrays();
        var traces = [];
        var currentFy = cfg.current_fy;

        traces.push({
            x: [1, 365], y: [0, 0],
            mode: 'lines', line: { color: '#9ca3af', width: 1, dash: 'dot' },
            showlegend: false, hoverinfo: 'skip',
        });

        for (var agencyKey of Object.keys(unified)) {
            var agencyData = unified[agencyKey];
            var agencyCfg = cfg.agencies[agencyKey];
            if (!agencyCfg) continue;
            var currentData = agencyData.years[String(currentFy)];
            if (!currentData) continue;
            var envelope = agencyData.envelope_pct || agencyData.envelope_dollars;
            var yCol = agencyData.envelope_pct ? 'pct_of_approp' : 'cumulative_dollars_m';
            if (!envelope) continue;

            var eDays = envelope.fy_days;
            var eMean = envelope.mean;
            var xVals = [], yVals = [];
            for (var i = 0; i < currentData.fy_days.length; i++) {
                var day = currentData.fy_days[i];
                var currVal = currentData[yCol] ? currentData[yCol][i] : null;
                if (currVal == null) continue;
                // Interpolate envelope mean at this day
                var closestMean = null;
                if (day <= eDays[0]) {
                    closestMean = eMean[0];
                } else if (day >= eDays[eDays.length - 1]) {
                    closestMean = eMean[eMean.length - 1];
                } else {
                    for (var j = 0; j < eDays.length - 1; j++) {
                        if (eDays[j] <= day && day <= eDays[j + 1]) {
                            var frac = (day - eDays[j]) / (eDays[j + 1] - eDays[j]);
                            closestMean = eMean[j] + frac * (eMean[j + 1] - eMean[j]);
                            break;
                        }
                    }
                }
                if (closestMean == null || closestMean < 0.05) continue;
                xVals.push(day);
                yVals.push(Math.round((currVal / closestMean * 100 - 100) * 100) / 100);
            }
            if (xVals.length === 0) continue;

            // Split provisional tail for USASpending agencies
            var provIdx = currentData.provisional_index;
            var plotX = xVals, plotY = yVals;
            var tailX = null, tailY = null;
            if (provIdx != null && plotX.length > 1) {
                tailX = [plotX[plotX.length - 2], plotX[plotX.length - 1]];
                tailY = [plotY[plotY.length - 2], plotY[plotY.length - 1]];
                plotX = plotX.slice(0, -1);
                plotY = plotY.slice(0, -1);
            }

            traces.push({
                x: plotX, y: plotY,
                mode: 'lines+markers',
                name: agencyCfg.display_name,
                line: { color: agencyCfg.color, width: 2.5 },
                marker: { size: 5, color: agencyCfg.color },
                text: plotX.map(function(d) { return fyDayToMonth(d); }),
                customdata: plotY.map(function(v) { return fmtSigned(v); }),
                hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{customdata} vs. avg. pace<extra></extra>',
                hoverlabel: { bordercolor: agencyCfg.color },
            });
            if (tailX) {
                traces.push({
                    x: tailX, y: tailY,
                    mode: 'lines',
                    name: agencyCfg.display_name,
                    line: { color: agencyCfg.color, width: 2.5 },
                    text: tailX.map(function(d) { return fyDayToMonth(d); }),
                    customdata: tailY.map(function(v) { return fmtSigned(v); }),
                    hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{customdata} vs. avg. pace<extra></extra>',
                    hoverlabel: { bordercolor: agencyCfg.color },
                    showlegend: false,
                });
            }
        }

        var titleEl = document.getElementById('unified-multi-title');
        if (titleEl) titleEl.textContent = 'FY' + currentFy + ' Award Pace (USASpending) vs. Historical Average';

        var layout = {
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals, ticktext: ticks.texts, ticks: '',
                range: [-15, 380], showgrid: true,
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: '%', tickformat: '+d', range: [-106, 106], dtick: 20,
                title: { text: 'vs. Avg. Pace', font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: { orientation: 'h', yanchor: 'top', y: -0.18, xanchor: 'center', x: 0.5,
                      font: { family: FONT_SANS, size: 11, color: MUTED_COLOR } },
            hovermode: 'closest',
            hoverlabel: { bgcolor: 'white', bordercolor: '#d9d6d0', font: { family: FONT_SANS, size: 12, color: TEXT_COLOR } },
            plot_bgcolor: '#fafaf9', paper_bgcolor: 'white',
            height: isMobile() ? 340 : 460,
            margin: { l: 60, r: 12, t: 8, b: 95 },
            annotations: [
                { text: 'On pace (historical avg.)', x: 365, y: 0, xanchor: 'right', yanchor: 'bottom', yshift: 4,
                  showarrow: false, font: { family: FONT_SANS, size: 11, color: '#9ca3af' } },
                sourceAnnotation('Source: USASpending.gov', -0.30),
                ...awardMonthLabels(false),
            ].filter(Boolean),
        };
        Plotly.newPlot('chart-unified-multi', traces, layout, plotlyConfigCompact());
    }

    function renderUnifiedSmallMultiples() {
        var unified = DATA.awards_unified;
        if (!unified) return;
        var container = document.getElementById('unified-small-multiples');
        container.innerHTML = '';
        for (var key of Object.keys(unified)) {
            if (!DATA.config.agencies[key]) continue;
            var card = document.createElement('div');
            card.className = 'chart-card';
            var chartDiv = document.createElement('div');
            chartDiv.id = 'chart-unified-mini-' + key;
            card.appendChild(chartDiv);
            container.appendChild(card);
            renderUnifiedCumulativeChart(key, chartDiv.id, 'pct', true);
        }
    }

    function renderUnifiedCumulativeChart(agencyKey, targetDiv, mode, compact) {
        var unified = DATA.awards_unified;
        var cfg = DATA.config;
        if (!unified || !unified[agencyKey]) return;

        var agencyAwards = unified[agencyKey];
        var agencyCfg = cfg.agencies[agencyKey];
        var traces = [];
        var currentFy = cfg.current_fy;
        var isPct = mode === 'pct';
        var isDollars = mode === 'dollars';
        var yCol = isPct ? 'pct_of_approp' : 'cumulative_dollars_m';
        var envelope = isPct ? agencyAwards.envelope_pct : agencyAwards.envelope_dollars;

        if (envelope) {
            var days = envelope.fy_days.map(fyDayToRefDate);
            var minV = envelope.min, maxV = envelope.max, medV = envelope.mean;
            var bandFys = envelope.band_fys;
            var validIdx = [];
            for (var i = 0; i < days.length; i++) { if (minV[i] != null) validIdx.push(i); }
            if (validIdx.length > 0) {
                var vd = validIdx.map(function(i) { return days[i]; });
                var vlo = validIdx.map(function(i) { return minV[i]; });
                var vhi = validIdx.map(function(i) { return maxV[i]; });
                var vmd = validIdx.map(function(i) { return medV[i]; });
                var bandLabel = bandFys.length > 1
                    ? 'FY' + bandFys[0] + '\u2013' + bandFys[bandFys.length - 1] + ' range'
                    : 'FY' + bandFys[0];
                traces.push({
                    x: vd.concat([].concat(vd).reverse()),
                    y: vhi.concat([].concat(vlo).reverse()),
                    fill: 'toself', fillcolor: PRIOR_RANGE_COLOR,
                    line: { width: 0 }, showlegend: true, name: bandLabel, hoverinfo: 'skip',
                });
                var medLabel = bandFys.length > 1
                    ? 'FY' + bandFys[0] + '\u2013' + bandFys[bandFys.length - 1] + ' avg.'
                    : 'FY' + bandFys[0];
                traces.push({
                    x: vd, y: vmd, mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true, name: medLabel,
                    hovertemplate: isPct ? '<b>Avg.</b>: %{y:.2f}% of approp<extra></extra>'
                        : '<b>Avg.</b>: $%{y:,.0f}M awarded<extra></extra>',
                });
            }
        }

        var hoverFmt = isPct ? '%{y:.2f}% of approp' : '$%{y:,.0f}M awarded';
        var highlightYears = cfg.highlight_years || [];
        for (var hi = 0; hi < highlightYears.length; hi++) {
            var fy = highlightYears[hi];
            if (fy === currentFy) continue;
            var yearData = agencyAwards.years[String(fy)];
            if (!yearData) continue;
            traces.push({
                x: yearData.fy_days.map(fyDayToRefDate), y: yearData[yCol],
                mode: 'lines', name: 'FY ' + fy,
                line: { color: HIGHLIGHT_COLORS[fy] || '#94a3b8', width: 1.8 },
                hovertemplate: '<b>FY ' + fy + '</b>: ' + hoverFmt + '<extra></extra>',
            });
        }

        var currentData = agencyAwards.years[String(currentFy)];
        if (currentData) {
            var uProvIdx = currentData.provisional_index;
            var uAllX = currentData.fy_days.map(fyDayToRefDate);
            var uAllY = currentData[yCol];

            if (uProvIdx != null && uProvIdx > 0) {
                traces.push({
                    x: uAllX.slice(0, uProvIdx), y: uAllY.slice(0, uProvIdx),
                    mode: 'lines+markers', name: 'FY ' + currentFy,
                    line: { color: agencyCfg.color, width: 3 },
                    marker: { size: 6, color: agencyCfg.color },
                    hovertemplate: '<b>FY ' + currentFy + '</b>: ' + hoverFmt + '<extra></extra>',
                });
                traces.push({
                    x: uAllX.slice(uProvIdx - 1, uProvIdx + 1),
                    y: uAllY.slice(uProvIdx - 1, uProvIdx + 1),
                    mode: 'lines', name: 'FY ' + currentFy,
                    line: { color: agencyCfg.color, width: 3 },
                    hovertemplate: '<b>FY ' + currentFy + '</b>: ' + hoverFmt + '<extra></extra>',
                    showlegend: false,
                });
            } else {
                traces.push({
                    x: uAllX, y: uAllY,
                    mode: 'lines+markers', name: 'FY ' + currentFy,
                    line: { color: agencyCfg.color, width: 3 },
                    marker: { size: 6, color: agencyCfg.color },
                    hovertemplate: '<b>FY ' + currentFy + '</b>: ' + hoverFmt + '<extra></extra>',
                });
            }
        }

        var yMaxU = 0;
        for (var ti = 0; ti < traces.length; ti++) {
            if (!traces[ti].y) continue;
            for (var vi = 0; vi < traces[ti].y.length; vi++) {
                if (traces[ti].y[vi] != null && traces[ti].y[vi] > yMaxU) yMaxU = traces[ti].y[vi];
            }
        }
        var yBuf = Math.max(yMaxU * 0.03, 0.01);
        var height = compact ? 310 : (isMobile() ? 340 : 500);
        var yAxisLabel = isPct ? '% of Appropriation Awarded' : 'Cumulative Awards ($M)';
        var annotations = compact ? [] : [sourceAnnotation('Source: USASpending.gov')].filter(Boolean);

        var layout = {
            title: compact ? {
                text: agencyCfg.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02, xanchor: 'left',
            } : {
                text: agencyCfg.display_name + ' \u2014 USASpending',
                font: { family: FONT_SERIF, size: isMobile() ? 14 : 16, weight: 600, color: TEXT_COLOR },
                x: 0.01, xanchor: 'left',
            },
            xaxis: Object.assign({}, baseAxisStyle(), {
                type: 'date', dtick: 'M1', tickformat: '%b', ticklabelmode: 'period',
                hoverformat: '%b', range: ['2000-09-25', '2001-10-05'], showgrid: true,
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: isPct ? '%' : 'M', tickprefix: isDollars ? '$' : '',
                range: [-yBuf, null],
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
                title: compact ? undefined : { text: yAxisLabel, font: { family: FONT_SANS, size: 11, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: { orientation: 'h', yanchor: 'top', y: -0.18, xanchor: 'center', x: 0.5,
                      font: { family: FONT_SANS, size: compact ? 9 : 11, color: MUTED_COLOR }, bgcolor: 'rgba(0,0,0,0)' },
            hovermode: compact ? 'closest' : 'x unified',
            hoverlabel: { bgcolor: 'white', bordercolor: '#d9d6d0', font: { family: FONT_SANS, size: 12, color: TEXT_COLOR } },
            plot_bgcolor: '#fafaf9', paper_bgcolor: 'white',
            height: height,
            margin: { l: compact ? 45 : 60, r: 12, t: compact ? 38 : 72, b: compact ? 65 : 110 },
            annotations: annotations,
        };
        Plotly.newPlot(targetDiv, traces, layout, compact ? plotlyConfigCompact() : plotlyConfigFull());
    }

    function renderUnifiedMetrics(agencyKey) {
        var container = document.getElementById('unified-metrics');
        var summary = DATA.awards_unified_summary;
        var cfg = DATA.config;
        if (!summary || !summary[agencyKey]) {
            container.innerHTML = '<div class="metric-card"><div class="metric-value">No data</div></div>';
            return;
        }
        var summ = summary[agencyKey];

        function card(label, value, delta, deltaDir) {
            var deltaHtml = '';
            if (delta) deltaHtml = '<div class="metric-delta ' + (deltaDir || '') + '">' + delta + '</div>';
            return '<div class="metric-card"><div class="metric-label">' + label + '</div><div class="metric-value">' + value + '</div>' + deltaHtml + '</div>';
        }

        var html = '';
        var dollars = summ.cumul_dollars != null ? formatDollars(summ.cumul_dollars) : 'N/A';
        html += card('Awarded through ' + (summ.latest_date || 'latest'), dollars);

        var pctApprop = summ.cumul_pct_approp != null ? summ.cumul_pct_approp.toFixed(1) + '%' : 'N/A';
        html += card('% of Appropriation', pctApprop);

        var yoyStr = 'N/A', yoyDir = '';
        if (summ.cumul_pct_approp != null && summ.prior_year_pct_approp != null) {
            var diff = summ.cumul_pct_approp - summ.prior_year_pct_approp;
            var rel = summ.prior_year_pct_approp !== 0 ? (diff / summ.prior_year_pct_approp * 100) : 0;
            yoyStr = (diff >= 0 ? '+' : '') + diff.toFixed(1) + 'pp (' + (rel >= 0 ? '+' : '') + rel.toFixed(1) + '%)';
            yoyDir = diff < 0 ? 'negative' : 'positive';
        }
        html += card('vs. FY' + (cfg.current_fy - 1), yoyStr, null, yoyDir);

        var medStr = 'N/A', medDir = '';
        if (summ.cumul_pct_approp != null && summ.mean_pct_approp != null) {
            var diff2 = summ.cumul_pct_approp - summ.mean_pct_approp;
            var rel2 = summ.mean_pct_approp !== 0 ? (diff2 / summ.mean_pct_approp * 100) : 0;
            medStr = (diff2 >= 0 ? '+' : '') + diff2.toFixed(1) + 'pp (' + (rel2 >= 0 ? '+' : '') + rel2.toFixed(1) + '%)';
            medDir = diff2 < 0 ? 'negative' : 'positive';
        }
        html += card('vs. Avg.', medStr, null, medDir);

        container.innerHTML = html;
        var cards = container.querySelectorAll('.metric-card');
        if (cards[2] && yoyDir) cards[2].querySelector('.metric-value').classList.add(yoyDir === 'negative' ? 'metric-neg' : 'metric-pos');
        if (cards[3] && medDir) cards[3].querySelector('.metric-value').classList.add(medDir === 'negative' ? 'metric-neg' : 'metric-pos');
    }

    // ── Initialize ──

    async function init() {
        try {
            const resp = await fetch('data/site_data.json');
            DATA = await resp.json();
        } catch (e) {
            document.querySelector('main').innerHTML =
                '<div style="padding:3rem;text-align:center;color:#991b1b;">Error loading data. Run <code>python3 build.py</code> first.</div>';
            return;
        }

        initTabs();
        initDataSectionToggle();
        initAgencySelect();
        initExport();
        initAwardsExport();
        renderDataBadge();
        renderMultiAgencyChart();
        renderSmallMultiples();
        renderAgencyDetail();
        renderTables();
        renderAwardsSeriesTable();
        initAwardsTab();
        initUnifiedTab();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
