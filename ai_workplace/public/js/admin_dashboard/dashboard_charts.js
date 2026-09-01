/**
 * dashboard_charts.js
 * Modular chart rendering for Admin Operations Dashboard.
 * Supports frappe.Chart with dynamic SVG fallbacks.
 */
window.DashboardCharts = (function () {
    var activeCharts = {};

    function clearChartContainer(containerId) {
        var el = document.getElementById(containerId);
        if (el) {
            el.innerHTML = '';
            if (activeCharts[containerId]) {
                try {
                    if (activeCharts[containerId].destroy) activeCharts[containerId].destroy();
                } catch (e) {}
                delete activeCharts[containerId];
            }
        }
        return el;
    }

    function renderFallbackSvgBarChart(container, title, labels, datasets) {
        if (!container || !labels || !labels.length) return;
        var maxVal = 1;
        datasets.forEach(function (ds) {
            (ds.values || []).forEach(function (v) {
                if (v > maxVal) maxVal = v;
            });
        });

        var svgHtml = '<div class="svg-chart-wrapper"><div class="svg-chart-title">' + DashboardUtils.escapeHtml(title) + '</div>';
        svgHtml += '<div class="svg-chart-bars">';
        
        labels.forEach(function (lbl, idx) {
            var v1 = (datasets[0] && datasets[0].values[idx]) || 0;
            var pct1 = Math.round((v1 / maxVal) * 100);
            svgHtml += '<div class="svg-bar-col" title="' + DashboardUtils.escapeHtml(lbl) + ': ' + v1 + '">';
            svgHtml += '<div class="svg-bar-track"><div class="svg-bar-fill" style="height: ' + pct1 + '%;"></div></div>';
            svgHtml += '<div class="svg-bar-label">' + DashboardUtils.escapeHtml(lbl.slice(-5)) + '</div>';
            svgHtml += '</div>';
        });
        
        svgHtml += '</div></div>';
        container.innerHTML = svgHtml;
    }

    return {
        renderRequestsChart: function (containerId, timeline) {
            var el = clearChartContainer(containerId);
            if (!el || !timeline || !timeline.length) {
                if (el) el.innerHTML = '<div class="dash-empty">No request timeline data available for date range.</div>';
                return;
            }

            var labels = timeline.map(function (d) { return d.date; });
            var totalVals = timeline.map(function (d) { return d.total; });
            var successVals = timeline.map(function (d) { return d.success; });

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'AI Requests Over Time',
                    data: {
                        labels: labels,
                        datasets: [
                            { name: 'Total Requests', values: totalVals, chartType: 'line' },
                            { name: 'Successful', values: successVals, chartType: 'bar' }
                        ]
                    },
                    type: 'axis-mixed',
                    height: 240,
                    colors: ['#3b82f6', '#10b981']
                });
            } else {
                renderFallbackSvgBarChart(el, 'AI Requests Over Time', labels, [{ values: totalVals }]);
            }
        },

        renderTokenChart: function (containerId, timeline) {
            var el = clearChartContainer(containerId);
            if (!el || !timeline || !timeline.length) {
                if (el) el.innerHTML = '<div class="dash-empty">No token consumption data available.</div>';
                return;
            }

            var labels = timeline.map(function (d) { return d.date; });
            var inputVals = timeline.map(function (d) { return d.tokens_in; });
            var outputVals = timeline.map(function (d) { return d.tokens_out; });

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'Token Consumption (Input vs Output)',
                    data: {
                        labels: labels,
                        datasets: [
                            { name: 'Input Tokens', values: inputVals },
                            { name: 'Output Tokens', values: outputVals }
                        ]
                    },
                    type: 'bar',
                    height: 240,
                    colors: ['#6366f1', '#ec4899']
                });
            } else {
                renderFallbackSvgBarChart(el, 'Token Consumption', labels, [{ values: inputVals }]);
            }
        },

        renderCostChart: function (containerId, timeline) {
            var el = clearChartContainer(containerId);
            if (!el || !timeline || !timeline.length) {
                if (el) el.innerHTML = '<div class="dash-empty">No cost data available.</div>';
                return;
            }

            var labels = timeline.map(function (d) { return d.date; });
            var costVals = timeline.map(function (d) { return d.cost; });

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'AI Usage Cost Trend ($)',
                    data: {
                        labels: labels,
                        datasets: [{ name: 'Daily Cost ($)', values: costVals }]
                    },
                    type: 'line',
                    height: 240,
                    colors: ['#f59e0b']
                });
            } else {
                renderFallbackSvgBarChart(el, 'AI Usage Cost Trend ($)', labels, [{ values: costVals }]);
            }
        },

        renderRoutingChart: function (containerId, dist) {
            var el = clearChartContainer(containerId);
            if (!el || !dist) return;

            var labels = ['Deterministic Resolved', 'LLM Routed', 'Hybrid Fallback'];
            var values = [
                dist.deterministic_pct || 0,
                dist.llm_pct || 0,
                dist.fallback_pct || 0
            ];

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'Query Routing Distribution',
                    data: {
                        labels: labels,
                        datasets: [{ values: values }]
                    },
                    type: 'donut',
                    height: 240,
                    colors: ['#10b981', '#8b5cf6', '#f59e0b']
                });
            } else {
                var html = '<div class="routing-legend">';
                html += '<div class="legend-item"><span class="dot green"></span> Deterministic: <strong>' + values[0] + '%</strong></div>';
                html += '<div class="legend-item"><span class="dot purple"></span> LLM Routed: <strong>' + values[1] + '%</strong></div>';
                html += '<div class="legend-item"><span class="dot orange"></span> Fallback: <strong>' + values[2] + '%</strong></div>';
                html += '</div>';
                el.innerHTML = html;
            }
        },

        renderDauChart: function (containerId, dauTrend) {
            var el = clearChartContainer(containerId);
            if (!el || !dauTrend || !dauTrend.length) {
                if (el) el.innerHTML = '<div class="dash-empty">No DAU activity data.</div>';
                return;
            }

            var labels = dauTrend.map(function (d) { return d.date; });
            var values = dauTrend.map(function (d) { return d.active_users; });

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'Daily Active Users (DAU)',
                    data: {
                        labels: labels,
                        datasets: [{ name: 'Active Users', values: values }]
                    },
                    type: 'line',
                    height: 240,
                    colors: ['#06b6d4']
                });
            } else {
                renderFallbackSvgBarChart(el, 'Daily Active Users', labels, [{ values: values }]);
            }
        },

        renderErrorTrendChart: function (containerId, trend) {
            var el = clearChartContainer(containerId);
            if (!el || !trend || !trend.length) {
                if (el) el.innerHTML = '<div class="dash-empty">No errors recorded in this date range.</div>';
                return;
            }

            var labels = trend.map(function (d) { return d.date; });
            var values = trend.map(function (d) { return d.total_errors; });

            if (window.frappe && window.frappe.Chart) {
                activeCharts[containerId] = new frappe.Chart('#' + containerId, {
                    title: 'System Errors Over Time',
                    data: {
                        labels: labels,
                        datasets: [{ name: 'Failed Queries', values: values }]
                    },
                    type: 'bar',
                    height: 240,
                    colors: ['#ef4444']
                });
            } else {
                renderFallbackSvgBarChart(el, 'System Errors Over Time', labels, [{ values: values }]);
            }
        }
    };
})();
