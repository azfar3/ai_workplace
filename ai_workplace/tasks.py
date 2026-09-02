import frappe
from frappe.utils import add_days, now_datetime

@frappe.whitelist()
def cleanup_temporary_media():
    """Remove abandoned WhatsApp Temporary Media and associated Files."""
    expiry_date = add_days(now_datetime(), -1)
    abandoned = frappe.get_all(
        "WhatsApp Temporary Media",
        filters={"creation": ("<", expiry_date), "status": ("in", ["Pending", "Abandoned"])},
        fields=["name", "file_reference"]
    )
    
    for media in abandoned:
        try:
            if media.file_reference:
                frappe.delete_doc("File", media.file_reference, ignore_permissions=True, force=True)
            frappe.delete_doc("WhatsApp Temporary Media", media.name, ignore_permissions=True, force=True)
        except Exception:
            pass


@frappe.whitelist()
def close_inactive_sessions_task():
    """Scheduled task to close inactive WhatsApp conversations and send Bye message."""
    from ai_workplace.conversation.manager import close_inactive_sessions
    return close_inactive_sessions()

