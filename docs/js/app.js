/* ================================================================
   Science Agency Spend-Down Tracker — Frontend
   ================================================================ */

(function () {
    'use strict';

    // ── Shared chart styling ──
    const FONT_SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif";
    const FONT_SERIF = "Source Serif 4, Georgia, serif";
    const TEXT_COLOR = "#111827";
    const MUTED_COLOR = "#6b7280";
    const GRID_COLOR = "rgba(0,0,0,0.04)";
    const AXIS_LINE_COLOR = "#e5e7eb";
    const PRIOR_RANGE_COLOR = "rgba(160, 175, 200, 0.15)";
    const HIGHLIGHT_COLORS = { 2025: "#94a3b8" };

    // ── Agency Descriptions ──
    const AGENCY_DESCRIPTIONS = {
        NIH: "The largest public funder of biomedical research, distributing most of its budget as extramural grants across 27 institutes and centers.",
        NSF: "Funds fundamental research and education across all non-medical fields of science and engineering through competitive grants.",
        DOE_SC: "The nation's largest sponsor of basic physical-sciences research, operating 17 national laboratories.",
        NASA_SCI: "Funds Earth science, planetary exploration, astrophysics, and heliophysics missions and research.",
        USDA_RD: "Spans the Agricultural Research Service (intramural) and National Institute of Food and Agriculture (extramural grants).",
    };

    let DATA = null;

    // ── Utilities ──

    function formatDollars(amount) {
        if (amount == null) return "N/A";
        const abs = Math.abs(amount);
        if (abs >= 1e9) return "$" + (amount / 1e9).toFixed(2) + "B";
        if (abs >= 1e6) return "$" + (amount / 1e6).toFixed(1) + "M";
        return "$" + amount.toLocaleString('en-US', { maximumFractionDigits: 0 });
    }

    function fyMonthLabels() {
        return { 1: "Oct", 2: "Nov", 3: "Dec", 4: "Jan", 5: "Feb", 6: "Mar",
                 7: "Apr", 8: "May", 9: "Jun", 10: "Jul", 11: "Aug", 12: "Sep" };
    }

    function tickArrays() {
        const labels = fyMonthLabels();
        const vals = [];
        const texts = [];
        for (let i = 1; i <= 12; i++) {
            vals.push(i);
            texts.push(labels[i]);
        }
        return { vals, texts };
    }

    function sourceAnnotation(yOffset) {
        return {
            text: "Source: OMB SF-133",
            xref: 'paper',
            yref: 'paper',
            x: 1,
            y: yOffset || -0.19,
            xanchor: 'right',
            yanchor: 'top',
            showarrow: false,
            font: { family: FONT_SANS, size: 9, color: '#9ca3af' },
        };
    }

    function baseAxisStyle() {
        return {
            gridcolor: GRID_COLOR,
            zeroline: false,
            showline: false,
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
            parts.push('Data through ' + cfg.latest_period_label + ' FY' + cfg.current_fy);
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

        if (buildEl && cfg.build_date) {
            buildEl.textContent = 'Site built ' + cfg.build_date;
        }
    }

    // ── Tab Navigation ──

    function initTabs() {
        const btns = document.querySelectorAll('.tab-btn');
        const panels = document.querySelectorAll('.tab-panel');

        btns.forEach(btn => {
            btn.addEventListener('click', () => {
                btns.forEach(b => {
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                });
                panels.forEach(p => p.classList.remove('active'));
                btn.classList.add('active');
                btn.setAttribute('aria-selected', 'true');
                document.getElementById('tab-' + btn.dataset.tab).classList.add('active');

                setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
            });
        });
    }

    // ── Multi-Agency Overview Chart ──

    function renderMultiAgencyChart() {
        const cfg = DATA.config;
        const multiData = DATA.multi_agency;
        const ticks = tickArrays();
        const traces = [];

        // 100% reference line
        traces.push({
            x: [1, 12],
            y: [100, 100],
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
            const vals = trace.pct_of_median;

            // Lead-in (Oct-Nov) — faded dashed
            const leadX = months.filter(m => m <= 2);
            const leadY = vals.slice(0, leadX.length);
            if (leadX.length >= 2) {
                traces.push({
                    x: leadX,
                    y: leadY,
                    mode: 'lines',
                    line: { color: agency.color, width: 1.5, dash: 'dot' },
                    opacity: 0.35,
                    showlegend: false,
                    hoverinfo: 'skip',
                });
            }

            // Main segment
            const mainStartIdx = leadX.length - 1;
            const mainX = months.slice(mainStartIdx);
            const mainY = vals.slice(mainStartIdx);
            const labels = fyMonthLabels();
            const mainText = mainX.map(m => labels[m] || '');

            traces.push({
                x: mainX,
                y: mainY,
                text: mainText,
                mode: 'lines+markers',
                name: agency.display_name,
                line: { color: agency.color, width: 2.5 },
                marker: { size: 5, color: agency.color },
                hovertemplate: '<b>' + agency.display_name + '</b><br>%{text}: %{y:.1f}% of median pace<extra></extra>',
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
            titleEl.textContent = `FY${cfg.current_fy} Obligation Pace vs. ${bandLabel} Median`;
        }

        const layout = {
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals,
                ticktext: ticks.texts,
                range: [0.5, 12.5],
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: '%',
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.12,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: 11, color: MUTED_COLOR },
            },
            hovermode: 'closest',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#e5e7eb',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            height: 460,
            margin: { l: 52, r: 12, t: 8, b: 85 },
            annotations: [
                {
                    text: bandLabel + ' median',
                    x: 12,
                    y: 100,
                    xanchor: 'right',
                    yanchor: 'bottom',
                    yshift: 4,
                    showarrow: false,
                    font: { family: FONT_SANS, size: 10, color: '#9ca3af' },
                },
                sourceAnnotation(-0.2),
            ],
        };

        Plotly.newPlot('chart-multi-agency', traces, layout, { displayModeBar: false, responsive: true });
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
            const medV = envelope.median;
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
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} median`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vm,
                    y: vmd,
                    mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true,
                    name: medLabel,
                    hovertemplate: '<b>Median</b>: %{y:.1f}' + (showPct ? '%' : 'B') + '<extra></extra>',
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

        const height = compact ? 340 : 440;
        const annotations = compact ? [] : [sourceAnnotation(-0.2)];

        const layout = {
            title: compact ? {
                text: agency.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02,
                xanchor: 'left',
            } : undefined,
            xaxis: Object.assign({}, baseAxisStyle(), {
                tickvals: ticks.vals,
                ticktext: ticks.texts,
                range: [0.5, 12.5],
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
            }),
            yaxis: Object.assign({}, baseAxisStyle(), {
                ticksuffix: showPct ? '%' : 'B',
                tickprefix: showPct ? '' : '$',
                rangemode: 'tozero',
                tick0: 0,
                range: [showPct ? -4 : -0.5, null],
                tickfont: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: compact ? -0.12 : -0.12,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: compact ? 9 : 10, color: MUTED_COLOR },
                bgcolor: 'rgba(0,0,0,0)',
            },
            hovermode: 'x unified',
            hoverlabel: {
                bgcolor: 'white',
                bordercolor: '#e5e7eb',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            height: height,
            margin: {
                l: compact ? 45 : 52,
                r: 12,
                t: compact ? 38 : 8,
                b: compact ? 65 : 80,
            },
            annotations: annotations,
        };

        Plotly.newPlot(targetDiv, traces, layout, { displayModeBar: false, responsive: true });
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
        heading.textContent = `Individual Agency Trends`;

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
            container.innerHTML = '<div class="metric-card"><div class="metric-value">No data</div></div>';
            return;
        }

        function card(label, value, delta, deltaDir) {
            let deltaHtml = '';
            if (delta && delta !== 'N/A') {
                deltaHtml = `<div class="metric-delta ${deltaDir || ''}">${delta}</div>`;
            }
            return `<div class="metric-card">
                <div class="metric-label">${label}</div>
                <div class="metric-value">${value}</div>
                ${deltaHtml}
            </div>`;
        }

        const pct = summary.pct_obligated;
        const pctStr = pct != null ? pct.toFixed(1) + '%' : 'N/A';

        let yoyStr = 'N/A';
        let yoyDir = '';
        if (summary.yoy_diff != null && summary.yoy_rel != null) {
            const yoySign = summary.yoy_diff >= 0 ? '+' : '';
            const yoyRelSign = summary.yoy_rel >= 0 ? '+' : '';
            yoyStr = yoySign + summary.yoy_diff.toFixed(1) + 'pp (' + yoyRelSign + summary.yoy_rel.toFixed(1) + '%)';
            yoyDir = summary.yoy_diff < 0 ? 'negative' : 'positive';
        }

        let medStr = 'N/A';
        let medDir = '';
        if (summary.median_diff != null && summary.median_rel != null) {
            const medSign = summary.median_diff >= 0 ? '+' : '';
            const medRelSign = summary.median_rel >= 0 ? '+' : '';
            medStr = medSign + summary.median_diff.toFixed(1) + 'pp (' + medRelSign + summary.median_rel.toFixed(1) + '%)';
            medDir = summary.median_diff < 0 ? 'negative' : 'positive';
        }

        container.innerHTML =
            card(`FY${cfg.current_fy} Appropriation`, formatDollars(summary.appropriations)) +
            card(`Obligated through ${summary.latest_period}`, formatDollars(summary.obligations_to_date)) +
            card('Percent Obligated', pctStr) +
            card(`vs. FY${cfg.current_fy - 1}`, yoyStr, null, yoyDir) +
            card('vs. Median', medStr, null, medDir);

        const cards = container.querySelectorAll('.metric-card');
        if (cards[3] && yoyDir) {
            cards[3].querySelector('.metric-value').classList.add(yoyDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
        if (cards[4] && medDir) {
            cards[4].querySelector('.metric-value').classList.add(medDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
    }

    // ── Agency Detail Tab ──

    function renderAgencyDetail() {
        const select = document.getElementById('agency-select');
        const agencyKey = select.value;
        const showDollars = document.getElementById('toggle-dollars').checked;
        const agency = DATA.config.agencies[agencyKey];

        // Update description
        const descEl = document.getElementById('agency-description');
        if (descEl) {
            descEl.textContent = AGENCY_DESCRIPTIONS[agencyKey] || '';
        }

        // Update chart title
        const chartTitle = document.getElementById('agency-chart-title');
        const chartSubtitle = document.getElementById('agency-chart-subtitle');
        if (chartTitle && agency) {
            chartTitle.textContent = agency.display_name;
            if (chartSubtitle) {
                chartSubtitle.textContent = showDollars
                    ? 'Cumulative obligations in billions of dollars by fiscal year month.'
                    : 'Cumulative obligations as a percentage of full-year appropriations.';
            }
        }

        renderMetrics(agencyKey);
        renderSpenddownChart(agencyKey, 'chart-agency-detail', !showDollars, false);
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
        document.getElementById('toggle-dollars').addEventListener('change', renderAgencyDetail);
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

    // ── Data Tables ──

    function renderTables() {
        const cfg = DATA.config;
        const tables = DATA.tables;

        // Appropriations summary
        const appropTable = document.getElementById('table-approp');
        const appropHead = appropTable.querySelector('thead');
        const appropBody = appropTable.querySelector('tbody');

        const appropCols = [
            { key: 'agency', label: 'Agency', format: v => cfg.agencies[v] ? cfg.agencies[v].display_name : v },
            { key: 'fiscal_year', label: 'FY', format: v => v },
            { key: 'approp_disc_raw', label: 'Disc. Approp', format: formatDollars, cls: 'number' },
            { key: 'approp_mand_raw', label: 'Mand. Approp', format: formatDollars, cls: 'number' },
            { key: 'approp_disc_net', label: 'Net Disc.', format: formatDollars, cls: 'number' },
            { key: 'budget_authority', label: 'Budget Auth.', format: formatDollars, cls: 'number' },
            { key: 'obligations_total', label: 'Obligations', format: formatDollars, cls: 'number' },
            { key: 'outlays_net', label: 'Outlays', format: formatDollars, cls: 'number' },
        ];

        appropHead.innerHTML = '<tr>' + appropCols.map(c => `<th>${c.label}</th>`).join('') + '</tr>';

        const appropRows = [...tables.approp_summary].sort((a, b) => {
            const agencyCmp = (a.agency || '').localeCompare(b.agency || '');
            if (agencyCmp !== 0) return agencyCmp;
            return (b.fiscal_year || 0) - (a.fiscal_year || 0);
        });

        appropBody.innerHTML = appropRows.map(row =>
            '<tr>' + appropCols.map(c => {
                const val = row[c.key];
                const formatted = val != null ? c.format(val) : '\u2014';
                return `<td class="${c.cls || ''}">${formatted}</td>`;
            }).join('') + '</tr>'
        ).join('');

        // YoY comparison
        const yoyTable = document.getElementById('table-yoy');
        const yoyHead = yoyTable.querySelector('thead');
        const yoyBody = yoyTable.querySelector('tbody');

        const yoyHeading = document.getElementById('yoy-heading');
        yoyHeading.textContent = `Year-over-Year Comparison`;

        const yoyCols = [
            { key: 'display_name', label: 'Agency', format: v => v },
            { key: 'period_label', label: 'Period', format: v => v },
            { key: 'current_pct', label: `FY${cfg.current_fy}`, format: v => v != null ? v.toFixed(1) + '%' : '\u2014', cls: 'number' },
            { key: 'prior_year_pct', label: `FY${cfg.current_fy - 1}`, format: v => v != null ? v.toFixed(1) + '%' : '\u2014', cls: 'number' },
            { key: 'yoy_diff', label: 'Diff (pp)', format: v => v != null ? (v >= 0 ? '+' : '') + v.toFixed(1) : '\u2014', cls: 'number' },
            { key: 'median_prior_pct', label: 'Median', format: v => v != null ? v.toFixed(1) + '%' : '\u2014', cls: 'number' },
        ];

        yoyHead.innerHTML = '<tr>' + yoyCols.map(c => `<th>${c.label}</th>`).join('') + '</tr>';

        yoyBody.innerHTML = tables.yoy_comparison.map(row =>
            '<tr>' + yoyCols.map(c => {
                const val = row[c.key];
                const formatted = val != null ? c.format(val) : '\u2014';
                return `<td class="${c.cls || ''}">${formatted}</td>`;
            }).join('') + '</tr>'
        ).join('');
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
        initAgencySelect();
        initExport();
        renderDataBadge();
        renderMultiAgencyChart();
        renderSmallMultiples();
        renderAgencyDetail();
        renderTables();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
