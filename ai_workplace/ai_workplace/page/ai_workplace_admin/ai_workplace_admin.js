/**
 * ai_workplace_admin.js
 * Frappe Desk Page Controller for Admin Operations Dashboard.
 * 100% Vanilla JS + HTML + CSS Implementation.
 */

frappe.pages['ai-workplace-admin'].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('AI Workplace Operational Dashboard'),
        single_column: true
    });

    // Ensure assets are loaded
    frappe.require([
        '/assets/ai_workplace/css/ai_workplace_admin.css',
        '/assets/ai_workplace/js/admin_dashboard/dashboard_utils.js',
        '/assets/ai_workplace/js/admin_dashboard/dashboard_state.js',
        '/assets/ai_workplace/js/admin_dashboard/dashboard_api.js',
        '/assets/ai_workplace/js/admin_dashboard/dashboard_charts.js',
        '/assets/ai_workplace/js/admin_dashboard/admin_dashboard_render.js'
    ], function () {
        initAdminDashboard(page, wrapper);
    });
};

function initAdminDashboard(page, wrapper) {
    var $body = $(wrapper).find('.layout-main-section');
    $body.html('<div id="admin-dashboard-app"><div class="dash-empty"><i class="fa fa-spinner fa-spin fa-2x"></i><br><br>Loading Operational Dashboard...</div></div>');
    var container = document.getElementById('admin-dashboard-app');

    var autoRefreshTimer = null;

    function loadData() {
        var rangeType = DashboardState.get('rangeType');
        var fromDate = DashboardState.get('fromDate');
        var toDate = DashboardState.get('toDate');

        DashboardState.set('isLoading', true);

        DashboardAPI.fetchDashboardData(rangeType, fromDate, toDate, function (err, data) {
            if (err) {
                console.error('Dashboard data error:', err);
                frappe.show_alert({ message: __('Failed to load dashboard data'), indicator: 'red' });
                if (container) container.innerHTML = '<div class="dash-empty text-danger"><i class="fa fa-exclamation-triangle fa-2x"></i><br><br>Error loading dashboard statistics. Please refresh.</div>';
                return;
            }
            DashboardState.setData(data);
            AdminDashboardRender.renderFullDashboard(container, data, DashboardState);
        });
    }

    function setupAutoRefresh() {
        if (autoRefreshTimer) clearInterval(autoRefreshTimer);
        if (DashboardState.get('autoRefresh')) {
            autoRefreshTimer = setInterval(function () {
                loadData();
            }, DashboardState.get('refreshInterval'));
        }
    }

    // Subscribe to state updates
    DashboardState.subscribe(function (event, payload) {
        if (event === 'range') {
            loadData();
        }
    });

    // Event Delegation
    $(wrapper).on('click', '.dash-tab-btn', function () {
        var tabId = $(this).attr('data-tab');
        if (tabId) {
            DashboardState.set('activeTab', tabId);
            AdminDashboardRender.renderFullDashboard(container, DashboardState.get('data'), DashboardState);
        }
    });

    $(wrapper).on('change', '#dash-range-select', function () {
        var val = $(this).val();
        if (val === 'custom') {
            $('#dash-custom-dates').show();
        } else {
            $('#dash-custom-dates').hide();
            DashboardState.updateRange(val, null, null);
        }
    });

    $(wrapper).on('click', '#dash-apply-custom', function () {
        var fromD = $('#dash-from-date').val();
        var toD = $('#dash-to-date').val();
        if (!fromD) {
            frappe.show_alert({ message: __('Please select From Date'), indicator: 'orange' });
            return;
        }
        DashboardState.updateRange('custom', fromD, toD);
    });

    $(wrapper).on('click', '#dash-refresh-btn', function () {
        var $btn = $(this);
        $btn.find('i').addClass('fa-spin');
        loadData();
        setTimeout(function () { $btn.find('i').removeClass('fa-spin'); }, 1000);
    });

    $(wrapper).on('change', '#dash-auto-toggle', function () {
        var checked = $(this).is(':checked');
        DashboardState.set('autoRefresh', checked);
        setupAutoRefresh();
    });

    $(wrapper).on('click', '.btn-reset-circuit', function () {
        var provider = $(this).attr('data-provider');
        if (provider) {
            DashboardAPI.resetCircuitBreaker(provider, function (err, res) {
                if (!err) loadData();
            });
        }
    });

    // Initial Load & Auto Refresh setup
    loadData();
    setupAutoRefresh();

    // Clean up timer on page destruction
    page.wrapper.on('hide', function () {
        if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    });
}
