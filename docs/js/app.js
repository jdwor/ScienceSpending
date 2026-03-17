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
        var defaultY = isMobile() ? -0.38 : -0.28;
        return {
            text: text || "Source: OMB SF-133",
            xref: 'paper',
            yref: 'paper',
            x: 1,
            y: yOffset || defaultY,
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
            parts.push('Obligations through ' + cfg.latest_period_label + ' FY' + cfg.current_fy);
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
                parts.push('Awards through ' + monthName + ' FY' + cfg.current_fy);
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

        // 100% reference line — spans full FY (start of Oct to end of Sep)
        traces.push({
            x: [0, 12],
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
            const vals = trace.pct_of_mean;

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
                hovertemplate: '<b>' + agency.display_name + '</b><br>%{text}: %{y:.1f}% of avg. pace<extra></extra>',
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
                range: [-6, 200],
                dtick: 20,
                title: { text: '% of Avg. Pace', font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
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
            height: 460,
            margin: { l: 60, r: 12, t: 8, b: isMobile() ? 110 : 95 },
            annotations: [
                {
                    text: bandLabel + ' avg.',
                    x: 12,
                    y: 100,
                    xanchor: 'right',
                    yanchor: 'bottom',
                    yshift: 4,
                    showarrow: false,
                    font: { family: FONT_SANS, size: 10, color: '#9ca3af' },
                },
                sourceAnnotation("Source: OMB SF-133", -0.30),
                ...obligationMonthLabels(false),
            ],
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
                    hovertemplate: '<b>Avg.</b>: %{y:.1f}' + (showPct ? '%' : 'B') + '<extra></extra>',
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

        const height = compact ? 310 : 500;
        const yAxisLabel = showPct ? '% of Appropriation Obligated' : 'Cumulative Obligations ($B)';
        const detailSubtitle = showPct
            ? 'Cumulative obligations as a percentage of full-year appropriations.'
            : 'Cumulative obligations in billions of dollars by fiscal year month.';
        const detailTitle = agency.display_name + ' \u2014 Obligation Spend-Down'
            + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + detailSubtitle + '</span>';
        const annotations = compact ? [] : [sourceAnnotation("Source: OMB SF-133")];
        annotations.push(...obligationMonthLabels(compact));

        const layout = {
            title: compact ? {
                text: agency.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02,
                xanchor: 'left',
            } : {
                text: detailTitle,
                font: { family: FONT_SERIF, size: 16, weight: 600, color: TEXT_COLOR },
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
                title: compact ? undefined : { text: yAxisLabel, font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: compact ? 9 : 10, color: MUTED_COLOR },
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
                b: compact ? 65 : (isMobile() ? 125 : 110),
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
        if (summary.mean_diff != null && summary.mean_rel != null) {
            const medSign = summary.mean_diff >= 0 ? '+' : '';
            const medRelSign = summary.mean_rel >= 0 ? '+' : '';
            medStr = medSign + summary.mean_diff.toFixed(1) + 'pp (' + medRelSign + summary.mean_rel.toFixed(1) + '%)';
            medDir = summary.mean_diff < 0 ? 'negative' : 'positive';
        }

        container.innerHTML =
            card(`FY${cfg.current_fy} Appropriation`, formatDollars(summary.appropriations)) +
            card(`Obligated through ${summary.latest_period}`, formatDollars(summary.obligations_to_date)) +
            card('Percent Obligated', pctStr) +
            card(`vs. FY${cfg.current_fy - 1}`, yoyStr, null, yoyDir) +
            card('vs. Avg.', medStr, null, medDir);

        const cards = container.querySelectorAll('.metric-card');
        if (cards[3] && yoyDir) {
            cards[3].querySelector('.metric-value').classList.add(yoyDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
        if (cards[4] && medDir) {
            cards[4].querySelector('.metric-value').classList.add(medDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
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

            let csv = 'fiscal_year,fy_day,cumulative_count,cumulative_dollars_m\n';
            for (const [fy, yearData] of Object.entries(agencyAwards.years)) {
                for (let i = 0; i < yearData.fy_days.length; i++) {
                    const count = yearData.cumulative_count ? yearData.cumulative_count[i] : '';
                    const dollars = yearData.cumulative_dollars_m ? yearData.cumulative_dollars_m[i] : '';
                    csv += `${fy},${yearData.fy_days[i]},${count},${dollars}\n`;
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
            // Get appropriation from summaries
            const summary = DATA.summaries[agencyKey];
            const approp = summary ? summary.appropriations : null;
            for (const [fy, yearData] of Object.entries(agencyData.years)) {
                for (let i = 0; i < yearData.months.length; i++) {
                    if (yearData.months[i] === 1 && yearData.pct[i] === 0) continue; // skip anchor
                    rows.push({
                        agency: agencyKey,
                        fy: parseInt(fy),
                        month: yearData.months[i],
                        obligations: yearData.dollars_b[i],
                        appropriations: approp != null ? approp / 1e9 : null,
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

        // 100% reference line — spans full FY (Oct 1 = day 1 to Sep 30 = day 365)
        traces.push({
            x: [1, 365],
            y: [100, 100],
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

                // Find closest envelope day <= this day
                let closestMean = null;
                for (let j = envelope.fy_days.length - 1; j >= 0; j--) {
                    if (envelope.fy_days[j] <= day) {
                        closestMean = envelope.mean[j];
                        break;
                    }
                }

                // Skip when mean is below 0.05% (ratio is noisy with tiny denominators)
                if (closestMean == null || closestMean < 0.05) continue;

                xVals.push(day);
                yVals.push(currVal / closestMean * 100);
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

            traces.push({
                x: plotX,
                y: plotY,
                mode: 'lines+markers',
                name: agencyCfg.display_name,
                line: { color: agencyCfg.color, width: 2.5 },
                marker: { size: isDaily ? 4 : 5, color: agencyCfg.color },
                text: plotX.map(d => fyDayToMonth(d)),
                hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{y:.1f}% of avg. pace<extra></extra>',
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
                    hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{y:.1f}% of avg. pace<extra></extra>',
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
                range: [-6, 200],
                dtick: 20,
                title: { text: '% of Avg. Pace', font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
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
            height: 460,
            margin: { l: 60, r: 12, t: 8, b: isMobile() ? 110 : 95 },
            annotations: [
                {
                    text: 'Historical avg.',
                    x: 365,
                    y: 100,
                    xanchor: 'right',
                    yanchor: 'bottom',
                    yshift: 4,
                    showarrow: false,
                    font: { family: FONT_SANS, size: 10, color: '#9ca3af' },
                },
                sourceAnnotation('Source: NIH Reporter, NSF Awards, USASpending', -0.30),
                ...awardMonthLabels(false),
            ],
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
                    hovertemplate: isPct ? '<b>Avg.</b>: %{y:.2f}%<extra></extra>'
                        : '<b>Avg.</b>: %{y:,.0f}<extra></extra>',
                });
            }
        }

        const hoverFmt = isPct ? '%{y:.2f}% of approp' : isDollars ? '$%{y:,.0f}M' : '%{y:,.0f}';

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
            traces.push({
                x: currentData.fy_days.map(fyDayToRefDate),
                y: currentData[yCol],
                mode: isDaily ? 'lines' : 'lines+markers',
                name: `FY ${currentFy}`,
                line: { color: agencyCfg.color, width: 3 },
                marker: { size: isDaily ? 0 : 6, color: agencyCfg.color },
                hovertemplate: `<b>FY ${currentFy}</b>: ${hoverFmt}<extra></extra>`,
            });
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

        const height = compact ? 310 : 500;
        const sourceLabel = SOURCE_LABELS[agencyAwards.source_type] || agencyAwards.source_type;
        const awardAnnotations = compact ? [] : [sourceAnnotation('Source: ' + sourceLabel)];

        const awardYLabel = isPct ? '% of Appropriation Awarded' : isDollars ? 'Cumulative Awards ($M)' : 'Cumulative Award Count';
        const awardsDetailSubtitle = mode === 'counts'
            ? 'Cumulative new award count over the fiscal year.'
            : isDollars ? 'Cumulative new award dollars over the fiscal year.'
            : 'Cumulative grant dollars as a percentage of the full-year appropriation.';
        const awardsDetailTitle = agencyCfg.display_name + ' \u2014 New Awards'
            + '<br><span style="font-size:11px;font-weight:400;color:#6b7280;font-family:' + FONT_SANS + '">' + awardsDetailSubtitle + '</span>';

        const layout = {
            title: compact ? {
                text: agencyCfg.display_name,
                font: { family: FONT_SANS, size: 12, weight: 600, color: TEXT_COLOR },
                x: 0.02,
                xanchor: 'left',
            } : {
                text: awardsDetailTitle,
                font: { family: FONT_SERIF, size: 16, weight: 600, color: TEXT_COLOR },
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
                title: compact ? undefined : { text: awardYLabel, font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
            }),
            legend: {
                orientation: 'h',
                yanchor: 'top',
                y: -0.18,
                xanchor: 'center',
                x: 0.5,
                font: { family: FONT_SANS, size: compact ? 9 : 10, color: MUTED_COLOR },
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
                b: compact ? 65 : (isMobile() ? 125 : 110),
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
            container.innerHTML = '<div class="metric-card"><div class="metric-value">No data</div></div>';
            return;
        }

        const agencyAwards = awards[agencyKey];
        const hasCounts = agencyAwards && agencyAwards.source_type !== 'usaspending';
        const summ = summary ? summary[agencyKey] : null;

        function card(label, value, delta, deltaDir) {
            let deltaHtml = '';
            if (delta) {
                deltaHtml = `<div class="metric-delta ${deltaDir || ''}">${delta}</div>`;
            }
            return `<div class="metric-card">
                <div class="metric-label">${label}</div>
                <div class="metric-value">${value}</div>
                ${deltaHtml}
            </div>`;
        }

        if (!summ) {
            container.innerHTML = card('Status', 'No summary data');
            return;
        }

        let html = '';

        // Card 1: Current FY cumulative new award dollars
        const dollars = summ.cumul_dollars != null ? formatDollars(summ.cumul_dollars) : 'N/A';
        html += card(`Awarded through ${summ.latest_date || 'latest'}`, dollars);

        // Card 3: Percent of appropriation awarded
        const pctApprop = summ.cumul_pct_approp != null ? summ.cumul_pct_approp.toFixed(1) + '%' : 'N/A';
        html += card('Percent Awarded', pctApprop);

        // Card 4: vs. prior year (pp + relative %)
        let yoyStr = 'N/A';
        let yoyDir = '';
        if (summ.cumul_pct_approp != null && summ.prior_year_pct_approp != null) {
            const diff = summ.cumul_pct_approp - summ.prior_year_pct_approp;
            const rel = summ.prior_year_pct_approp !== 0 ? (diff / summ.prior_year_pct_approp * 100) : 0;
            const diffSign = diff >= 0 ? '+' : '';
            const relSign = rel >= 0 ? '+' : '';
            yoyStr = diffSign + diff.toFixed(1) + 'pp (' + relSign + rel.toFixed(1) + '%)';
            yoyDir = diff < 0 ? 'negative' : 'positive';
        }
        html += card(`vs. FY${cfg.current_fy - 1}`, yoyStr, null, yoyDir);

        // Card 5: vs. historical mean (pp + relative %)
        let medStr = 'N/A';
        let medDir = '';
        if (summ.cumul_pct_approp != null && summ.mean_pct_approp != null) {
            const diff = summ.cumul_pct_approp - summ.mean_pct_approp;
            const rel = summ.mean_pct_approp !== 0 ? (diff / summ.mean_pct_approp * 100) : 0;
            const diffSign = diff >= 0 ? '+' : '';
            const relSign = rel >= 0 ? '+' : '';
            medStr = diffSign + diff.toFixed(1) + 'pp (' + relSign + rel.toFixed(1) + '%)';
            medDir = diff < 0 ? 'negative' : 'positive';
        }
        html += card('vs. Avg.', medStr, null, medDir);

        // Card 6: Award count (NIH/NSF only — inherently normalized)
        if (hasCounts && summ.cumul_count) {
            const count = summ.cumul_count.toLocaleString();
            const meanCount = summ.mean_count ? Math.round(summ.mean_count).toLocaleString() : null;
            let countDelta = '';
            let countDir = '';
            if (meanCount != null && summ.mean_count) {
                countDelta = 'vs. avg. of ' + meanCount;
                countDir = summ.cumul_count < summ.mean_count ? 'negative' : 'positive';
            }
            html += card(`FY${cfg.current_fy} Awards`, count, countDelta, countDir);
        }

        container.innerHTML = html;

        const cards = container.querySelectorAll('.metric-card');
        if (cards[2] && yoyDir) {
            cards[2].querySelector('.metric-value').classList.add(yoyDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
        if (cards[3] && medDir) {
            cards[3].querySelector('.metric-value').classList.add(medDir === 'negative' ? 'metric-neg' : 'metric-pos');
        }
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
