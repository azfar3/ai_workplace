frappe.pages["ai-workplace-admin"].on_page_load = function (wrapper) {
	frappe.require("/assets/ai_workplace/css/ai_workplace_admin.css");

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "AI Workplace Admin Control Center",
		single_column: true,
	});

	const $root = $(`<div id="ai-workplace-admin-vue"></div>`);
	page.main.empty().append($root);

	function initVueApp() {
		const { createApp, ref, onMounted, computed, watch } = window.Vue;

		const app = createApp({
		template: `
			<div class="ai-workplace-admin">
				<ul class="nav nav-tabs awa-tabs" role="tablist">
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='overview'}" @click.prevent="activeTab='overview'" href="#">Overview</a></li>
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='providers'}" @click.prevent="activeTab='providers'" href="#">Providers</a></li>
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='rag'}" @click.prevent="activeTab='rag'" href="#">RAG & Knowledge</a></li>
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='conversations'}" @click.prevent="activeTab='conversations'" href="#">Conversations</a></li>
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='security'}" @click.prevent="activeTab='security'" href="#">Security</a></li>
					<li class="nav-item"><a class="nav-link" :class="{active: activeTab==='logs'}" @click.prevent="activeTab='logs'" href="#">Activity & Logs</a></li>
				</ul>
				<div class="awa-tab-content" style="padding-top: 1rem;">
					
					<!-- Overview Tab -->
					<div v-if="activeTab==='overview'">
                        <div class="awa-page-header">
                            <div>
                                <h4>System Health: <span class="awa-badge" :class="healthClass">{{ overview.health }}</span></h4>
                                <div class="text-muted">Analytics for the last 30 days.</div>
                            </div>
                            <button class="btn btn-default btn-sm" @click="loadData">Refresh</button>
                        </div>
                        <div v-if="loadingOverview" class="text-muted">Loading overview...</div>
                        <div v-else>
                            <div class="awa-summary-grid">
                                <div class="awa-summary-card">
                                    <div class="label">AI Requests</div>
                                    <div class="value">{{ overview.requests_total }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Success Rate</div>
                                    <div class="value">{{ overview.success_rate }}%</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Avg Latency</div>
                                    <div class="value">{{ overview.avg_latency_ms }} ms</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Total Cost</div>
                                    <div class="value">\${{ overview.total_cost }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Active Conversations</div>
                                    <div class="value">{{ overview.active_conversations }}</div>
                                </div>
                            </div>

                            <div style="margin-top: 2rem;">
                                <h5>Requests & Usage Timeline</h5>
                                <div id="usage-chart"></div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Providers Tab -->
                    <div v-if="activeTab==='providers'">
                        <div class="awa-page-header">
                            <div>
                                <h4>Provider Monitoring & Resilience</h4>
                                <div class="text-muted">Manage Circuit Breaker status and fallback behavior.</div>
                            </div>
                        </div>
                        <div v-if="loadingProviders" class="text-muted">Loading providers...</div>
                        <div v-else>
                            <table class="table table-bordered awa-table">
                                <thead>
                                    <tr>
                                        <th>Provider</th>
                                        <th>Circuit State</th>
                                        <th>Consecutive Failures</th>
                                        <th>Success Rate</th>
                                        <th>Avg Latency</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr v-for="p in providers" :key="p.name">
                                        <td><strong>{{ p.provider_name }}</strong></td>
                                        <td><span class="awa-badge" :class="p.circuit_state === 'CLOSED' ? 'awa-badge-success' : (p.circuit_state === 'HALF_OPEN' ? 'awa-badge-warn' : 'awa-badge-danger')">{{ p.circuit_state }}</span></td>
                                        <td>{{ p.consecutive_failures }}</td>
                                        <td>{{ 100 - p.fail_rate }}%</td>
                                        <td>{{ p.avg_latency }} ms</td>
                                        <td>
                                            <button class="btn btn-default btn-xs" @click="testProvider(p.name)">Test Connection</button>
                                            <button class="btn btn-danger btn-xs" v-if="p.circuit_state !== 'CLOSED'" @click="resetCircuit(p.name)" style="margin-left: 5px;">Reset Circuit</button>
                                            <a class="btn btn-default btn-xs" :href="'/app/ai-workplace-provider/' + encodeURIComponent(p.name)" style="margin-left: 5px;">Edit</a>
                                        </td>
                                    </tr>
                                    <tr v-if="!providers || !providers.length"><td colspan="6" class="text-muted">No providers configured.</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- RAG Tab -->
                    <div v-if="activeTab==='rag'">
                        <div class="awa-page-header">
                            <div>
                                <h4>RAG & Knowledge Dashboard</h4>
                                <div class="text-muted">Vector embedding limits and knowledge gaps.</div>
                            </div>
                            <button class="btn btn-primary btn-sm" @click="reindexAll">Re-index Entire Knowledge Base</button>
                        </div>
                        <div v-if="loadingRag" class="text-muted">Loading RAG metrics...</div>
                        <div v-else>
                            <div class="awa-summary-grid">
                                <div class="awa-summary-card">
                                    <div class="label">Knowledge Sources</div>
                                    <div class="value">{{ rag.sources }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Total Chunks</div>
                                    <div class="value">{{ rag.chunks }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Embedded Chunks</div>
                                    <div class="value">{{ rag.embedded }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Failed Embeddings</div>
                                    <div class="value" :style="{color: rag.failed_embeddings > 0 ? 'red' : 'inherit'}">{{ rag.failed_embeddings }}</div>
                                </div>
                            </div>
                            <h5 style="margin-top: 2rem;">Top Knowledge Gaps</h5>
                            <table class="table table-bordered awa-table">
                                <thead><tr><th>Query</th><th>Frequency</th><th>Status</th><th>Last Seen</th></tr></thead>
                                <tbody>
                                    <tr v-for="g in rag.gaps" :key="g.name">
                                        <td><a :href="'/app/ai-knowledge-gap-log/' + encodeURIComponent(g.name)">{{ g.query }}</a></td>
                                        <td>{{ g.frequency }}</td>
                                        <td>{{ g.status }}</td>
                                        <td>{{ g.last_seen }}</td>
                                    </tr>
                                    <tr v-if="!rag.gaps || !rag.gaps.length"><td colspan="4" class="text-muted">No knowledge gaps recorded.</td></tr>
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <!-- Conversations Tab -->
                    <div v-if="activeTab==='conversations'">
                        <div class="awa-page-header">
                            <div>
                                <h4>Conversation Analytics</h4>
                                <div class="text-muted">Lifecycle of HR chat routing.</div>
                            </div>
                        </div>
                        <div v-if="loadingConv" class="text-muted">Loading conversations...</div>
                        <div v-else>
                            <div class="awa-summary-grid">
                                <div class="awa-summary-card">
                                    <div class="label">Active Sessions</div>
                                    <div class="value">{{ conv.active }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Completed</div>
                                    <div class="value">{{ conv.completed }}</div>
                                </div>
                                <div class="awa-summary-card">
                                    <div class="label">Abandoned</div>
                                    <div class="value">{{ conv.abandoned }}</div>
                                </div>
                            </div>
                            <h5 style="margin-top: 2rem;">Channel Breakdown</h5>
                            <ul class="list-group" style="max-width: 300px;">
                                <li class="list-group-item" v-for="c in conv.channels" :key="c.channel">
                                    {{ c.channel || 'Unknown' }}
                                    <span class="badge">{{ c.cnt }}</span>
                                </li>
                            </ul>
                        </div>
                    </div>

                    <!-- Security Tab -->
                    <div v-if="activeTab==='security'">
                        <div class="awa-page-header">
                            <div>
                                <h4>Security Dashboard</h4>
                                <div class="text-muted">Auditable system blocks and Evidence Gateway actions.</div>
                            </div>
                        </div>
                        <div v-if="loadingSec" class="text-muted">Loading security metrics...</div>
                        <div v-else>
                            <div class="awa-summary-grid">
                                <div class="awa-summary-card">
                                    <div class="label">Blocked / Escalated Actions</div>
                                    <div class="value">{{ sec.blocked_actions }}</div>
                                </div>
                            </div>
                            <div style="margin-top: 1rem;">
                                <a class="btn btn-default btn-sm" href="/app/ai-action-log">View AI Action Logs</a>
                            </div>
                        </div>
                    </div>

                    <!-- Logs Tab -->
                    <div v-if="activeTab==='logs'">
                        <div class="awa-page-header">
                            <div>
                                <h4>Recent AI Activity</h4>
                                <div class="text-muted">Latest 50 usage requests.</div>
                            </div>
                            <a class="btn btn-default btn-sm" href="/app/ai-workplace-usage-log">View All Usage Logs</a>
                        </div>
                        <div v-if="loadingLogs" class="text-muted">Loading activity...</div>
                        <table v-else class="table table-bordered awa-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Channel</th>
                                    <th>Provider (Model)</th>
                                    <th>Latency</th>
                                    <th>Tokens</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="l in logs" :key="l.name">
                                    <td><a :href="'/app/ai-workplace-usage-log/' + encodeURIComponent(l.name)">{{ l.creation }}</a></td>
                                    <td>{{ l.channel }}</td>
                                    <td>{{ l.provider }}<br><span class="text-muted" style="font-size:11px;">{{ l.model }}</span></td>
                                    <td>{{ l.latency_ms }} ms</td>
                                    <td>{{ l.tokens_total }}</td>
                                    <td>
                                        <span class="awa-badge" :class="l.success ? 'awa-badge-success' : 'awa-badge-danger'">
                                            {{ l.success ? 'Success' : 'Failed' }}
                                        </span>
                                        <span v-if="l.fallback_used" class="awa-badge awa-badge-warn" style="margin-left: 5px;">Fallback</span>
                                    </td>
                                </tr>
                                <tr v-if="!logs || !logs.length"><td colspan="6" class="text-muted">No recent AI activity.</td></tr>
                            </tbody>
                        </table>
                    </div>
				</div>
			</div>
		`,
		setup() {
			const activeTab = ref('overview');
			const overview = ref({});
			const loadingOverview = ref(true);

            const providers = ref([]);
            const loadingProviders = ref(true);

            const rag = ref({});
            const loadingRag = ref(true);

            const conv = ref({});
            const loadingConv = ref(true);

            const sec = ref({});
            const loadingSec = ref(true);

            const logs = ref([]);
            const loadingLogs = ref(true);

			const healthClass = computed(() => {
				if (overview.value.health === 'HEALTHY') return 'awa-badge-success';
				if (overview.value.health === 'CRITICAL') return 'awa-badge-danger';
				return 'awa-badge-warn';
			});

            function renderChart(timelineData) {
                if (!timelineData || !timelineData.length) return;
                
                const labels = timelineData.map(d => d.date);
                const reqs = timelineData.map(d => d.total);
                
                new frappe.Chart("#usage-chart", {
                    data: {
                        labels: labels,
                        datasets: [
                            { name: "Requests", type: "bar", values: reqs }
                        ]
                    },
                    title: "Requests Over Time",
                    type: "bar",
                    height: 250,
                    colors: ["#7cd6fd"]
                });
            }

            function loadData() {
                frappe.call({
                    method: "ai_workplace.api.analytics.get_dashboard_summary",
                    callback: (r) => { overview.value = r.message || {}; loadingOverview.value = false; }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_usage_metrics",
                    callback: (r) => { 
                        if (r.message && r.message.timeline) {
                            setTimeout(() => renderChart(r.message.timeline), 300);
                        }
                    }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_provider_health",
                    callback: (r) => { providers.value = r.message || []; loadingProviders.value = false; }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_rag_metrics",
                    callback: (r) => { rag.value = r.message || {}; loadingRag.value = false; }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_conversation_metrics",
                    callback: (r) => { conv.value = r.message || {}; loadingConv.value = false; }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_security_metrics",
                    callback: (r) => { sec.value = r.message || {}; loadingSec.value = false; }
                });
                frappe.call({
                    method: "ai_workplace.api.analytics.get_recent_activity",
                    callback: (r) => { logs.value = r.message || []; loadingLogs.value = false; }
                });
            }

            function testProvider(name) {
                frappe.call({
                    method: "ai_workplace.api.ai_admin.test_provider_connection",
                    args: { provider_name: name },
                    freeze: true,
                    freeze_message: "Testing connection...",
                    callback(res) {
                        const m = res.message || {};
                        if (m.success) {
                            frappe.msgprint({ title: "Connection OK", message: `Latency: ${m.latency || 0}ms`, indicator: "green" });
                        } else {
                            frappe.msgprint({ title: "Connection Failed", message: m.error || "Error", indicator: "red" });
                        }
                    }
                });
            }

            function resetCircuit(name) {
                frappe.confirm(`Are you sure you want to reset the circuit breaker for ${name}?`, () => {
                    frappe.call({
                        method: "ai_workplace.api.analytics.reset_circuit_breaker",
                        args: { provider_name: name },
                        callback(res) {
                            frappe.show_alert({ message: "Circuit reset.", indicator: "green" });
                            loadData();
                        }
                    });
                });
            }

            function reindexAll() {
                frappe.confirm(`Are you sure you want to re-index the entire knowledge base? This operation will run in the background.`, () => {
                    frappe.call({
                        method: "ai_workplace.api.ai_admin.reindex_all_knowledge_sources",
                        callback(res) {
                            frappe.show_alert({ message: "Re-indexing started.", indicator: "green" });
                        }
                    });
                });
            }

            watch(activeTab, (newTab) => {
                if (newTab === 'overview') {
                    frappe.call({
                        method: "ai_workplace.api.analytics.get_usage_metrics",
                        callback: (r) => { 
                            if (r.message && r.message.timeline) {
                                setTimeout(() => renderChart(r.message.timeline), 100);
                            }
                        }
                    });
                }
            });

			onMounted(() => {
				loadData();
			});

			return {
				activeTab,
				overview, loadingOverview, healthClass, loadData,
                providers, loadingProviders, testProvider, resetCircuit,
                rag, loadingRag, reindexAll,
                conv, loadingConv,
                sec, loadingSec,
                logs, loadingLogs
			};
		}
	});

	app.mount("#ai-workplace-admin-vue");
    }

	if (!window.Vue) {
        frappe.require("https://unpkg.com/vue@3/dist/vue.global.prod.js", () => {
            initVueApp();
        });
	} else {
        initVueApp();
    }
};
