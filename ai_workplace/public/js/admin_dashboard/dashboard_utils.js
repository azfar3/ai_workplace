/**
 * dashboard_utils.js
 * Utility functions for formatting numbers, currency, dates, HTML escaping, and status badges.
 */
window.DashboardUtils = (function () {
    return {
        escapeHtml: function (str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        },

        formatNumber: function (num) {
            if (num === null || num === undefined || isNaN(num)) return '0';
            return Number(num).toLocaleString();
        },

        formatCurrency: function (amount, currency) {
            currency = currency || 'USD';
            if (amount === null || amount === undefined || isNaN(amount)) return '$0.00';
            var formatted = Number(amount).toFixed(4);
            return (currency === 'USD' ? '$' : currency + ' ') + formatted;
        },

        formatPercent: function (val) {
            if (val === null || val === undefined || isNaN(val)) return '0.0%';
            return Number(val).toFixed(1) + '%';
        },

        formatDate: function (dateStr) {
            if (!dateStr) return 'N/A';
            var d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        },

        formatTime: function (dateTimeStr) {
            if (!dateTimeStr) return 'N/A';
            var d = new Date(dateTimeStr);
            if (isNaN(d.getTime())) {
                if (dateTimeStr.indexOf(' ') !== -1) return dateTimeStr.split(' ')[1];
                return dateTimeStr;
            }
            return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        },

        formatDateTime: function (dateTimeStr) {
            if (!dateTimeStr) return 'N/A';
            var d = new Date(dateTimeStr);
            if (isNaN(d.getTime())) return dateTimeStr;
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' +
                d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
        },

        truncate: function (str, len) {
            len = len || 30;
            if (!str) return '';
            str = String(str);
            if (str.length <= len) return str;
            return str.substring(0, len) + '...';
        },

        statusBadge: function (status) {
            status = String(status || '').toUpperCase();
            var badgeClass = 'badge-secondary';
            if (['HEALTHY', 'SUCCESS', 'ACTIVE', 'CLOSED', 'COMPLETED'].indexOf(status) !== -1) {
                badgeClass = 'badge-success';
            } else if (['DEGRADED', 'WARNING', 'HALF_OPEN', 'EXPIRED', 'TIMED OUT'].indexOf(status) !== -1) {
                badgeClass = 'badge-warning';
            } else if (['CRITICAL', 'UNAVAILABLE', 'FAILED', 'BLOCKED', 'OPEN', 'ABANDONED'].indexOf(status) !== -1) {
                badgeClass = 'badge-danger';
            } else if (['NOT_MONITORED', 'UNKNOWN'].indexOf(status) !== -1) {
                badgeClass = 'badge-info';
            }
            return '<span class="dash-badge ' + badgeClass + '">' + this.escapeHtml(status) + '</span>';
        },

        severityBadge: function (severity) {
            severity = String(severity || 'LOW').toUpperCase();
            var badgeClass = 'badge-info';
            if (severity === 'CRITICAL' || severity === 'HIGH') {
                badgeClass = 'badge-danger';
            } else if (severity === 'MEDIUM') {
                badgeClass = 'badge-warning';
            }
            return '<span class="dash-badge ' + badgeClass + '">' + this.escapeHtml(severity) + '</span>';
        },

        latencyBadge: function (ms) {
            if (ms === null || ms === undefined || isNaN(ms)) return '<span class="dash-badge badge-secondary">N/A</span>';
            ms = Number(ms);
            var badgeClass = 'badge-success';
            if (ms > 1500) badgeClass = 'badge-danger';
            else if (ms > 500) badgeClass = 'badge-warning';
            return '<span class="dash-badge ' + badgeClass + '">' + ms.toFixed(0) + ' ms</span>';
        }
    };
})();
