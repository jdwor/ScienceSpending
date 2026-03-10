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

    // ── Source type display names ──
    const SOURCE_LABELS = {
        nih_reporter: 'NIH Reporter',
        nsf_awards: 'NSF Awards',
        usaspending: 'USASpending',
    };

    // ── Agency Descriptions ──
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
        const labels = fyMonthLabels();
        const annots = [];
        for (let i = 1; i <= 12; i++) {
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
                font: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
            });
        }
        return annots;
    }

    function sourceAnnotation(text, yOffset) {
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
    };

    // Plotly config for small multiples (no mode bar)
    const PLOTLY_CONFIG_COMPACT = { displayModeBar: false, responsive: true };

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
                hovertemplate: '<b>' + agency.display_name + '</b><br>%{text}: %{y:.1f}% of mean pace<extra></extra>',
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
            titleEl.textContent = `FY${cfg.current_fy} Obligation Pace vs. ${bandLabel} Mean`;
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
                title: { text: '% of Mean Pace', font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
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
                bordercolor: '#e5e7eb',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            height: 460,
            margin: { l: 60, r: 12, t: 8, b: 95 },
            annotations: [
                {
                    text: bandLabel + ' mean',
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

        Plotly.newPlot('chart-multi-agency', traces, layout, PLOTLY_CONFIG_COMPACT);
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
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} mean`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vm,
                    y: vmd,
                    mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true,
                    name: medLabel,
                    hovertemplate: '<b>Mean</b>: %{y:.1f}' + (showPct ? '%' : 'B') + '<extra></extra>',
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

        const height = compact ? 340 : 500;
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
                l: compact ? 45 : 60,
                r: 12,
                t: compact ? 38 : 72,
                b: compact ? 65 : 110,
            },
            annotations: annotations,
        };

        Plotly.newPlot(targetDiv, traces, layout, compact ? PLOTLY_CONFIG_COMPACT : PLOTLY_CONFIG_EXPORT);
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
            card('vs. Mean', medStr, null, medDir);

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
        const showDollars = document.getElementById('toggle-dollars').checked;
        const agency = DATA.config.agencies[agencyKey];

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
            { key: 'mean_prior_pct', label: 'Mean', format: v => v != null ? v.toFixed(1) + '%' : '\u2014', cls: 'number' },
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

    // ── Awards Data Tables ──

    function renderAwardsAnnualTable() {
        const awards = DATA.awards;
        const cfg = DATA.config;
        const table = document.getElementById('table-awards-annual');
        if (!table || !awards) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        const cols = [
            { key: 'agency', label: 'Agency', format: v => {
                const a = cfg.agencies[v];
                return a ? a.display_name : v;
            }},
            { key: 'fiscal_year', label: 'FY', format: v => v },
            { key: 'source', label: 'Source', format: v => SOURCE_LABELS[v] || v },
            { key: 'count', label: 'Awards', format: v => v != null && v > 0 ? v.toLocaleString() : '\u2014', cls: 'number' },
            { key: 'dollars', label: 'Dollars', format: v => v != null ? formatDollars(v * 1e6) : '\u2014', cls: 'number' },
        ];

        thead.innerHTML = '<tr>' + cols.map(c => `<th>${c.label}</th>`).join('') + '</tr>';

        // Build rows from awards year traces (end-of-year values)
        const rows = [];
        for (const [agencyKey, agencyData] of Object.entries(awards)) {
            if (!cfg.agencies[agencyKey]) continue;
            for (const fy of agencyData.fiscal_years) {
                const yearData = agencyData.years[String(fy)];
                if (!yearData) continue;
                const lastIdx = yearData.fy_days.length - 1;
                if (lastIdx < 0) continue;
                rows.push({
                    agency: agencyKey,
                    fiscal_year: fy,
                    source: agencyData.source_type,
                    count: yearData.cumulative_count[lastIdx],
                    dollars: yearData.cumulative_dollars_m[lastIdx],
                });
            }
        }

        rows.sort((a, b) => {
            const cmp = (a.agency || '').localeCompare(b.agency || '');
            if (cmp !== 0) return cmp;
            return (b.fiscal_year || 0) - (a.fiscal_year || 0);
        });

        tbody.innerHTML = rows.map(row =>
            '<tr>' + cols.map(c => {
                const val = row[c.key];
                const formatted = c.format(val, row);
                return `<td class="${c.cls || ''}">${formatted}</td>`;
            }).join('') + '</tr>'
        ).join('');
    }

    function renderAwardsSummaryTable() {
        const summary = DATA.awards_summary;
        const cfg = DATA.config;
        const table = document.getElementById('table-awards-summary');
        if (!table || !summary) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        const cols = [
            { key: 'agency', label: 'Agency', format: v => {
                const a = cfg.agencies[v];
                return a ? a.display_name : v;
            }},
            { key: 'source_type', label: 'Source', format: v => SOURCE_LABELS[v] || v },
            { key: 'latest_date', label: 'As Of', format: v => v || '\u2014' },
            { key: 'cumul_count', label: `FY${cfg.current_fy} Awards`, format: v => v != null && v > 0 ? v.toLocaleString() : '\u2014', cls: 'number' },
            { key: 'cumul_dollars', label: `FY${cfg.current_fy} Dollars`, format: v => v != null ? formatDollars(v) : '\u2014', cls: 'number' },
            { key: 'prior_year_dollars', label: `FY${cfg.current_fy - 1} Dollars`, format: v => v != null ? formatDollars(v) : '\u2014', cls: 'number' },
            { key: '_pct_prior_dollars', label: '% of Prior Yr', format: (v, row) => {
                if (row.prior_year_dollars && row.prior_year_dollars > 0) {
                    return (row.cumul_dollars / row.prior_year_dollars * 100).toFixed(0) + '%';
                }
                return '\u2014';
            }, cls: 'number' },
            { key: 'mean_dollars', label: 'Mean Dollars', format: v => v != null ? formatDollars(v) : '\u2014', cls: 'number' },
            { key: '_pct_mean_dollars', label: '% of Mean', format: (v, row) => {
                if (row.mean_dollars && row.mean_dollars > 0) {
                    return (row.cumul_dollars / row.mean_dollars * 100).toFixed(0) + '%';
                }
                return '\u2014';
            }, cls: 'number' },
        ];

        thead.innerHTML = '<tr>' + cols.map(c => `<th>${c.label}</th>`).join('') + '</tr>';

        const rows = Object.entries(summary)
            .map(([key, row]) => Object.assign({ agency: key }, row))
            .sort((a, b) => (a.agency || '').localeCompare(b.agency || ''));

        tbody.innerHTML = rows.map(row =>
            '<tr>' + cols.map(c => {
                const val = row[c.key];
                const formatted = c.format(val, row);
                return `<td class="${c.cls || ''}">${formatted}</td>`;
            }).join('') + '</tr>'
        ).join('');
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
        const labels = fyMonthLabels();
        const annots = [];
        for (let i = 1; i <= 12; i++) {
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
                font: { family: FONT_SANS, size: compact ? 10 : 11, color: MUTED_COLOR },
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
                // Interpolate at each target day, plus always keep the last point
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
                // Always include the latest data point
                const lastX = xVals[xVals.length - 1];
                if (plotX[plotX.length - 1] !== lastX) {
                    plotX.push(lastX);
                    plotY.push(yVals[yVals.length - 1]);
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
                hovertemplate: '<b>' + agencyCfg.display_name + '</b><br>%{text}: %{y:.1f}% of mean pace<extra></extra>',
                hoverlabel: { bordercolor: agencyCfg.color },
            });
        }

        // Set HTML chart title
        const awardsTitleEl = document.getElementById('awards-multi-title');
        if (awardsTitleEl) {
            awardsTitleEl.textContent = `FY${currentFy} Award-Making Pace vs. Historical Mean`;
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
                title: { text: '% of Mean Pace', font: { family: FONT_SANS, size: 10, color: MUTED_COLOR }, standoff: 5 },
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
                bordercolor: '#e5e7eb',
                font: { family: FONT_SANS, size: 12, color: TEXT_COLOR },
            },
            plot_bgcolor: 'white',
            paper_bgcolor: 'white',
            height: 460,
            margin: { l: 60, r: 12, t: 8, b: 95 },
            annotations: [
                {
                    text: 'Historical mean',
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

        Plotly.newPlot('chart-awards-multi', traces, layout, PLOTLY_CONFIG_COMPACT);
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
                    ? `FY${bandFys[0]}\u2013${bandFys[bandFys.length - 1]} mean`
                    : `FY${bandFys[0]}`;

                traces.push({
                    x: vd,
                    y: vmd,
                    mode: 'lines',
                    line: { color: '#b0bac8', width: 1.5, dash: 'dot' },
                    showlegend: true,
                    name: medLabel,
                    hovertemplate: isPct ? '<b>Mean</b>: %{y:.2f}%<extra></extra>'
                        : '<b>Mean</b>: %{y:,.0f}<extra></extra>',
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

        const height = compact ? 340 : 500;
        const sourceLabel = SOURCE_LABELS[agencyAwards.source_type] || agencyAwards.source_type;
        const awardAnnotations = compact ? [] : [sourceAnnotation('Source: ' + sourceLabel)];

        const awardYLabel = isPct ? '% of Appropriation Awarded' : isDollars ? 'Cumulative Awards ($M)' : 'Cumulative Award Count';
        const awardsDetailSubtitle = mode === 'counts'
            ? 'Cumulative new award count over the fiscal year.'
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
                l: compact ? 45 : 60,
                r: 12,
                t: compact ? 38 : 72,
                b: compact ? 65 : 110,
            },
            annotations: awardAnnotations,
        };

        Plotly.newPlot(targetDiv, traces, layout, compact ? PLOTLY_CONFIG_COMPACT : PLOTLY_CONFIG_EXPORT);
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
        html += card('vs. Mean', medStr, null, medDir);

        // Card 6: Award count (NIH/NSF only — inherently normalized)
        if (hasCounts && summ.cumul_count) {
            const count = summ.cumul_count.toLocaleString();
            const meanCount = summ.mean_count ? Math.round(summ.mean_count).toLocaleString() : null;
            let countDelta = '';
            let countDir = '';
            if (meanCount != null && summ.mean_count) {
                countDelta = 'vs. mean of ' + meanCount;
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
        const agencyCfg = DATA.config.agencies[agencyKey];

        // Default to pct; only NIH/NSF have meaningful counts
        const hasCounts = agencyAwards && agencyAwards.source_type !== 'usaspending';
        const showCounts = hasCounts && document.getElementById('awards-toggle-counts').checked;
        const mode = showCounts ? 'counts' : 'pct';

        // Show count toggle only for agencies with count data (NIH, NSF)
        const toggleContainer = document.getElementById('awards-toggle-container');
        if (toggleContainer) {
            toggleContainer.style.display = hasCounts ? '' : 'none';
        }

        renderAwardsMetrics(agencyKey);
        renderAwardsCumulativeChart(agencyKey, 'chart-awards-detail', mode, false);
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
            // Reset count toggle when switching agencies
            document.getElementById('awards-toggle-counts').checked = false;
            renderAwardsDetail();
        });
        document.getElementById('awards-toggle-counts').addEventListener('change', renderAwardsDetail);

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
        renderAwardsAnnualTable();
        renderAwardsSummaryTable();
        initAwardsTab();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
