# Copyright (c) 2026, MicroMerger and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class AIIntentPattern(Document):
    def before_insert(self):
        if not self.normalized_pattern:
            self.normalized_pattern = self.pattern.strip().lower()

def match_intent_pattern(query: str) -> dict | None:
    """Check fast-path intent pattern repository."""
    if not query or not frappe.db.exists("DocType", "AI Intent Pattern"):
        return None
    
    norm = query.strip().lower()
    pattern_name = frappe.db.get_value(
        "AI Intent Pattern",
        {"normalized_pattern": norm, "approved": 1},
        "name"
    )
    if pattern_name:
        doc = frappe.get_doc("AI Intent Pattern", pattern_name)
        doc.usage_count = (doc.usage_count or 0) + 1
        doc.save(ignore_permissions=True)
        import json
        tools = json.loads(doc.tools) if doc.tools else []
        return {
            "intent": doc.intent,
            "tools": tools,
            "confidence": doc.confidence or 0.95
        }
    return None
