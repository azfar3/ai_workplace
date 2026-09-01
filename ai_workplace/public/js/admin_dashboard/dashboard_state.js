/**
 * dashboard_state.js
 * Centralized Vanilla JS state manager for the Admin Operations Dashboard.
 */
window.DashboardState = (function () {
    var state = {
        rangeType: '30d',
        fromDate: null,
        toDate: null,
        activeTab: 'overview',
        autoRefresh: true,
        refreshInterval: 30000,
        lastUpdated: null,
        isLoading: false,
        data: null,
        listeners: []
    };

    return {
        get: function (key) {
            return key ? state[key] : state;
        },

        set: function (key, value) {
            state[key] = value;
            this.notify(key, value);
        },

        updateRange: function (rangeType, fromDate, toDate) {
            state.rangeType = rangeType || '30d';
            state.fromDate = fromDate || null;
            state.toDate = toDate || null;
            this.notify('range', { rangeType: state.rangeType, fromDate: state.fromDate, toDate: state.toDate });
        },

        setData: function (data) {
            state.data = data;
            state.lastUpdated = data ? data.last_updated : null;
            state.isLoading = false;
            this.notify('data', data);
        },

        subscribe: function (listener) {
            if (typeof listener === 'function') {
                state.listeners.push(listener);
            }
        },

        notify: function (event, payload) {
            for (var i = 0; i < state.listeners.length; i++) {
                try {
                    state.listeners[i](event, payload, state);
                } catch (e) {
                    console.error('Error in state listener:', e);
                }
            }
        }
    };
})();
