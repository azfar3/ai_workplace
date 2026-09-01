# Copyright (c) 2026, MicroMerger and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AIFeedbackLog(Document):
    def after_insert(self):
        """When NOT_HELPFUL feedback is logged, automatically create a candidate Knowledge Gap."""
        if self.feedback_type == "NOT_HELPFUL":
            from ai_workplace.ai_workplace.doctype.ai_knowledge_gap_log.ai_knowledge_gap_log import log_knowledge_gap

            log_knowledge_gap(
                query=self.query,
                context={
                    "employee": self.employee,
                    "user": self.user,
                    "whatsapp_identity": self.whatsapp_identity,
                },
                failure_reason="USER_NEGATIVE_FEEDBACK",
                detected_intent=self.intent or "",
                intent_confidence=self.confidence or 0.0,
                ai_response=self.response or ""
            )
