# ai_workplace/doctype/ai_workplace_settings/ai_workplace_settings.py

import frappe
from frappe.model.document import Document


class AIWorkplaceSettings(Document):
    """
    AI Workplace Settings — Single DocType.
    Stores Meta/WhatsApp Cloud API configuration.
    All secret fields are stored encrypted via Frappe's Password field type.
    """

    def validate(self):
        """Enforce Phase 1 invariants."""
        if self.proactive_notifications_enabled:
            frappe.throw(
                "Proactive notifications must remain disabled in Phase 1. "
                "This feature is reserved for a future phase.",
                frappe.ValidationError,
            )

        if self.graph_api_version and not self.graph_api_version.startswith("v"):
            self.graph_api_version = f"v{self.graph_api_version}"

        if self.message_retention_days is not None and self.message_retention_days < 1:
            frappe.throw("Message Retention Days must be at least 1")
