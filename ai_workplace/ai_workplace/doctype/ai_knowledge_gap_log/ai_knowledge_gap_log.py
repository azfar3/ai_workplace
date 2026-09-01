# Copyright (c) 2026, MicroMerger and contributors
# For license information, please see license.txt

import hashlib
import frappe
from frappe.model.document import Document

class AIKnowledgeGapLog(Document):
    def before_insert(self):
        if not self.normalized_query:
            self.normalized_query = self.query.strip().lower()
        if not self.first_seen:
            self.first_seen = frappe.utils.now_datetime()
        self.last_seen = frappe.utils.now_datetime()

    @frappe.whitelist()
    def create_knowledge_entry(self, title=None, answer=None, category="Policy"):
        """1-Click creation of an AI Knowledge Entry from an HR-resolved Knowledge Gap."""
        if not answer and not self.resolution:
            frappe.throw("Please provide an official resolution / answer before publishing to Knowledge Base.")

        official_answer = answer or self.resolution
        doc_title = title or (self.query[:100] + "...")

        entry = frappe.new_doc("AI Knowledge Entry")
        entry.title = doc_title
        entry.question = self.query
        entry.answer = official_answer
        entry.category = category
        entry.source_type = "HR_RESOLUTION"
        entry.source_reference = self.name
        entry.status = "APPROVED"
        entry.created_from_gap = self.name
        entry.approved_by = frappe.session.user
        entry.approved_on = frappe.utils.now_datetime()
        entry.insert(ignore_permissions=True)

        self.status = "RESOLVED"
        self.save(ignore_permissions=True)

        return entry.name


def log_knowledge_gap(
    query: str,
    context: dict,
    failure_reason: str = "NO_KNOWLEDGE",
    detected_intent: str = "",
    intent_confidence: float = 0.0,
    ai_response: str = ""
) -> str:
    """Helper to record or aggregate knowledge gap queries."""
    if not query:
        return ""
    
    norm = query.strip().lower()
    existing = frappe.db.get_value(
        "AI Knowledge Gap Log",
        {"normalized_query": norm, "status": ["in", ["NEW", "UNDER_REVIEW"]]},
        "name"
    )

    if existing:
        doc = frappe.get_doc("AI Knowledge Gap Log", existing)
        doc.frequency = (doc.frequency or 1) + 1
        doc.last_seen = frappe.utils.now_datetime()
        if ai_response:
            doc.ai_response = ai_response
        doc.save(ignore_permissions=True)
        return doc.name
    else:
        doc = frappe.new_doc("AI Knowledge Gap Log")
        doc.query = query
        doc.normalized_query = norm
        doc.failure_reason = failure_reason
        doc.detected_intent = detected_intent
        doc.intent_confidence = intent_confidence
        doc.ai_response = ai_response
        doc.employee = context.get("employee")
        doc.user = context.get("user")
        doc.whatsapp_identity = context.get("whatsapp_identity")
        doc.insert(ignore_permissions=True)
        return doc.name
