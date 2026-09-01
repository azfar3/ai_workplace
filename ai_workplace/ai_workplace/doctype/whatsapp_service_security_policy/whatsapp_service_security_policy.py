import frappe
from frappe.model.document import Document


class WhatsAppServiceSecurityPolicy(Document):
    """Maps WhatsApp menu service keys to PIN security levels."""
