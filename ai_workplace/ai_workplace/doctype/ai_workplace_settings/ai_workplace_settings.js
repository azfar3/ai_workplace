// Copyright (c) 2026, MicroMerger Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Workplace Settings", {
	refresh(frm) {
		if (frm.fields_dict.office_timezone && !frm.doc.office_timezone) {
			frm.set_value("office_timezone", "Asia/Karachi").catch(() => {});
		}
		if (
			frm.doc.hr_live_chat_enabled &&
			frm.fields_dict.hr_working_days &&
			!(frm.doc.hr_working_days || []).length
		) {
			frm.add_custom_button(__("Load Default Working Week"), () => {
				load_default_working_days(frm);
			});
		}
	},
});

function load_default_working_days(frm) {
	const defaults = [
		["Monday", 1, "09:00:00", "18:00:00"],
		["Tuesday", 1, "09:00:00", "18:00:00"],
		["Wednesday", 1, "09:00:00", "18:00:00"],
		["Thursday", 1, "09:00:00", "18:00:00"],
		["Friday", 1, "09:00:00", "18:00:00"],
		["Saturday", 0, "09:00:00", "18:00:00"],
		["Sunday", 0, "09:00:00", "18:00:00"],
	];

	frm.clear_table("hr_working_days");
	defaults.forEach(([day, is_working, start, end]) => {
		frm.add_child("hr_working_days", {
			day_of_week: day,
			is_working_day: is_working,
			start_time: start,
			end_time: end,
		});
	});
	frm.refresh_field("hr_working_days");
}
