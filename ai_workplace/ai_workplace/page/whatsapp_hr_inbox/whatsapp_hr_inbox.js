frappe.pages["whatsapp-hr-inbox"].on_page_load = function (wrapper) {
	frappe.require("/assets/ai_workplace/css/whatsapp_hr_inbox.css", function () {
		frappe.ui.make_app_page({
			parent: wrapper,
			title: __("WhatsApp HR Inbox"),
			single_column: true,
		});
		const page = wrapper.page;
		if (page?.page_actions?.length) {
			page.page_actions.hide();
		}
		frappe.whatsapp_hr_inbox.make(page);
	});
};

const EMOJI_CATEGORIES = {
	smileys: {
		name: "Smileys & Emotion",
		icon: "😀",
		list: [
			"😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇",
			"🙂","😉","😌","😍","🥰","😘","😗","😙","😚","😋",
			"😛","😜","🤪","😝","🤑","🤗","🤭","🤫","🤔","🤐",
			"🤨","😐","😑","😶","😏","😒","🙄","😬","🤥","😌",
			"😔","😪","🤤","😴","😷","🤒","🤕","🤢","🤮","🤧",
			"🥵","🥶","🥴","😵","🤯","🤠","🥳","😎","🤓","🧐",
			"😮","😯","😲","😳","🥺","😦","😧","😨","😰","😥",
			"😢","😭","😱","😖","😣","😞","😓","😩","😫","🥱"
		]
	},
	gestures: {
		name: "People & Gestures",
		icon: "👍",
		list: [
			"👍","👎","👌","✌️","🤞","🤟","🤘","🤙","👈","👉",
			"👆","👇","🖐️","✋","🖖","👋","👏","🙌","👐","🤲",
			"🤝","🙏","✍️","💅","🤳","💪","🦾","👀","👁️","🧑‍💼",
			"👨‍💼","👩‍💼","🙋‍♂️","🙋‍♀️","🙆‍♂️","🙆‍♀️","🙇‍♂️","🙇‍♀️","🤦‍♂️","🤦‍♀️"
		]
	},
	workplace: {
		name: "Work & HR",
		icon: "💼",
		list: [
			"💼","📋","📌","📍","📁","📂","📄","📑","📊","📈",
			"📉","📆","📅","📇","📝","✏️","✒️","✉️","📧","📨",
			"🏢","🏥","🏦","⏰","⏱️","⌛","⏳","💡","🔑","🔒",
			"🔔","📣","📢","💬","🎯","🚀","🎉","🎊","🎁","🏆",
			"🥇","🥈","🥉","✅","❌","❓","❗","ℹ️","⭐","✨"
		]
	},
	hearts: {
		name: "Hearts & Symbols",
		icon: "❤️",
		list: [
			"❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔",
			"❣️","💕","💞","💓","💗","💖","💘","💝","💟","💯",
			"🔥","💥","⚡","🌈","☀️","🌤️","🌧️","❄️","🍀","🌺"
		]
	}
};

frappe.whatsapp_hr_inbox = {
	current_filter: "queue",
	current_session: null,
	_session_data: null,
	_thread_message_ids: new Set(),
	_thread_content_keys: new Set(),
	_poll_timer: null,
	_last_thread_len: 0,

	make(page) {
		this.page = page;
		this.wrapper = $(`
			<div class="wa-inbox">
				<aside class="wa-sidebar">
					<div class="wa-sidebar-header">
						<span class="wa-live-dot"></span>${__("WhatsApp HR Inbox")}
					</div>
					<div class="wa-filters">
						<button class="wa-filter-btn active" data-filter="queue">${__("Queue")}</button>
						<button class="wa-filter-btn" data-filter="mine">${__("My Chats")}</button>
						<button class="wa-filter-btn" data-filter="all">${__("All")}</button>
						<button class="wa-filter-btn" data-filter="closed">${__("Closed")}</button>
					</div>
					<div class="wa-chat-list"></div>
				</aside>
				<main class="wa-chat-panel">
					<header class="wa-chat-header">
						<div class="wa-avatar hr-inbox-avatar">?</div>
						<div class="wa-chat-header-info">
							<div class="wa-chat-header-name hr-inbox-title">${__("Select a chat")}</div>
							<div class="wa-chat-header-sub hr-inbox-subtitle">${__("Pick a conversation from the list")}</div>
						</div>
						<div class="wa-chat-header-actions"></div>
					</header>
					<div class="wa-banner hidden"></div>
					<div class="wa-messages">
						<div class="wa-empty">
							<div class="wa-empty-icon">💬</div>
							<div class="wa-empty-title">${__("WhatsApp HR Live Chat")}</div>
							<div class="wa-empty-sub">${__("Select a chat to view messages. New WhatsApp messages appear here automatically.")}</div>
						</div>
					</div>
					<footer class="wa-compose">
						<div class="wa-emoji-picker hidden">
							<div class="wa-emoji-categories">
								<button type="button" class="wa-emoji-cat-btn active" data-cat="smileys" title="${__("Smileys & Emotion")}">😀</button>
								<button type="button" class="wa-emoji-cat-btn" data-cat="gestures" title="${__("People & Gestures")}">👍</button>
								<button type="button" class="wa-emoji-cat-btn" data-cat="workplace" title="${__("Work & HR")}">💼</button>
								<button type="button" class="wa-emoji-cat-btn" data-cat="hearts" title="${__("Hearts & Symbols")}">❤️</button>
							</div>
							<div class="wa-emoji-search-wrap">
								<input type="text" class="wa-emoji-search-input" placeholder="${__("Search emoji...")}">
							</div>
							<div class="wa-emoji-grid"></div>
						</div>
						<div class="wa-compose-box">
							<button class="wa-attach-btn" disabled title="${__("Attach file or image")}">
								<svg viewBox="0 0 24 24"><path d="M16.5 6v11.5a4 4 0 0 1-8 0V5a2.5 2.5 0 0 1 5 0v10.5a1 1 0 0 1-2 0V6h-1.5v9.5a2.5 2.5 0 0 0 5 0V5a4 4 0 0 0-8 0v12.5a5.5 5.5 0 0 0 11 0V6H16.5z"/></svg>
							</button>
							<button class="wa-emoji-btn" disabled title="${__("Insert Emoji")}">
								<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"/></svg>
							</button>
							<textarea rows="1" placeholder="${__("Type a message")}" disabled></textarea>
							<button class="wa-send-btn" disabled title="${__("Send")}">
								<svg viewBox="0 0 24 24"><path d="M1.101 21.757L23.8 12.029 1.101 2.3l.011 7.912 13.623 1.816-13.623 1.817-.011 7.912z"/></svg>
							</button>
						</div>
					</footer>
				</main>
			</div>
		`).appendTo(page.main);

		// Synchronize theme with Frappe App theme (Light or Dark)
		this.sync_theme();

		page.main.addClass("wa-inbox-page");
		if (page.wrapper) {
			page.wrapper.addClass("wa-inbox-page-wrapper");
		}

		this.list_el = this.wrapper.find(".wa-chat-list");
		this.messages_el = this.wrapper.find(".wa-messages");
		this.banner_el = this.wrapper.find(".wa-banner");
		this.compose_el = this.wrapper.find(".wa-compose textarea");
		this.send_btn = this.wrapper.find(".wa-send-btn");
		this.attach_btn = this.wrapper.find(".wa-attach-btn");
		this.emoji_btn = this.wrapper.find(".wa-emoji-btn");
		this.emoji_picker = this.wrapper.find(".wa-emoji-picker");
		this.title_el = this.wrapper.find(".hr-inbox-title");
		this.subtitle_el = this.wrapper.find(".hr-inbox-subtitle");
		this.avatar_el = this.wrapper.find(".hr-inbox-avatar");
		this.actions_el = this.wrapper.find(".wa-chat-header-actions");

		this.wrapper.find(".wa-filter-btn").on("click", (e) => {
			this.current_filter = $(e.currentTarget).data("filter");
			this.wrapper.find(".wa-filter-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.load_inbox();
		});

		// Attach scroll pagination for Sidebar Chat List
		this.list_el.on("scroll", () => {
			if (this._loading_chats || !this._has_more_chats) return;
			const el = this.list_el[0];
			if (el.scrollTop + el.clientHeight >= el.scrollHeight - 30) {
				this.load_more_chats();
			}
		});

		// Attach scroll-up pagination for Message Panel (Load 10-15 older messages when scrolling above)
		this.messages_el.on("scroll", () => {
			if (this._loading_messages || !this._has_more_messages || !this.current_session) return;
			if (this.messages_el.scrollTop() <= 30) {
				this.load_older_messages();
			}
		});

		this.send_btn.on("click", () => this.send_reply());
		this.attach_btn.on("click", () => this.attach_file());
		this.emoji_btn.on("click", (e) => {
			e.stopPropagation();
			this.toggle_emoji_picker();
		});
		this.emoji_picker.on("click", (e) => e.stopPropagation());
		$(document).on("click", () => this.hide_emoji_picker());

		this.wrapper.find(".wa-emoji-cat-btn").on("click", (e) => {
			const cat = $(e.currentTarget).data("cat");
			this.wrapper.find(".wa-emoji-cat-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.render_emoji_grid(cat, this.wrapper.find(".wa-emoji-search-input").val());
		});

		this.wrapper.find(".wa-emoji-search-input").on("input", (e) => {
			const active_cat = this.wrapper.find(".wa-emoji-cat-btn.active").data("cat") || "smileys";
			this.render_emoji_grid(active_cat, $(e.currentTarget).val());
		});

		this.compose_el.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.send_reply();
			}
		});
		this.compose_el.on("input", function () {
			this.style.height = "auto";
			this.style.height = Math.min(this.scrollHeight, 120) + "px";
		});

		this._realtime_handler = (payload) => this.on_realtime_update(payload);
		this._setup_realtime();

		$(window).on("beforeunload", () => this.stop_live_poll());

		frappe.call({
			method: "ai_workplace.api.hr_chat.get_user_access_info",
			callback: (res) => {
				if (res.message && res.message.role_access === "Assigned HR User (View & Reply Assigned Only)") {
					this.is_assigned_only = true;
					this.current_filter = "mine";
					this.wrapper.find('.wa-filter-btn[data-filter="queue"]').hide();
					this.wrapper.find('.wa-filter-btn[data-filter="all"]').hide();
					this.wrapper.find(".wa-filter-btn").removeClass("active");
					this.wrapper.find('.wa-filter-btn[data-filter="mine"]').addClass("active");
				}
				this.load_inbox();
			},
			error: () => {
				this.load_inbox();
			},
		});
	},

	sync_theme() {
		var isDark = false;
		if (window.frappe && frappe.ui && typeof frappe.ui.is_dark === "function") {
			isDark = frappe.ui.is_dark();
		} else {
			var htmlTheme = document.documentElement.getAttribute("data-theme");
			var bodyTheme = document.body ? document.body.getAttribute("data-theme") : null;
			isDark = (htmlTheme === "dark" || bodyTheme === "dark" || $(document.body).hasClass("dark-mode"));
		}

		if (isDark) {
			this.wrapper.addClass("dark-theme");
		} else {
			this.wrapper.removeClass("dark-theme");
		}
	},

	_setup_realtime() {
		const bind = () => {
			try {
				if (frappe.realtime?.socket) {
					frappe.realtime.socket.off("hr_chat_update", this._realtime_handler);
					frappe.realtime.socket.on("hr_chat_update", this._realtime_handler);
				}
				frappe.realtime.off("hr_chat_update", this._realtime_handler);
				frappe.realtime.on("hr_chat_update", this._realtime_handler);
				if (typeof frappe.realtime.doctype_subscribe === "function") {
					frappe.realtime.doctype_subscribe("HR Live Chat Session");
					frappe.realtime.doctype_subscribe("WhatsApp Message Log");
				}
			} catch (e) {
				console.warn("HR Inbox: realtime bind failed", e);
			}
		};

		if (frappe.realtime?.socket) {
			bind();
			try {
				frappe.realtime.socket.on("connect", bind);
				frappe.realtime.socket.on("reconnect", bind);
			} catch (e) {}
		} else {
			if (typeof frappe.realtime.init === "function") {
				frappe.realtime.init();
			}
			setTimeout(bind, 500);
		}
	},

	on_realtime_update(payload) {
		this.load_inbox(true);

		if (!this.current_session) {
			return;
		}

		if (payload && payload.name && payload.name !== this.current_session) {
			return;
		}

		if (payload && payload.event === "inbound_message" && (payload.message || payload.media_file)) {
			this.append_thread_message({
				direction: "Inbound",
				message: payload.message,
				sender_type: "Employee",
				timestamp: payload.timestamp || frappe.datetime.now_datetime(),
				meta_message_id: payload.meta_message_id || "",
				message_type: payload.message_type || "text",
				media_file: payload.media_file || "",
			});
			this._update_compose_from_payload(payload);
			this.play_notify();
			return;
		}

		if (payload && payload.event === "delivery_status_update") {
			this.update_message_delivery(payload);
			return;
		}

		if (payload && payload.event === "outbound_message" && payload.message) {
			this.append_thread_message({
				direction: "Outbound",
				message: payload.message,
				sender_type: "HR Agent",
				timestamp: payload.timestamp || frappe.datetime.now_datetime(),
				meta_message_id: payload.meta_message_id || "",
				name: payload.log_name || "",
				delivery_status: payload.delivery_status || "Sent",
				status: payload.success === false ? "Failed" : "Sent",
				message_type: payload.message_type || "text",
				media_file: payload.media_file || "",
			});
			return;
		}

		this.refresh_session(true);
	},

	play_notify() {
		try {
			const ctx = new (window.AudioContext || window.webkitAudioContext)();
			const osc = ctx.createOscillator();
			const gain = ctx.createGain();
			osc.connect(gain);
			gain.connect(ctx.destination);
			osc.frequency.value = 880;
			gain.gain.value = 0.05;
			osc.start();
			osc.stop(ctx.currentTime + 0.08);
		} catch (e) {
			/* optional */
		}
	},

	start_live_poll() {
		this.stop_live_poll();
		this._poll_timer = setInterval(() => {
			if (this.current_session) {
				this.refresh_session(true);
			}
		}, 4000);
	},

	stop_live_poll() {
		if (this._poll_timer) {
			clearInterval(this._poll_timer);
			this._poll_timer = null;
		}
	},

	_chat_start: 0,
	_chat_limit: 15,
	_has_more_chats: true,
	_loading_chats: false,

	_msg_start: 0,
	_msg_limit: 15,
	_has_more_messages: true,
	_loading_messages: false,

	load_inbox(silent, append = false) {
		if (!append) {
			this._chat_start = 0;
			this._has_more_chats = true;
		}
		if (this._loading_chats) return;
		this._loading_chats = true;

		frappe.call({
			method: "ai_workplace.api.hr_chat.get_inbox",
			args: {
				status_filter: this.current_filter,
				start: this._chat_start,
				limit: this._chat_limit,
			},
			callback: (r) => {
				this._loading_chats = false;
				const chats = r.message || [];
				if (chats.length < this._chat_limit) {
					this._has_more_chats = false;
				} else {
					this._has_more_chats = true;
				}
				this._chat_start += chats.length;

				this.render_list(chats, append);
				if (!silent && !append && !this.current_session && chats.length) {
					this.load_session(chats[0].name);
				}
			},
			error: () => {
				this._loading_chats = false;
			},
		});
	},

	load_more_chats() {
		this.load_inbox(true, true);
	},

	render_list(sessions, append = false) {
		if (!append) {
			this.list_el.empty();
		}
		if (!sessions.length && !append) {
			this.list_el.append(`
				<div class="wa-empty" style="height:200px;padding:24px;">
					<div class="wa-empty-sub">${__("No chats in this view.")}</div>
				</div>
			`);
			return;
		}

		sessions.forEach((s) => {
			if (this.list_el.find(`.wa-chat-item[data-name="${frappe.utils.escape_html(s.name)}"]`).length) {
				return;
			}
			const title = s.display_title || s.display_name || s.employee_name || s.wa_id || s.name;
			const initial = (title || "?").charAt(0).toUpperCase();
			const subtitle = s.phone || s.wa_id || "";
			const assignee = s.assigned_to_name || s.assigned_to || __("Unassigned");
			const item = $(`
				<div class="wa-chat-item" data-name="${frappe.utils.escape_html(s.name)}">
					<div class="wa-avatar">${frappe.utils.escape_html(initial)}</div>
					<div class="wa-chat-item-body">
						<div class="wa-chat-item-top">
							<span class="wa-chat-item-name">${frappe.utils.escape_html(title)}</span>
						</div>
						<div class="wa-chat-item-preview">${frappe.utils.escape_html(subtitle)} · ${frappe.utils.escape_html(assignee)}</div>
						<span class="wa-badge ${frappe.utils.escape_html(s.status)}">${frappe.utils.escape_html(s.status)}</span>
					</div>
				</div>
			`);
			if (this.current_session === s.name) item.addClass("active");
			item.on("click", () => this.load_session(s.name));
			this.list_el.append(item);
		});
	},

	load_session(name, silent) {
		this.current_session = name;
		this._thread_message_ids = new Set();
		this._thread_content_keys = new Set();
		this._last_thread_len = 0;
		this._msg_start = 0;
		this._has_more_messages = true;
		this._loading_messages = false;
		this.list_el.find(".wa-chat-item").removeClass("active");
		this.list_el.find(".wa-chat-item").each(function () {
			if ($(this).attr("data-name") === name) {
				$(this).addClass("active");
			}
		});
		this.start_live_poll();
		this.refresh_session(silent);
	},

	refresh_session(silent) {
		if (!this.current_session) return;

		frappe.call({
			method: "ai_workplace.api.hr_chat.get_session_detail",
			args: {
				session_name: this.current_session,
				start: 0,
				limit: this._msg_limit,
			},
			callback: (r) => {
				if (!r.message) return;
				const thread = r.message.thread || [];

				this._has_more_messages = !!r.message.has_more_messages;

				if (!this._session_data || this._last_thread_len === 0) {
					this.render_session(r.message);
					this._last_thread_len = thread.length;
				} else {
					thread.forEach((m) => {
						this.append_thread_message(m, true);
					});
					this._update_compose(r.message);
					this.render_banner(r.message);
					this.render_actions(r.message);
					this._last_thread_len = Math.max(this._last_thread_len, thread.length);
				}

				if (thread.length > 0) {
					this.sync_delivery_statuses(thread);
				}

				this._session_data = r.message;
			},
		});
	},

	load_older_messages() {
		if (!this.current_session || this._loading_messages || !this._has_more_messages) return;
		this._loading_messages = true;

		const next_start = this._msg_start + this._msg_limit;
		const prevScrollHeight = this.messages_el[0].scrollHeight;

		if (!this.messages_el.find(".wa-msg-loading").length) {
			this.messages_el.prepend(`
				<div class="wa-msg-loading" style="text-align:center;padding:8px;font-size:12px;color:var(--text-muted,#888);font-weight:500;">
					${__("Loading older messages...")}
				</div>
			`);
		}

		frappe.call({
			method: "ai_workplace.api.hr_chat.get_session_detail",
			args: {
				session_name: this.current_session,
				start: next_start,
				limit: this._msg_limit,
			},
			callback: (r) => {
				this.messages_el.find(".wa-msg-loading").remove();
				this._loading_messages = false;
				if (!r.message) return;

				const older_thread = r.message.thread || [];
				if (!older_thread.length) {
					this._has_more_messages = false;
					return;
				}

				this._msg_start = next_start;
				this._has_more_messages = !!r.message.has_more_messages;

				this.prepend_thread_messages(older_thread);

				const newScrollHeight = this.messages_el[0].scrollHeight;
				this.messages_el.scrollTop(newScrollHeight - prevScrollHeight);
			},
			error: () => {
				this.messages_el.find(".wa-msg-loading").remove();
				this._loading_messages = false;
			},
		});
	},

	prepend_thread_messages(messages) {
		let first_elem = this.messages_el.find(".wa-msg-row, .wa-date-separator").first();
		const msgs = messages.slice().reverse();
		msgs.forEach((m) => {
			const msg_key = this._message_key(m);
			const content_key = this._content_key(m);

			if (this._thread_message_ids.has(msg_key) || this._thread_content_keys.has(content_key)) {
				return;
			}
			this._thread_message_ids.add(msg_key);
			this._thread_content_keys.add(content_key);

			const inbound = m.direction === "Inbound";
			const cls = inbound ? "inbound" : "outbound";
			const time_str = this.format_msg_time(m.timestamp);
			const tick = this.render_tick_html(m);

			const row_html = `
				<div class="wa-msg-row ${cls}" data-key="${frappe.utils.escape_html(msg_key)}">
					<div class="wa-bubble">
						${this.render_message_body(m)}
						<div class="wa-bubble-footer">
							<span class="wa-bubble-time">${time_str}</span>
							<span class="wa-tick-wrap">${tick}</span>
						</div>
					</div>
				</div>
			`;
			if (first_elem.length) {
				$(row_html).insertBefore(first_elem);
				first_elem = this.messages_el.find(".wa-msg-row, .wa-date-separator").first();
			} else {
				this.messages_el.append(row_html);
			}
		});
	},

	render_session(data) {
		const title = data.display_title || data.display_name || data.employee_name || data.wa_id || data.name;
		const initial = (title || "?").charAt(0).toUpperCase();
		const phone = data.phone || data.wa_id || "";
		const status_line = [phone, data.status, data.assigned_to_name ? `${__("HR")}: ${data.assigned_to_name}` : __("Unassigned")]
			.filter(Boolean)
			.join(" · ");

		this.title_el.text(title);
		this.subtitle_el.text(status_line);
		this.avatar_el.text(initial);

		this.render_actions(data);
		this.render_banner(data);
		this.render_thread(data.thread || []);
		this._update_compose(data);
	},

	_update_compose_from_payload(payload) {
		if (payload.can_reply !== undefined) {
			this._update_compose({
				can_reply: payload.can_reply,
				can_reply_reason: payload.can_reply_reason,
			});
		}
	},

	_update_compose(data) {
		const can_reply = !!data.can_reply;
		this.compose_el.prop("disabled", !can_reply);
		this.send_btn.prop("disabled", !can_reply);
		this.attach_btn.prop("disabled", !can_reply);
		if (this.emoji_btn) {
			this.emoji_btn.prop("disabled", !can_reply);
		}
		if (!can_reply) {
			this.hide_emoji_picker();
		}
		this.compose_el.attr(
			"placeholder",
			can_reply ? __("Type a message") : data.can_reply_reason || __("Reply window is closed.")
		);
		if (can_reply) {
			this.send_btn.prop("disabled", false);
		}
	},

	toggle_emoji_picker() {
		if (!this.emoji_btn || this.emoji_btn.prop("disabled")) return;
		if (this.emoji_picker.hasClass("hidden")) {
			this.emoji_picker.removeClass("hidden");
			const active_cat = this.wrapper.find(".wa-emoji-cat-btn.active").data("cat") || "smileys";
			this.render_emoji_grid(active_cat);
		} else {
			this.hide_emoji_picker();
		}
	},

	hide_emoji_picker() {
		if (this.emoji_picker) {
			this.emoji_picker.addClass("hidden");
		}
	},

	render_emoji_grid(cat_key, query = "") {
		const grid = this.wrapper.find(".wa-emoji-grid");
		grid.empty();
		query = (query || "").trim().toLowerCase();

		let list = [];
		if (query) {
			Object.keys(EMOJI_CATEGORIES).forEach((k) => {
				list.push(...EMOJI_CATEGORIES[k].list);
			});
			list = Array.from(new Set(list));
		} else {
			const category = EMOJI_CATEGORIES[cat_key] || EMOJI_CATEGORIES.smileys;
			list = category.list;
		}

		list.forEach((emoji) => {
			$(`<span class="wa-emoji-item">${emoji}</span>`)
				.on("click", () => this.insert_emoji(emoji))
				.appendTo(grid);
		});
	},

	insert_emoji(emoji) {
		const textarea = this.compose_el[0];
		if (!textarea || textarea.disabled) return;

		const start = textarea.selectionStart || 0;
		const end = textarea.selectionEnd || 0;
		const text = textarea.value;

		textarea.value = text.substring(0, start) + emoji + text.substring(end);
		textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
		textarea.focus();

		$(textarea).trigger("input");
	},

	render_banner(data) {
		const messages = [];
		const pkt_label = data.office_local_time ? `${data.office_local_time} PKT` : __("Pakistan time");
		const hr_status = data.hr_support_status || (data.is_office_hours ? "OPEN" : "CLOSED");

		if (hr_status === "OPEN") {
			messages.push(__("HR Support is open ({0}).", [pkt_label]));
		} else if (data.is_holiday) {
			messages.push(__("HR Support is closed — holiday ({0}).", [pkt_label]));
		} else if (!data.is_office_hours) {
			if (data.can_reply) {
				messages.push(
					__(
						"Outside regular HR hours ({0}). You can still reply — chat stays open.",
						[pkt_label]
					)
				);
			} else if (data.status === "Queued") {
				messages.push(__("Outside HR hours ({0}). Take this chat to reply anytime.", [pkt_label]));
			}
		}
		if (!data.can_reply && data.can_reply_reason) {
			messages.push(data.can_reply_reason);
		}

		if (messages.length) {
			this.banner_el.removeClass("hidden").text(messages.join(" · "));
		} else {
			this.banner_el.addClass("hidden").text("");
		}
	},

	render_actions(data) {
		this.actions_el.empty();

		const icon_user = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>`;
		const icon_close = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M18.3 5.71a1 1 0 0 0-1.41 0L12 10.59 7.11 5.7A1 1 0 0 0 5.7 7.11L10.59 12 5.7 16.89a1 1 0 1 0 1.41 1.41L12 13.41l4.89 4.89a1 1 0 0 0 1.41-1.41L13.41 12l4.89-4.89a1 1 0 0 0 0-1.4z"/></svg>`;
		const icon_take = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>`;

		if (data.status === "Queued" && !this.is_assigned_only) {
			$(`<button type="button" class="wa-action-btn wa-action-take">${icon_take}<span>${__("Take Chat")}</span></button>`)
				.on("click", () => this.take_chat(data.name))
				.appendTo(this.actions_el);
		}

		if (!this.is_assigned_only) {
			const assignee_name = data.assigned_to_name || data.assigned_to;
			const assign_label = data.assigned_to ? `${__("Assigned")}: ${assignee_name}` : __("Assign");
			$(`<button type="button" class="wa-action-btn wa-action-assign" title="${__("Click to reassign chat")}">${icon_user}<span>${frappe.utils.escape_html(assign_label)}</span></button>`)
				.on("click", () => this.assign_chat(data.name))
				.appendTo(this.actions_el);
		}

		if (data.status !== "Closed") {
			$(`<button type="button" class="wa-action-btn wa-action-close" title="${__("Close Chat")}">${icon_close}<span>${__("Close")}</span></button>`)
				.on("click", () => this.close_chat(data.name))
				.appendTo(this.actions_el);
		}
	},

	render_thread(messages) {
		this.messages_el.empty();
		this._thread_message_ids = new Set();
		this._thread_content_keys = new Set();
		if (!messages.length) {
			this.messages_el.append(`
				<div class="wa-empty">
					<div class="wa-empty-sub">${__("No messages yet. Waiting for WhatsApp messages…")}</div>
				</div>
			`);
			return;
		}
		let last_date = "";
		messages.forEach((m) => {
			const d = frappe.datetime.str_to_obj(m.timestamp);
			const date_key = d ? frappe.datetime.obj_to_str(d).split(" ")[0] : "";
			if (date_key && date_key !== last_date) {
				last_date = date_key;
				this.messages_el.append(`<div class="wa-date-separator">${frappe.datetime.str_to_user(date_key)}</div>`);
			}
			this.append_thread_message(m, true);
		});
		this.scroll_to_bottom();
	},

	_message_key(message) {
		const text = (message.message || "").trim();
		const dir = message.direction || "";

		if (message.name && !String(message.name).startsWith("initial-") && message.name !== "guest-meta") {
			return `log:${message.name}`;
		}
		const meta = (message.meta_message_id || "").trim();
		if (meta) {
			return `meta:${meta}`;
		}
		return `content:${dir}:${text}:${this._time_bucket(message.timestamp)}`;
	},

	_content_key(message) {
		const text = (message.message || "").trim();
		const dir = message.direction || "";
		const media = (message.media_file || "").trim();
		if (media) {
			return `${dir}:${media}:${this._time_bucket(message.timestamp)}`;
		}
		return `${dir}:${text}:${this._time_bucket(message.timestamp)}`;
	},

	_time_bucket(ts) {
		if (!ts) return "";
		const d = frappe.datetime.str_to_obj(ts);
		if (!d) return String(ts).slice(0, 16);
		const pad = (n) => String(n).padStart(2, "0");
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
	},

	render_tick_html(message) {
		if (message.direction === "Inbound") {
			return "";
		}
		const delivery = (message.delivery_status || "Sent").toLowerCase();
		const log_status = (message.status || "").toLowerCase();
		if (delivery === "failed" || log_status === "failed") {
			return `<span class="wa-tick failed" title="${__("Failed to send")}">!</span>`;
		}
		if (delivery === "read") {
			return this._tick_icon("read", __("Read"));
		}
		if (delivery === "delivered") {
			return this._tick_icon("delivered", __("Delivered"));
		}
		return this._tick_icon("sent", __("Sent"));
	},

	_tick_icon(state, title) {
		const color = state === "read" ? "#53bdeb" : "#8696a0";
		if (state === "sent") {
			return `<span class="wa-tick ${state}" title="${title}"><svg viewBox="0 0 12 11" width="16" height="15" aria-hidden="true"><path fill="${color}" d="M11.154.833 4.605 7.382 1.921 4.698.833 5.786l3.772 3.772 7.14-7.14z"/></svg></span>`;
		}
		return `<span class="wa-tick ${state}" title="${title}"><svg viewBox="0 0 16 11" width="16" height="11" aria-hidden="true"><path fill="${color}" d="M11.071.653a.457.457 0 0 0-.304-.102.493.493 0 0 0-.381.178l-6.19 7.636-2.595-2.02a.488.488 0 0 0-.623.059l-.329.407a.485.485 0 0 0 .059.622l3.137 2.444a.46.46 0 0 0 .377.09.47.47 0 0 0 .304-.178l6.589-8.141a.448.448 0 0 0 .025-.595zm3.653 0a.457.457 0 0 0-.304-.102.493.493 0 0 0-.381.178l-6.19 7.636-1.27-1.27a.427.427 0 0 0-.597-.059l-.294.364a.426.426 0 0 0 .059.597l1.898 1.898a.46.46 0 0 0 .377.09.47.47 0 0 0 .304-.178l6.589-8.141a.448.448 0 0 0 .025-.595z"/></svg></span>`;
	},

	_find_msg_row(key) {
		return this.messages_el.find(".wa-msg-row").filter(function () {
			return $(this).attr("data-key") === key;
		});
	},

	render_message_body(message) {
		const media = (message.media_file || "").trim();
		const msg_type = (message.message_type || "text").toLowerCase();
		let html = "";

		if (media) {
			if (msg_type === "image") {
				html += `<a class="wa-media-link" href="${frappe.utils.escape_html(media)}" target="_blank" rel="noopener"><img class="wa-media-img" src="${frappe.utils.escape_html(media)}" alt=""></a>`;
			} else {
				const label = frappe.utils.escape_html(message.message || media.split("/").pop());
				html += `<a class="wa-media-doc" href="${frappe.utils.escape_html(media)}" target="_blank" rel="noopener"><span class="wa-doc-icon">📎</span><span class="wa-doc-name">${label}</span></a>`;
			}
		}

		const text = (message.message || "").trim();
		if (text && msg_type === "image" && media) {
			html += `<div class="wa-bubble-text">${frappe.utils.escape_html(text)}</div>`;
		} else if (text && !media) {
			html += `<div class="wa-bubble-text">${frappe.utils.escape_html(text)}</div>`;
		} else if (text && media && msg_type !== "image" && text !== media.split("/").pop()) {
			html += `<div class="wa-bubble-text">${frappe.utils.escape_html(text)}</div>`;
		}

		return html || `<div class="wa-bubble-text">${__("(empty message)")}</div>`;
	},

	update_message_delivery(payload) {
		const keys = [];
		if (payload.log_name) keys.push(`log:${payload.log_name}`);
		if (payload.meta_message_id) keys.push(`meta:${payload.meta_message_id}`);
		for (const key of keys) {
			const row = this._find_msg_row(key);
			if (row.length) {
				row.find(".wa-tick-wrap").html(
					this.render_tick_html({
						direction: "Outbound",
						delivery_status: payload.delivery_status,
					})
				);
				return;
			}
		}
	},

	sync_delivery_statuses(thread) {
		(thread || []).forEach((m) => {
			if (m.direction !== "Outbound") return;
			const key = this._message_key(m);
			const row = this._find_msg_row(key);
			if (!row.length) return;
			row.find(".wa-tick-wrap").html(this.render_tick_html(m));
		});
	},

	append_thread_message(message, skip_scroll) {
		const msg_key = this._message_key(message);
		const content_key = this._content_key(message);

		if (this._thread_message_ids.has(msg_key) || this._thread_content_keys.has(content_key)) {
			return;
		}
		this._thread_message_ids.add(msg_key);
		this._thread_content_keys.add(content_key);

		this.messages_el.find(".wa-empty").remove();

		const inbound = message.direction === "Inbound";
		const cls = inbound ? "inbound" : "outbound";
		const time_str = this.format_msg_time(message.timestamp);
		const tick = this.render_tick_html(message);

		this.messages_el.append(`
			<div class="wa-msg-row ${cls}" data-key="${frappe.utils.escape_html(msg_key)}">
				<div class="wa-bubble">
					${this.render_message_body(message)}
					<div class="wa-bubble-footer">
						<span class="wa-bubble-time">${time_str}</span>
						<span class="wa-tick-wrap">${tick}</span>
					</div>
				</div>
			</div>
		`);

		if (!skip_scroll) {
			this.scroll_to_bottom();
		}
	},

	format_msg_time(ts) {
		if (!ts) return "";
		try {
			const d = frappe.datetime.str_to_obj(ts);
			if (!d) return frappe.datetime.prettyDate(ts);
			return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true });
		} catch (e) {
			return frappe.datetime.prettyDate(ts);
		}
	},

	scroll_to_bottom() {
		this.messages_el.scrollTop(this.messages_el[0].scrollHeight);
	},

	take_chat(name) {
		frappe.call({
			method: "ai_workplace.api.hr_chat.take_chat",
			args: { session_name: name },
			callback: () => {
				frappe.show_alert({ message: __("Chat assigned to you"), indicator: "green" });
				this.load_inbox(true);
				this.refresh_session(true);
			},
		});
	},

	assign_chat(name) {
		frappe.call({
			method: "ai_workplace.api.hr_chat.get_hr_agents",
			callback: (r) => {
				const agents = r.message || [];
				const current_assignee = this._session_data?.assigned_to || "";
				const dialog = new frappe.ui.Dialog({
					title: __("Assign / Reassign Chat"),
					fields: [{
						fieldname: "assign_to",
						fieldtype: "Select",
						label: __("HR Agent"),
						options: agents.map((a) => ({ value: a.value, label: a.label })),
						default: current_assignee,
						reqd: 1,
					}],
					primary_action_label: __("Assign"),
					primary_action: (values) => {
						frappe.call({
							method: "ai_workplace.api.hr_chat.assign_chat",
							args: { session_name: name, assign_to: values.assign_to },
							callback: () => {
								dialog.hide();
								frappe.show_alert({ message: __("Chat assigned successfully"), indicator: "green" });
								this.load_inbox(true);
								this.refresh_session(true);
							},
						});
					},
				});
				dialog.show();
			},
		});
	},

	close_chat(name) {
		frappe.confirm(__("Close this HR chat session?"), () => {
			frappe.call({
				method: "ai_workplace.api.hr_chat.close_chat",
				args: { session_name: name },
				callback: () => {
					frappe.show_alert({ message: __("Chat closed"), indicator: "blue" });
					this.current_session = null;
					this.stop_live_poll();
					this.load_inbox();
					this.messages_el.html(`
						<div class="wa-empty">
							<div class="wa-empty-icon">💬</div>
							<div class="wa-empty-title">${__("WhatsApp HR Live Chat")}</div>
							<div class="wa-empty-sub">${__("Select a chat to view messages.")}</div>
						</div>
					`);
				},
			});
		});
	},

	send_reply() {
		const message = (this.compose_el.val() || "").trim();
		if (!message || !this.current_session) return;

		this.hide_emoji_picker();
		this.compose_el.val("").css("height", "auto");
		this.send_btn.prop("disabled", true);
		this.attach_btn.prop("disabled", true);
		if (this.emoji_btn) {
			this.emoji_btn.prop("disabled", true);
		}

		frappe.call({
			method: "ai_workplace.api.hr_chat.send_reply",
			args: { session_name: this.current_session, message },
			callback: () => {
				this.send_btn.prop("disabled", false);
				this.attach_btn.prop("disabled", false);
				if (this.emoji_btn) {
					this.emoji_btn.prop("disabled", false);
				}
				this.refresh_session(true);
			},
			error: () => {
				this.send_btn.prop("disabled", false);
				this.attach_btn.prop("disabled", false);
				if (this.emoji_btn) {
					this.emoji_btn.prop("disabled", false);
				}
			},
		});
	},

	attach_file() {
		if (!this.current_session) return;

		new frappe.ui.FileUploader({
			doctype: "WhatsApp Message Log",
			fieldname: "media_file",
			folder: "Home/Attachments",
			make_attachments_public: true,
			dialog_title: __("Send attachment"),
			restrictions: {
				max_file_size: 16 * 1024 * 1024,
				allowed_file_types: [
					".png",
					".jpg",
					".jpeg",
					".gif",
					".webp",
					".pdf",
					".doc",
					".docx",
					".xls",
					".xlsx",
					".txt",
					".csv",
					".zip",
				],
			},
			on_success: (file_doc) => {
				const file_url = file_doc?.file_url;
				if (!file_url) {
					frappe.msgprint(__("Upload succeeded but file URL was missing."));
					return;
				}
				const caption = (this.compose_el.val() || "").trim();
				this.compose_el.val("").css("height", "auto");
				this.send_btn.prop("disabled", true);
				this.attach_btn.prop("disabled", true);

				frappe.call({
					method: "ai_workplace.api.hr_chat.send_attachment",
					args: {
						session_name: this.current_session,
						file_url,
						caption,
					},
					callback: () => {
						this.send_btn.prop("disabled", false);
						this.attach_btn.prop("disabled", false);
						this.refresh_session(true);
						frappe.show_alert({ message: __("Attachment sent."), indicator: "green" });
					},
					error: (err) => {
						this.send_btn.prop("disabled", false);
						this.attach_btn.prop("disabled", false);
						frappe.msgprint({
							title: __("Could not send attachment"),
							message: err?.message || __("Failed to send file to WhatsApp."),
							indicator: "red",
						});
					},
				});
			},
		});
	},
};
