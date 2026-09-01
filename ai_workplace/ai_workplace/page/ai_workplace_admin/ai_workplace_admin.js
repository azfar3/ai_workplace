frappe.pages["ai-workplace-admin"].on_page_load = function (wrapper) {
	frappe.require("/assets/ai_workplace/css/ai_workplace_admin.css");

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "AI Workplace Admin",
		single_column: true,
	});

	const $root = $(`
		<div class="ai-workplace-admin">
			<ul class="nav nav-tabs awa-tabs" role="tablist">
				<li class="nav-item"><a class="nav-link active" href="#" data-tab="tab-providers">Providers</a></li>
				<li class="nav-item"><a class="nav-link" href="#" data-tab="tab-models">Models</a></li>
				<li class="nav-item"><a class="nav-link" href="#" data-tab="tab-knowledge">Knowledge</a></li>
				<li class="nav-item"><a class="nav-link" href="#" data-tab="tab-usage">Usage</a></li>
				<li class="nav-item"><a class="nav-link" href="#" data-tab="tab-agents">Agent Settings</a></li>
			</ul>
			<div class="awa-tab-content" style="padding-top: 1rem;">
				<div data-tab-pane="tab-providers"></div>
				<div data-tab-pane="tab-models" style="display:none;"></div>
				<div data-tab-pane="tab-knowledge" style="display:none;"></div>
				<div data-tab-pane="tab-usage" style="display:none;"></div>
				<div data-tab-pane="tab-agents" style="display:none;"></div>
			</div>
		</div>
	`);

	page.main.empty().append($root);

	const panes = {
		providers: $root.find('[data-tab-pane="tab-providers"]'),
		models: $root.find('[data-tab-pane="tab-models"]'),
		knowledge: $root.find('[data-tab-pane="tab-knowledge"]'),
		usage: $root.find('[data-tab-pane="tab-usage"]'),
		agents: $root.find('[data-tab-pane="tab-agents"]'),
	};

	function switch_tab(tab_id) {
		$root.find(".awa-tabs .nav-link").removeClass("active");
		$root.find(`.awa-tabs .nav-link[data-tab="${tab_id}"]`).addClass("active");
		$root.find("[data-tab-pane]").hide();
		$root.find(`[data-tab-pane="${tab_id}"]`).show();
		if (tab_id === "tab-providers") load_providers();
		if (tab_id === "tab-models") load_models();
		if (tab_id === "tab-agents") load_agents();
	}

	$root.find(".awa-tabs .nav-link").on("click", function (e) {
		e.preventDefault();
		switch_tab($(this).data("tab"));
	});

	function esc(s) {
		return frappe.utils.escape_html(String(s ?? ""));
	}

	function summary_cards(items) {
		return `<div class="awa-summary-grid">${items
			.map(
				(c) => `
			<div class="awa-summary-card">
				<div class="label">${esc(c.label)}</div>
				<div class="value">${esc(c.value)}</div>
				${c.sub ? `<div class="sub">${esc(c.sub)}</div>` : ""}
			</div>`
			)
			.join("")}</div>`;
	}

	function load_providers() {
		panes.providers.html(`<div class="text-muted">${__("Loading providers...")}</div>`);
		frappe.call({
			method: "ai_workplace.api.ai_admin.get_providers_dashboard",
			callback(r) {
				const d = r.message || {};
				const s = d.summary || {};
				panes.providers.html(`
					<div class="awa-page-header">
						<div>
							<h4>${__("AI Provider Infrastructure")}<span class="awa-badge awa-badge-danger">${__("Super Admin Only")}</span></h4>
							<div class="text-muted">${__("Configure multi-provider AI engines, encrypted API keys, default models, and fallback rules.")}</div>
						</div>
						<a class="btn btn-primary btn-sm" href="/app/ai-workplace-provider">${__("+ Add AI Provider")}</a>
					</div>
					${summary_cards([
						{ label: __("Active Providers"), value: `${s.active_count || 0} / ${s.total_count || 0}`, sub: __("Ready for AI requests") },
						{ label: __("Default Provider"), value: s.default_provider || "—", sub: s.default_model || "" },
						{ label: __("Key Security"), value: __("Encrypted at Rest"), sub: __("Frappe Password field vault") },
						{ label: __("Fallback Routing"), value: `${s.fallback_count || 0} ${__("Fallbacks")}`, sub: __("Auto rate-limit recovery") },
					])}
					<div class="awa-panel">
						<div class="awa-panel-header">
							<h5>${__("Configured AI Providers")}</h5>
							<button class="btn btn-default btn-xs" id="btn-refresh-providers">${__("Refresh")}</button>
						</div>
						<div class="awa-table-wrap">
							<table class="table table-bordered awa-table">
								<thead>
									<tr>
										<th>${__("Provider")}</th>
										<th>${__("API Base URL")}</th>
										<th>${__("API Key Status")}</th>
										<th>${__("Default Model")}</th>
										<th>${__("Priority")}</th>
										<th>${__("Status")}</th>
										<th>${__("Actions")}</th>
									</tr>
								</thead>
								<tbody>
									${(d.providers || [])
										.map(
											(p) => `
										<tr>
											<td><strong>${esc(p.provider_name)}</strong>${p.is_default ? ` <span class="label label-primary">${__("DEFAULT")}</span>` : ""}</td>
											<td><code>${esc(p.api_base_url)}</code></td>
											<td class="${p.has_api_key ? "awa-status-ok" : "awa-status-warn"}">${p.has_api_key ? __("Configured") : __("Missing Key")}</td>
											<td>${esc(p.default_model || "—")}</td>
											<td>#${esc(p.priority)}</td>
											<td class="${p.is_active ? "awa-status-ok" : ""}">${p.is_active ? __("Active") : __("Inactive")}</td>
											<td>
												<button class="btn btn-default btn-xs btn-test-provider" data-name="${esc(p.name)}">${__("Test Connection")}</button>
												<a class="btn btn-default btn-xs" href="/app/ai-workplace-provider/${encodeURIComponent(p.name)}">${__("Edit")}</a>
											</td>
										</tr>`
										)
										.join("")}
								</tbody>
							</table>
						</div>
					</div>
					<div class="list-group" style="max-width: 480px; margin-top: 1rem;">
						<a class="list-group-item list-group-item-action" href="/app/employee-profile-change-request">${__("Profile Change Requests")}</a>
						<a class="list-group-item list-group-item-action" href="/app/whatsapp-service-security-policy">${__("Service Security Policies")}</a>
					</div>
				`);
				panes.providers.find("#btn-refresh-providers").on("click", load_providers);
				panes.providers.find(".btn-test-provider").on("click", function () {
					const name = $(this).data("name");
					frappe.call({
						method: "ai_workplace.api.ai_admin.test_provider_connection",
						args: { provider_name: name },
						freeze: true,
						freeze_message: __("Testing connection..."),
						callback(res) {
							const m = res.message || {};
							if (m.success) {
								frappe.msgprint({
									title: __("Connection OK"),
									message: `${__("Provider")}: ${esc(m.provider)}<br>${__("Model")}: ${esc(m.model)}<br>${__("Reply")}: ${esc(m.message)}`,
									indicator: "green",
								});
							} else {
								frappe.msgprint({
									title: __("Connection Failed"),
									message: esc(m.error || m.message || __("Unknown error")),
									indicator: "red",
								});
							}
						},
					});
				});
			},
		});
	}

	function load_models() {
		panes.models.html(`<div class="text-muted">${__("Loading models...")}</div>`);
		frappe.call({
			method: "ai_workplace.api.ai_admin.get_models_dashboard",
			callback(r) {
				const d = r.message || {};
				const s = d.summary || {};
				panes.models.html(`
					<div class="awa-page-header">
						<div>
							<h4>${__("AI Models & Capability Registry")}<span class="awa-badge awa-badge-pink">${__("Super Admin Only")}</span></h4>
							<div class="text-muted">${__("Manage vision capabilities and active status across configured AI models.")}</div>
						</div>
						<a class="btn btn-primary btn-sm" href="/app/ai-workplace-model">${__("+ Add AI Model")}</a>
					</div>
					${summary_cards([
						{ label: __("Active Models"), value: `${s.active_count || 0} / ${s.total_count || 0}`, sub: __("Registered in platform") },
					])}
					<div class="awa-panel">
						<div class="awa-panel-header">
							<h5>${esc(s.active_count || 0)} ${__("Active Models")} / ${esc(s.total_count || 0)} ${__("Total")}</h5>
							<button class="btn btn-default btn-xs" id="btn-refresh-models">${__("Refresh")}</button>
						</div>
						<div class="awa-table-wrap">
							<table class="table table-bordered awa-table">
								<thead>
									<tr>
										<th>${__("Model Name / Slug")}</th>
										<th>${__("Provider")}</th>
										<th>${__("Capabilities")}</th>
										<th>${__("Vision")}</th>
										<th>${__("Max Tokens")}</th>
										<th>${__("Active")}</th>
										<th>${__("Actions")}</th>
									</tr>
								</thead>
								<tbody>
									${(d.models || [])
										.map(
											(m) => `
										<tr>
											<td><strong>${esc(m.display_name)}</strong><br><code>${esc(m.model_slug)}</code></td>
											<td>${esc(m.provider)}</td>
											<td>${(m.capabilities || []).map((c) => `<span class="awa-cap-badge">${esc(c)}</span>`).join("")}</td>
											<td class="${m.supports_vision ? "awa-status-ok" : ""}">${m.supports_vision ? __("Supported") : __("—")}</td>
											<td>${esc(m.max_tokens)}</td>
											<td class="${m.is_active ? "awa-status-ok" : ""}">${m.is_active ? __("Yes") : __("No")}</td>
											<td><a class="btn btn-default btn-xs" href="/app/ai-workplace-model/${encodeURIComponent(m.name)}">${__("Edit")}</a></td>
										</tr>`
										)
										.join("")}
								</tbody>
							</table>
						</div>
					</div>
				`);
				panes.models.find("#btn-refresh-models").on("click", load_models);
			},
		});
	}

	panes.knowledge.html(`
		<p>${__("Knowledge sources power the AI HR Agent.")}</p>
		<button class="btn btn-primary btn-sm" id="btn-reindex-all">${__("Re-index All Sources")}</button>
		<div id="reindex-result" style="margin-top: 0.5rem; white-space: pre-wrap; font-size: 12px;"></div>
		<div class="list-group" style="max-width: 480px; margin-top: 1rem;">
			<a class="list-group-item list-group-item-action" href="/app/ai-workplace-knowledge-source">${__("Knowledge Sources")}</a>
			<a class="list-group-item list-group-item-action" href="/app/ai-onboarding-playbook">${__("Onboarding Playbooks")}</a>
		</div>
	`);

	panes.usage.html(`
		<p>${__("AI usage log summary (last 7 days).")}</p>
		<div id="usage-summary">${__("Loading...")}</div>
		<a class="btn btn-default btn-sm" href="/app/ai-workplace-usage-log" style="margin-top: 0.5rem;">${__("View Full Usage Log")}</a>
	`);

	function load_agents() {
		panes.agents.html(`<div class="text-muted">${__("Loading agent settings...")}</div>`);
		frappe.call({
			method: "ai_workplace.api.ai_admin.get_agents_dashboard",
			callback(r) {
				const d = r.message || {};
				const prefs = d.agent_settings || {};
				const agents_html = (d.agents || [])
					.map((a) => {
						const curl = `curl -X POST "${a.endpoint_url}" \\
  -H "Content-Type: application/json" \\
  -H "X-AI-Workplace-Key: YOUR_API_KEY" \\
  -H "X-AI-Workplace-App: hrms_portal" \\
  -d '{"agent_slug": "${a.agent_slug}", "message": "What is the leave policy?", "employee": "EMP-001"}'`;
						return `
						<div class="awa-agent-card" data-slug="${esc(a.agent_slug)}">
							<div class="title-row">
								<h5>${esc(a.agent_name)} <span class="label label-default">${esc(a.agent_type)}</span></h5>
								<span class="${a.is_active ? "awa-status-ok" : "awa-status-warn"}">${a.is_active ? __("Active") : __("Inactive")}</span>
							</div>
							<div class="awa-meta">${__("Slug")}: <code>${esc(a.agent_slug)}</code> · ${__("Model")}: ${esc(a.default_model_slug || "—")}</div>
							<div class="awa-form-row">
								<label>${__("Share with other apps")}</label>
								<input type="checkbox" class="agent-share-toggle" ${a.allow_external_access ? "checked" : ""} />
							</div>
							<div class="awa-form-row">
								<label>${__("Allowed applications")}</label>
								<input type="text" class="form-control input-sm agent-allowed-apps" value="${esc(a.allowed_applications || "")}" placeholder="hrms_portal, ai_analytics, mobile_app" />
							</div>
							<div class="awa-form-row">
								<label>${__("API key")}</label>
								<span class="text-muted">${a.has_api_key ? __("Configured (hidden)") : __("Not generated")}</span>
								<button class="btn btn-default btn-xs btn-gen-key">${__("Generate / Regenerate Key")}</button>
							</div>
							<div class="awa-form-row">
								<label>${__("Endpoint")}</label>
								<input type="text" class="form-control input-sm" readonly value="${esc(a.endpoint_url)}" />
								<button class="btn btn-default btn-xs btn-copy-endpoint">${__("Copy")}</button>
							</div>
							<div class="text-muted" style="font-size:12px;">${__("Integration example")}:</div>
							<div class="awa-code-block agent-curl">${esc(curl)}</div>
							<div style="margin-top:8px;">
								<button class="btn btn-primary btn-xs btn-save-agent">${__("Save Sharing Settings")}</button>
								<a class="btn btn-default btn-xs" href="/app/ai-workplace-agent/${encodeURIComponent(a.name)}">${__("Open Agent Form")}</a>
							</div>
							<div class="agent-key-result text-muted" style="font-size:12px; margin-top:6px;"></div>
						</div>`;
					})
					.join("");

				panes.agents.html(`
					<div class="awa-page-header">
						<div>
							<h4>${__("Agent Sharing & Integration")}</h4>
							<div class="text-muted">${__("Configure agents for WhatsApp, HRMS Portal, mobile apps, and ai_analytics via API key.")}</div>
						</div>
						<a class="btn btn-primary btn-sm" href="/app/ai-workplace-agent">${__("+ Add Agent")}</a>
					</div>
					${agents_html || `<p class="text-muted">${__("No agents configured yet.")}</p>`}
					<div class="awa-panel" style="margin-top: 1rem;">
						<div class="awa-panel-header"><h5>${__("Agent Behaviour Preferences")}</h5></div>
						<div style="padding: 14px;">
							<div class="awa-form-row">
								<label>${__("Proactive notifications")}</label>
								<input type="checkbox" id="pref-proactive" ${prefs.proactive_notifications_enabled ? "checked" : ""} />
							</div>
							<div class="awa-form-row">
								<label>${__("Gap threshold")}</label>
								<input type="number" id="pref-gap" class="form-control input-sm" value="${esc(prefs.proactive_gap_threshold ?? 80)}" />
							</div>
							<div class="awa-form-row">
								<label>${__("Attendance nudge")}</label>
								<input type="checkbox" id="pref-attendance" ${prefs.proactive_attendance_nudge ? "checked" : ""} />
							</div>
							<div class="awa-form-row">
								<label>${__("Cooldown (hours)")}</label>
								<input type="number" id="pref-cooldown" class="form-control input-sm" value="${esc(prefs.proactive_cooldown_hours ?? 24)}" />
							</div>
							<div class="awa-form-row">
								<label>${__("Confidence threshold")}</label>
								<input type="number" step="0.1" id="pref-confidence" class="form-control input-sm" value="${esc(prefs.agent_confidence_threshold ?? 0)}" />
							</div>
							<button class="btn btn-primary btn-sm" id="btn-save-prefs">${__("Save Preferences")}</button>
							<a class="btn btn-default btn-sm" href="/app/ai-workplace-settings">${__("Full Settings Form")}</a>
						</div>
					</div>
				`);

				panes.agents.find(".btn-gen-key").on("click", function () {
					const $card = $(this).closest(".awa-agent-card");
					const slug = $card.data("slug");
					frappe.confirm(__("Regenerating will invalidate the existing API key. Continue?"), () => {
						frappe.call({
							method: "ai_workplace.api.ai_admin.generate_agent_api_key",
							args: { agent_slug: slug },
							freeze: true,
							callback(res) {
								const m = res.message || {};
								if (m.api_key) {
									$card.find(".agent-key-result").html(
										`<strong>${__("New API key (copy now — shown once)")}:</strong><br><code>${esc(m.api_key)}</code>`
									);
									frappe.show_alert({ message: __("API key generated"), indicator: "green" });
								}
							},
						});
					});
				});

				panes.agents.find(".btn-copy-endpoint").on("click", function () {
					const val = $(this).closest(".awa-form-row").find("input").val();
					frappe.utils.copy_to_clipboard(val);
					frappe.show_alert({ message: __("Copied"), indicator: "green" });
				});

				panes.agents.find(".btn-save-agent").on("click", function () {
					const $card = $(this).closest(".awa-agent-card");
					const slug = $card.data("slug");
					frappe.call({
						method: "ai_workplace.api.ai_admin.update_agent_share",
						args: {
							agent_slug: slug,
							allow_external_access: $card.find(".agent-share-toggle").is(":checked") ? 1 : 0,
							allowed_applications: $card.find(".agent-allowed-apps").val(),
						},
						callback() {
							frappe.show_alert({ message: __("Agent sharing updated"), indicator: "green" });
						},
					});
				});

				panes.agents.find("#btn-save-prefs").on("click", function () {
					frappe.call({
						method: "ai_workplace.api.ai_admin.save_agent_preferences",
						args: {
							proactive_notifications_enabled: panes.agents.find("#pref-proactive").is(":checked") ? 1 : 0,
							proactive_gap_threshold: panes.agents.find("#pref-gap").val(),
							proactive_attendance_nudge: panes.agents.find("#pref-attendance").is(":checked") ? 1 : 0,
							proactive_cooldown_hours: panes.agents.find("#pref-cooldown").val(),
							agent_confidence_threshold: panes.agents.find("#pref-confidence").val(),
						},
						callback() {
							frappe.show_alert({ message: __("Preferences saved"), indicator: "green" });
						},
					});
				});
			},
		});
	}

	frappe.call({
		method: "ai_workplace.api.ai_admin.get_usage_summary",
		args: { days: 7 },
		callback(r) {
			const d = r.message || {};
			panes.usage.find("#usage-summary").html(`
				<ul>
					<li>${__("Total calls")}: <strong>${d.total || 0}</strong></li>
					<li>${__("Success")}: <strong>${d.success || 0}</strong></li>
					<li>${__("Failed")}: <strong>${d.failed || 0}</strong></li>
				</ul>
			`);
		},
	});

	panes.knowledge.find("#btn-reindex-all").on("click", function () {
		frappe.call({
			method: "ai_workplace.api.ai_admin.reindex_all_knowledge_sources",
			freeze: true,
			freeze_message: __("Re-indexing knowledge sources..."),
			callback(r) {
				panes.knowledge.find("#reindex-result").text(JSON.stringify(r.message || {}, null, 2));
				frappe.show_alert({ message: __("Re-index complete"), indicator: "green" });
			},
		});
	});

	load_providers();
};
