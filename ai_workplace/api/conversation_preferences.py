"""Authenticated self-service reminder preferences; no caller-supplied user ID."""
import frappe


@frappe.whitelist()
def get_preferences():
    from ai_workplace.services.conversation_engagement import preference
    user = frappe.session.user
    if not user or user == 'Guest':
        frappe.throw('Sign in to access reminder preferences.', frappe.PermissionError)
    value = preference(user)
    return dict(value) if value else dict(reminders_enabled=1, quiet_start=20, quiet_end=9, timezone=frappe.utils.get_system_timezone())


@frappe.whitelist(methods=['POST'])
def update_preferences(reminders_enabled, quiet_start=20, quiet_end=9, timezone=None):
    from ai_workplace.services.conversation_engagement import save_preference
    if str(reminders_enabled) not in {'0','1'}:
        frappe.throw('Reminders Enabled must be 0 or 1.')
    return save_preference(frappe.session.user, bool(int(reminders_enabled)), quiet_start, quiet_end, timezone)
