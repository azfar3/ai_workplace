/**
 * dashboard_api.js
 * API communication layer for Admin Operations Dashboard.
 */
window.DashboardAPI = (function () {
    return {
        fetchDashboardData: function (rangeType, fromDate, toDate, callback) {
            frappe.call({
                method: 'ai_workplace.api.analytics.get_full_admin_dashboard_data',
                args: {
                    range_type: rangeType || '30d',
                    from_date: fromDate || null,
                    to_date: toDate || null
                },
                freeze: false,
                callback: function (r) {
                    if (r && r.message) {
                        callback(null, r.message);
                    } else {
                        callback(r ? r.exc : 'Failed to fetch dashboard data', null);
                    }
                },
                error: function (err) {
                    callback(err || 'Server communication error', null);
                }
            });
        },

        resetCircuitBreaker: function (providerName, callback) {
            frappe.call({
                method: 'ai_workplace.api.analytics.reset_circuit_breaker',
                args: { provider_name: providerName },
                callback: function (r) {
                    if (r && r.message && r.message.success) {
                        frappe.show_alert({ message: __('Circuit Breaker Reset Successfully'), indicator: 'green' });
                        if (callback) callback(null, r.message);
                    } else {
                        frappe.show_alert({ message: __('Failed to reset Circuit Breaker'), indicator: 'red' });
                        if (callback) callback(r ? r.exc : 'Error resetting breaker', null);
                    }
                }
            });
        }
    };
})();
