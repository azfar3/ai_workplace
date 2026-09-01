/**
 * admin_dashboard_render.js
 * Vanilla JavaScript UI Renderer for Admin Operations Dashboard.
 * 100% Framework-free Pure HTML DOM Generation & Event Handling.
 */
window.AdminDashboardRender = (function () {
    var U = DashboardUtils;

    function renderHeader(data, state) {
        var range = state.get('rangeType');
        var fromDate = state.get('fromDate') || '';
        var toDate = state.get('toDate') || '';
        var autoRef = state.get('autoRefresh');
        var healthStatus = (data && data.overview) ? data.overview.health : 'HEALTHY';

        var html = '<div class="dash-header-card">';
        html += '  <div class="header-left">';
        html += '    <div class="header-title-row">';
        html += '      <h1 class="header-title"><i class="fa fa-dashboard"></i> AI Workplace Operational Dashboard</h1>';
        html += '      <div class="header-status">' + U.statusBadge(healthStatus) + '</div>';
        html += '    </div>';
        html += '    <div class="header-sub">Comprehensive real-time operational, AI cost, security, performance & deterministic engine observability</div>';
        html += '  </div>';

        html += '  <div class="header-controls">';
        html += '    <div class="control-group">';
        html += '      <label><i class="fa fa-calendar"></i> Date Range:</label>';
        html += '      <select id="dash-range-select" class="dash-select">';
        html += '        <option value="today"' + (range === 'today' ? ' selected' : '') + '>Today</option>';
        html += '        <option value="yesterday"' + (range === 'yesterday' ? ' selected' : '') + '>Yesterday</option>';
        html += '        <option value="7d"' + (range === '7d' ? ' selected' : '') + '>Last 7 Days</option>';
        html += '        <option value="30d"' + (range === '30d' ? ' selected' : '') + '>Last 30 Days</option>';
        html += '        <option value="90d"' + (range === '90d' ? ' selected' : '') + '>Last 90 Days</option>';
        html += '        <option value="custom"' + (range === 'custom' ? ' selected' : '') + '>Custom Range...</option>';
        html += '      </select>';
        html += '    </div>';

        var customStyle = range === 'custom' ? '' : 'display: none;';
        html += '    <div id="dash-custom-dates" class="control-group" style="' + customStyle + '">';
        html += '      <input type="date" id="dash-from-date" class="dash-input" value="' + U.escapeHtml(fromDate) + '">';
        html += '      <span>to</span>';
        html += '      <input type="date" id="dash-to-date" class="dash-input" value="' + U.escapeHtml(toDate) + '">';
        html += '      <button id="dash-apply-custom" class="btn btn-sm btn-secondary">Apply</button>';
        html += '    </div>';

        html += '    <div class="control-group auto-refresh-group">';
        html += '      <label class="checkbox-label"><input type="checkbox" id="dash-auto-toggle"' + (autoRef ? ' checked' : '') + '> Auto Refresh</label>';
        html += '      <button id="dash-refresh-btn" class="btn btn-sm btn-primary"><i class="fa fa-refresh"></i> Refresh</button>';
        html += '    </div>';
        html += '    <div class="header-updated">Updated: <span id="dash-updated-text">' + U.escapeHtml(state.get('lastUpdated') || 'Just now') + '</span></div>';
        html += '  </div>';
        html += '</div>';

        return html;
    }

    function renderTabBar(activeTab) {
        var tabs = [
            { id: 'overview', label: 'Executive Overview', icon: 'fa-line-chart' },
            { id: 'ai_analytics', label: 'AI Usage & Cost', icon: 'fa-bolt' },
            { id: 'deterministic', label: 'Deterministic Engine', icon: 'fa-cogs' },
            { id: 'users', label: 'User Analytics', icon: 'fa-users' },
            { id: 'conversations', label: 'Conversations', icon: 'fa-comments' },
            { id: 'health', label: 'System Health', icon: 'fa-heartbeat' },
            { id: 'errors', label: 'Errors & Failures', icon: 'fa-exclamation-triangle' },
            { id: 'security', label: 'Security & Access', icon: 'fa-shield' },
            { id: 'knowledge', label: 'Knowledge / RAG', icon: 'fa-book' },
            { id: 'erpnext', label: 'ERPNext HR', icon: 'fa-building' },
            { id: 'tools', label: 'Tool Analytics', icon: 'fa-wrench' },
            { id: 'performance', label: 'Performance', icon: 'fa-tachometer' },
            { id: 'live_feed', label: 'Live Stream', icon: 'fa-rss' }
        ];

        var html = '<div class="dash-tab-bar">';
        tabs.forEach(function (t) {
            var activeClass = (t.id === activeTab) ? ' active' : '';
            html += '<button class="dash-tab-btn' + activeClass + '" data-tab="' + t.id + '"><i class="fa ' + t.icon + '"></i> ' + t.label + '</button>';
        });
        html += '</div>';
        return html;
    }

    function renderAlerts(alerts) {
        if (!alerts || !alerts.length) return '';
        var html = '<div class="dash-alerts-container">';
        alerts.forEach(function (a) {
            html += '<div class="dash-alert dash-alert-' + (a.severity || 'warning') + '">';
            html += '  <div class="alert-icon"><i class="fa fa-bell"></i></div>';
            html += '  <div class="alert-body">';
            html += '    <strong>' + U.escapeHtml(a.title) + ':</strong> ' + U.escapeHtml(a.message);
            html += '  </div>';
            html += '</div>';
        });
        html += '</div>';
        return html;
    }

    // 1. Executive Overview Tab
    function renderOverviewTab(data) {
        if (!data || !data.overview) return '<div class="dash-empty">No overview data available.</div>';
        var o = data.overview;
        var sys = o.system || {};
        var ai = o.ai || {};
        var det = o.deterministic || {};

        var html = '<div class="tab-pane-content">';
        
        // Key Highlight: Deterministic Resolution Rate Banner
        html += '<div class="highlight-banner-card">';
        html += '  <div class="banner-left">';
        html += '    <div class="banner-label">DETERMINISTIC QUERY RESOLUTION RATE</div>';
        html += '    <div class="banner-value">' + U.formatPercent(det.deterministic_resolution_rate) + '</div>';
        html += '    <div class="banner-sub">Queries handled deterministically without incurring LLM cost or hallucination risk</div>';
        html += '  </div>';
        html += '  <div class="banner-metrics">';
        html += '    <div class="b-stat"><span class="b-val">' + U.formatNumber(det.deterministic_queries) + '</span><span class="b-lbl">Deterministic Queries</span></div>';
        html += '    <div class="b-stat"><span class="b-val">' + U.formatNumber(det.llm_routed_queries) + '</span><span class="b-lbl">LLM Routed</span></div>';
        html += '    <div class="b-stat"><span class="b-val">' + U.formatPercent(det.llm_routing_rate) + '</span><span class="b-lbl">LLM Rate</span></div>';
        html += '  </div>';
        html += '</div>';

        // Stat Cards Grid
        html += '<div class="dash-section-title">System & Operational KPIs</div>';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card">';
        html += '    <div class="stat-icon blue"><i class="fa fa-users"></i></div>';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatNumber(sys.total_users) + '</div>';
        html += '      <div class="stat-label">Total Users</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(sys.active_users) + ' Active</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-icon purple"><i class="fa fa-comments-o"></i></div>';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatNumber(sys.active_sessions) + '</div>';
        html += '      <div class="stat-label">Active Sessions</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(sys.sessions_today) + ' Sessions Today</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-icon green"><i class="fa fa-check-circle"></i></div>';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatPercent(ai.ai_success_rate) + '</div>';
        html += '      <div class="stat-label">AI Success Rate</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(ai.ai_responses) + ' Success / ' + U.formatNumber(ai.ai_failures) + ' Failed</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-icon orange"><i class="fa fa-clock-o"></i></div>';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.latencyBadge(ai.avg_ai_response_time) + '</div>';
        html += '      <div class="stat-label">Avg AI Latency</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(ai.ai_timeout_count) + ' Timeouts</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-icon gold"><i class="fa fa-usd"></i></div>';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatCurrency(ai.total_cost) + '</div>';
        html += '      <div class="stat-label">AI Cost (Selected Range)</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(ai.ai_requests_today) + ' AI Requests Today</div>';
        html += '    </div>';
        html += '  </div>';

        html += '</div>';

        // Overview Charts Row
        html += '<div class="dash-charts-row">';
        html += '  <div class="dash-chart-card wide">';
        html += '    <div class="chart-card-title">AI Requests Timeline</div>';
        html += '    <div id="chart-overview-requests"></div>';
        html += '  </div>';
        html += '  <div class="dash-chart-card narrow">';
        html += '    <div class="chart-card-title">Query Engine Routing</div>';
        html += '    <div id="chart-overview-routing"></div>';
        html += '  </div>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 2. AI Usage & Cost Analytics Tab
    function renderAiAnalyticsTab(data) {
        if (!data || !data.ai_analytics) return '<div class="dash-empty">No AI analytics available.</div>';
        var ai = data.ai_analytics;
        var s = ai.summary || {};
        var providers = ai.providers || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatNumber(s.total_llm_requests) + '</div>';
        html += '      <div class="stat-label">Total LLM Requests</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(s.requests_today) + ' Today | ' + U.formatNumber(s.requests_this_month) + ' Month</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatNumber(s.total_tokens) + '</div>';
        html += '      <div class="stat-label">Total Tokens</div>';
        html += '      <div class="stat-sub">In: ' + U.formatNumber(s.input_tokens) + ' | Out: ' + U.formatNumber(s.output_tokens) + '</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatCurrency(s.total_cost) + '</div>';
        html += '      <div class="stat-label">Total Cost</div>';
        html += '      <div class="stat-sub">Today: ' + U.formatCurrency(s.cost_today) + ' | Month: ' + U.formatCurrency(s.cost_this_month) + '</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatCurrency(s.avg_cost_per_request) + '</div>';
        html += '      <div class="stat-label">Avg Cost / Request</div>';
        html += '      <div class="stat-sub">Avg Tokens: ' + U.formatNumber(s.avg_tokens_per_request) + '</div>';
        html += '    </div>';
        html += '  </div>';

        html += '</div>';

        // AI Charts Row
        html += '<div class="dash-charts-row">';
        html += '  <div class="dash-chart-card">';
        html += '    <div class="chart-card-title">Token Consumption (Input vs Output)</div>';
        html += '    <div id="chart-ai-tokens"></div>';
        html += '  </div>';
        html += '  <div class="dash-chart-card">';
        html += '    <div class="chart-card-title">AI Cost Trend</div>';
        html += '    <div id="chart-ai-cost"></div>';
        html += '  </div>';
        html += '</div>';

        // Providers Table
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-server"></i> AI Providers & Models Breakdown</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Provider</th><th>Requests</th><th>Success</th><th>Fail Rate</th><th>Total Tokens</th><th>Cost</th><th>Avg Latency</th><th>Actions</th></tr></thead>';
        html += '    <tbody>';
        if (providers.length) {
            providers.forEach(function (p) {
                html += '<tr>';
                html += '  <td><strong>' + U.escapeHtml(p.provider) + '</strong></td>';
                html += '  <td>' + U.formatNumber(p.total) + '</td>';
                html += '  <td>' + U.formatNumber(p.ok) + '</td>';
                html += '  <td>' + U.formatPercent(p.fail_rate) + '</td>';
                html += '  <td>' + U.formatNumber(p.tokens) + '</td>';
                html += '  <td>' + U.formatCurrency(p.cost) + '</td>';
                html += '  <td>' + U.latencyBadge(p.avg_latency) + '</td>';
                html += '  <td><button class="btn btn-xs btn-default btn-reset-circuit" data-provider="' + U.escapeHtml(p.provider) + '">Reset Circuit Breaker</button></td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="8" class="text-center text-muted">No provider usage recorded in this range.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 3. Deterministic Query Engine Analytics Tab
    function renderDeterministicTab(data) {
        if (!data || !data.deterministic) return '<div class="dash-empty">No deterministic analytics available.</div>';
        var d = data.deterministic;
        var intents = d.top_intents || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.formatNumber(d.total_queries) + '</div>';
        html += '      <div class="stat-label">Total Queries Evaluated</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(d.intent_classification_count) + ' Intents Registered</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value green-text">' + U.formatNumber(d.resolved_deterministically) + '</div>';
        html += '      <div class="stat-label">Resolved Deterministically</div>';
        html += '      <div class="stat-sub">Zero LLM Call</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value purple-text">' + U.formatNumber(d.sent_to_llm) + '</div>';
        html += '      <div class="stat-label">Sent to LLM Agent</div>';
        html += '      <div class="stat-sub">' + U.formatNumber(d.fallback_to_llm) + ' Hybrid Fallbacks</div>';
        html += '    </div>';
        html += '  </div>';

        html += '  <div class="stat-card">';
        html += '    <div class="stat-content">';
        html += '      <div class="stat-value">' + U.latencyBadge(d.avg_deterministic_response_ms) + '</div>';
        html += '      <div class="stat-label">Avg Deterministic Speed</div>';
        html += '      <div class="stat-sub">Instant response</div>';
        html += '    </div>';
        html += '  </div>';

        html += '</div>';

        // Routing Donut + Intents Table
        html += '<div class="dash-charts-row">';
        html += '  <div class="dash-chart-card narrow">';
        html += '    <div class="chart-card-title">Routing Split</div>';
        html += '    <div id="chart-det-routing"></div>';
        html += '  </div>';

        html += '  <div class="dash-table-card wide" style="margin: 0;">';
        html += '    <div class="table-card-title"><i class="fa fa-list-ol"></i> Most Common Query Intents</div>';
        html += '    <table class="dash-table">';
        html += '      <thead><tr><th>Intent Name</th><th>Requests</th><th>Success Rate</th><th>Avg Speed</th></tr></thead>';
        html += '      <tbody>';
        if (intents.length) {
            intents.forEach(function (ti) {
                html += '<tr>';
                html += '  <td><code>' + U.escapeHtml(ti.intent) + '</code></td>';
                html += '  <td>' + U.formatNumber(ti.requests) + '</td>';
                html += '  <td>' + U.formatPercent(ti.success_rate) + '</td>';
                html += '  <td>' + U.latencyBadge(ti.avg_response_ms) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="4" class="text-center text-muted">No intents logged yet.</td></tr>';
        }
        html += '      </tbody>';
        html += '    </table>';
        html += '  </div>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 4. User Analytics Tab
    function renderUsersTab(data) {
        if (!data || !data.user_analytics) return '<div class="dash-empty">No user analytics available.</div>';
        var u = data.user_analytics;
        var top = u.top_users || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(u.registered_users) + '</div><div class="stat-label">Registered Users</div><div class="stat-sub">' + U.formatNumber(u.active_users) + ' Enabled</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(u.users_active_today) + '</div><div class="stat-label">Active Today</div><div class="stat-sub">Unique active accounts</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(u.users_active_week) + '</div><div class="stat-label">Active This Week</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(u.users_active_month) + '</div><div class="stat-label">Active This Month</div></div></div>';

        html += '</div>';

        html += '<div class="dash-charts-row">';
        html += '  <div class="dash-chart-card wide">';
        html += '    <div class="chart-card-title">Daily Active Users (DAU) Trend</div>';
        html += '    <div id="chart-user-dau"></div>';
        html += '  </div>';
        html += '</div>';

        // Top Users Table
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-trophy"></i> Top Active Users & Query Volume</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>User (Masked)</th><th>Total Queries</th><th>AI Queries</th><th>Deterministic Queries</th><th>Last Activity</th><th>Errors</th></tr></thead>';
        html += '    <tbody>';
        if (top.length) {
            top.forEach(function (tu) {
                html += '<tr>';
                html += '  <td><strong>' + U.escapeHtml(tu.user_display || tu.user_id) + '</strong></td>';
                html += '  <td>' + U.formatNumber(tu.total_queries) + '</td>';
                html += '  <td>' + U.formatNumber(tu.ai_queries) + '</td>';
                html += '  <td>' + U.formatNumber(tu.det_queries) + '</td>';
                html += '  <td>' + U.formatDateTime(tu.last_activity) + '</td>';
                html += '  <td>' + (tu.error_count > 0 ? '<span class="text-danger">' + tu.error_count + '</span>' : '0') + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="6" class="text-center text-muted">No user activity recorded.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 5. Conversation Analytics Tab
    function renderConversationsTab(data) {
        if (!data || !data.conversations) return '<div class="dash-empty">No conversation analytics available.</div>';
        var c = data.conversations;
        var recent = c.recent_conversations || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value green-text">' + U.formatNumber(c.active) + '</div><div class="stat-label">Active Conversations</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(c.completed) + '</div><div class="stat-label">Completed</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value text-warning">' + U.formatNumber(c.expired) + '</div><div class="stat-label">Expired</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(c.avg_length_msgs) + '</div><div class="stat-label">Avg Msgs / Session</div></div></div>';

        html += '</div>';

        // Recent Conversations Table
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-comments"></i> Recent Conversations Log</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Conversation ID</th><th>User / Identity</th><th>Status</th><th>Messages</th><th>Routing</th><th>Started</th><th>Last Activity</th></tr></thead>';
        html += '    <tbody>';
        if (recent.length) {
            recent.forEach(function (rc) {
                html += '<tr>';
                html += '  <td><code>' + U.escapeHtml(rc.name) + '</code></td>';
                html += '  <td>' + U.escapeHtml(rc.user_label || rc.whatsapp_identity || 'Guest') + '</td>';
                html += '  <td>' + U.statusBadge(rc.status) + '</td>';
                html += '  <td>' + U.formatNumber(rc.msg_count) + '</td>';
                html += '  <td><span class="dash-badge ' + (rc.routing === 'LLM' ? 'badge-info' : 'badge-success') + '">' + rc.routing + '</span></td>';
                html += '  <td>' + U.formatDateTime(rc.started_at) + '</td>';
                html += '  <td>' + U.formatDateTime(rc.last_activity_at) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="7" class="text-center text-muted">No conversations found.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 6. System Health Tab
    function renderHealthTab(data) {
        if (!data || !data.health) return '<div class="dash-empty">No health data available.</div>';
        var h = data.health;
        var services = h.services || {};

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-section-title">Operational Health Matrix (' + U.statusBadge(h.overall_status) + ')</div>';

        html += '<div class="health-grid">';
        Object.keys(services).forEach(function (key) {
            var s = services[key];
            html += '<div class="health-card health-' + String(s.status).toLowerCase() + '">';
            html += '  <div class="health-header">';
            html += '    <div class="health-title">' + U.escapeHtml(s.title) + '</div>';
            html += '    <div class="health-status-badge">' + U.statusBadge(s.status) + '</div>';
            html += '  </div>';
            html += '  <div class="health-body">';
            html += '    <div class="health-detail">' + U.escapeHtml(s.details) + '</div>';
            html += '    <div class="health-metrics">';
            html += '      <span>Latency: <strong>' + U.latencyBadge(s.latency_ms) + '</strong></span>';
            html += '      <span>Errors: <strong>' + s.error_count + '</strong></span>';
            html += '      <span>Checked: ' + U.escapeHtml(s.last_check) + '</span>';
            html += '    </div>';
            html += '  </div>';
            html += '</div>';
        });
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 7. Errors Tab
    function renderErrorsTab(data) {
        if (!data || !data.errors) return '<div class="dash-empty">No error monitoring data available.</div>';
        var e = data.errors;
        var recent = e.recent_errors || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value text-danger">' + U.formatNumber(e.errors_today) + '</div><div class="stat-label">Errors Today</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value text-danger">' + U.formatNumber(e.errors_week) + '</div><div class="stat-label">Errors This Week</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatPercent(e.error_rate_pct) + '</div><div class="stat-label">Error Rate</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(e.failed_ai_requests) + '</div><div class="stat-label">Failed AI Reqs</div></div></div>';

        html += '</div>';

        html += '<div class="dash-charts-row">';
        html += '  <div class="dash-chart-card wide">';
        html += '    <div class="chart-card-title">Error Frequency Trend</div>';
        html += '    <div id="chart-error-trend"></div>';
        html += '  </div>';
        html += '</div>';

        // Recent Errors Table
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-exclamation-triangle"></i> Recent Error Logs</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Timestamp</th><th>Component</th><th>Severity</th><th>Error Type</th><th>Endpoint / Tool</th><th>Details</th></tr></thead>';
        html += '    <tbody>';
        if (recent.length) {
            recent.forEach(function (err) {
                html += '<tr>';
                html += '  <td>' + U.formatDateTime(err.timestamp) + '</td>';
                html += '  <td>' + U.escapeHtml(err.component) + '</td>';
                html += '  <td>' + U.severityBadge(err.severity) + '</td>';
                html += '  <td><code>' + U.escapeHtml(err.error_type) + '</code></td>';
                html += '  <td>' + U.escapeHtml(err.endpoint_tool || 'N/A') + '</td>';
                html += '  <td class="text-muted">' + U.truncate(err.details, 60) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="6" class="text-center text-muted">No recent error logs found. System operates normally.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 8. Security Tab
    function renderSecurityTab(data) {
        if (!data || !data.security) return '<div class="dash-empty">No security monitoring data available.</div>';
        var sec = data.security;
        var events = sec.recent_events || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(sec.total_admins) + '</div><div class="stat-label">System Admins</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(sec.active_admin_sessions) + '</div><div class="stat-label">Active Admin Sessions</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(sec.auth_failures) + '</div><div class="stat-label">Auth Failures</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(sec.blocked_requests) + '</div><div class="stat-label">Blocked Requests</div></div></div>';

        html += '</div>';

        // Security Events Table
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-shield"></i> Recent Security Events Log</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Timestamp</th><th>Event Type</th><th>Severity</th><th>WhatsApp (Masked)</th><th>Description</th></tr></thead>';
        html += '    <tbody>';
        if (events.length) {
            events.forEach(function (se) {
                html += '<tr>';
                html += '  <td>' + U.formatDateTime(se.timestamp) + '</td>';
                html += '  <td><strong>' + U.escapeHtml(se.event_type) + '</strong></td>';
                html += '  <td>' + U.severityBadge(se.severity) + '</td>';
                html += '  <td>' + U.escapeHtml(se.whatsapp_masked || 'N/A') + '</td>';
                html += '  <td>' + U.escapeHtml(se.description) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="5" class="text-center text-muted">No security events logged.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 9. Knowledge / RAG Tab
    function renderKnowledgeTab(data) {
        if (!data || !data.knowledge) return '<div class="dash-empty">No knowledge analytics available.</div>';
        var k = data.knowledge;

        var html = '<div class="tab-pane-content">';
        
        if (k.is_stale) {
            html += '<div class="dash-alert dash-alert-warning"><i class="fa fa-warning"></i> <strong>Knowledge Index Stale:</strong> Knowledge base was last indexed on ' + U.escapeHtml(k.last_indexing_time) + '. Consider triggering re-indexing.</div>';
        }

        html += '<div class="dash-card-grid">';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(k.sources) + '</div><div class="stat-label">Knowledge Sources</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(k.chunks) + '</div><div class="stat-label">Total Text Chunks</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value green-text">' + U.formatNumber(k.embedded) + '</div><div class="stat-label">Embedded Chunks</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.escapeHtml(k.last_indexing_time) + '</div><div class="stat-label">Last Indexing Time</div></div></div>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 10. ERPNext Integration Tab
    function renderErpnextTab(data) {
        if (!data || !data.erpnext) return '<div class="dash-empty">No ERPNext monitoring available.</div>';
        var erp = data.erpnext;
        var breakdown = erp.tool_calls_breakdown || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.statusBadge(erp.status) + '</div><div class="stat-label">Connection Status</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.formatNumber(erp.total_requests) + '</div><div class="stat-label">Total Tool Calls</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value green-text">' + U.formatNumber(erp.successful_requests) + '</div><div class="stat-label">Successful</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.latencyBadge(erp.avg_response_time_ms) + '</div><div class="stat-label">Avg Response Time</div></div></div>';
        html += '</div>';

        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-briefcase"></i> ERPNext Service Function Breakdown</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Function Name</th><th>Tool Calls Count</th><th>Avg Latency</th></tr></thead>';
        html += '    <tbody>';
        breakdown.forEach(function (b) {
            html += '<tr>';
            html += '  <td><strong>' + U.escapeHtml(b.name) + '</strong></td>';
            html += '  <td>' + U.formatNumber(b.calls) + '</td>';
            html += '  <td>' + U.latencyBadge(b.avg_ms) + '</td>';
            html += '</tr>';
        });
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';

        html += '</div>';
        return html;
    }

    // 11. Tool Analytics Tab
    function renderToolsTab(data) {
        if (!data || !data.tools) return '<div class="dash-empty">No tool analytics available.</div>';
        var t = data.tools;
        var toolsList = t.tools || [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-wrench"></i> Tool & Function Execution Performance</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Tool / Service Name</th><th>Executions</th><th>Success</th><th>Failures</th><th>Failure Rate</th><th>Avg Speed</th></tr></thead>';
        html += '    <tbody>';
        if (toolsList.length) {
            toolsList.forEach(function (tl) {
                html += '<tr>';
                html += '  <td><code>' + U.escapeHtml(tl.tool_name) + '</code></td>';
                html += '  <td>' + U.formatNumber(tl.calls) + '</td>';
                html += '  <td>' + U.formatNumber(tl.success) + '</td>';
                html += '  <td>' + U.formatNumber(tl.failure) + '</td>';
                html += '  <td>' + U.formatPercent(tl.fail_rate) + '</td>';
                html += '  <td>' + U.latencyBadge(tl.avg_time_ms) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="6" class="text-center text-muted">No tool executions recorded.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';
        html += '</div>';
        return html;
    }

    // 12. Performance Monitoring Tab
    function renderPerformanceTab(data) {
        if (!data || !data.performance) return '<div class="dash-empty">No performance monitoring available.</div>';
        var p = data.performance;

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-card-grid">';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.latencyBadge(p.p50_latency_ms) + '</div><div class="stat-label">P50 Latency (Median)</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.latencyBadge(p.p95_latency_ms) + '</div><div class="stat-label">P95 Latency</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.latencyBadge(p.p99_latency_ms) + '</div><div class="stat-label">P99 Latency</div></div></div>';
        html += '  <div class="stat-card"><div class="stat-content"><div class="stat-value">' + U.latencyBadge(p.avg_deterministic_ms) + '</div><div class="stat-label">Avg Deterministic Speed</div></div></div>';
        html += '</div>';
        html += '</div>';
        return html;
    }

    // 13. Live Activity Stream Tab
    function renderLiveFeedTab(data) {
        var feed = (data && data.live_feed) ? data.live_feed : [];

        var html = '<div class="tab-pane-content">';
        html += '<div class="dash-table-card">';
        html += '  <div class="table-card-title"><i class="fa fa-rss"></i> Live Activity Feed (Auto-polling)</div>';
        html += '  <table class="dash-table">';
        html += '    <thead><tr><th>Time</th><th>User / Identity</th><th>Intent</th><th>Action</th><th>Status</th></tr></thead>';
        html += '    <tbody>';
        if (feed.length) {
            feed.forEach(function (item) {
                html += '<tr>';
                html += '  <td><code>' + U.escapeHtml(item.timestamp_str || item.timestamp) + '</code></td>';
                html += '  <td>' + U.escapeHtml(item.user_label || 'User') + '</td>';
                html += '  <td><code>' + U.escapeHtml(item.intent || 'general') + '</code></td>';
                html += '  <td>' + U.escapeHtml(item.action || item.service || 'N/A') + '</td>';
                html += '  <td>' + U.statusBadge(item.status) + '</td>';
                html += '</tr>';
            });
        } else {
            html += '<tr><td colspan="5" class="text-center text-muted">No recent activity stream entries.</td></tr>';
        }
        html += '    </tbody>';
        html += '  </table>';
        html += '</div>';
        html += '</div>';
        return html;
    }

    return {
        renderFullDashboard: function (container, data, state) {
            if (!container) return;
            var activeTab = state.get('activeTab') || 'overview';

            var html = '<div class="admin-dash-wrapper">';
            html += renderHeader(data, state);
            html += renderTabBar(activeTab);
            html += renderAlerts(data ? data.alerts : []);

            html += '<div class="dash-tab-body">';
            if (activeTab === 'overview') html += renderOverviewTab(data);
            else if (activeTab === 'ai_analytics') html += renderAiAnalyticsTab(data);
            else if (activeTab === 'deterministic') html += renderDeterministicTab(data);
            else if (activeTab === 'users') html += renderUsersTab(data);
            else if (activeTab === 'conversations') html += renderConversationsTab(data);
            else if (activeTab === 'health') html += renderHealthTab(data);
            else if (activeTab === 'errors') html += renderErrorsTab(data);
            else if (activeTab === 'security') html += renderSecurityTab(data);
            else if (activeTab === 'knowledge') html += renderKnowledgeTab(data);
            else if (activeTab === 'erpnext') html += renderErpnextTab(data);
            else if (activeTab === 'tools') html += renderToolsTab(data);
            else if (activeTab === 'performance') html += renderPerformanceTab(data);
            else if (activeTab === 'live_feed') html += renderLiveFeedTab(data);
            html += '</div>';

            html += '</div>';
            container.innerHTML = html;

            // Render active tab charts after DOM injection
            setTimeout(function () {
                if (activeTab === 'overview' && data && data.ai_analytics) {
                    DashboardCharts.renderRequestsChart('chart-overview-requests', data.ai_analytics.timeline);
                    if (data.deterministic) DashboardCharts.renderRoutingChart('chart-overview-routing', data.deterministic.distribution);
                } else if (activeTab === 'ai_analytics' && data && data.ai_analytics) {
                    DashboardCharts.renderTokenChart('chart-ai-tokens', data.ai_analytics.timeline);
                    DashboardCharts.renderCostChart('chart-ai-cost', data.ai_analytics.timeline);
                } else if (activeTab === 'deterministic' && data && data.deterministic) {
                    DashboardCharts.renderRoutingChart('chart-det-routing', data.deterministic.distribution);
                } else if (activeTab === 'users' && data && data.user_analytics) {
                    DashboardCharts.renderDauChart('chart-user-dau', data.user_analytics.dau_trend);
                } else if (activeTab === 'errors' && data && data.errors) {
                    DashboardCharts.renderErrorTrendChart('chart-error-trend', data.errors.trend);
                }
            }, 50);
        }
    };
})();
