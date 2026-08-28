"""
ai_workplace/doctype/ai_action_log/ai_action_log.py
────────────────────────────────────────────────────
AI Action Log DocType — Phase 2.
Logs AI, service routing, authorization, and conversation actions.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class AIActionLog(Document):
    """Transaction/Log DocType representing actions processed by AI Workplace."""
    pass
