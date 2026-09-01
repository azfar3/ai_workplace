import frappe
from frappe.utils import add_days, nowdatetime

@frappe.whitelist()
def cleanup_temporary_media():
    """Remove abandoned WhatsApp Temporary Media and associated Files."""
    expiry_date = add_days(nowdatetime(), -1)
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
