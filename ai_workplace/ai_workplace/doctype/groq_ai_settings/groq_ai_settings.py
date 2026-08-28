# ai_workplace/doctype/groq_ai_settings/groq_ai_settings.py

import frappe
from frappe.model.document import Document


class GroqAISettings(Document):
    """
    Groq AI Settings — Phase 2+ preparation.
    No Groq API calls are made in Phase 1.
    """

    def validate(self):
        if self.enabled:
            frappe.msgprint(
                "Groq AI is enabled but will not be called until Phase 2 is implemented.",
                indicator="orange",
                alert=True,
            )
