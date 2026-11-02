"""Validate application-owned guidance metadata on approved knowledge records."""
import json


def validate_metadata(doc):
    import frappe
    from ai_workplace.ai.intent_catalog import INTENT_CATALOG
    value = doc.get('guided_questions')
    if value:
        try:
            questions = json.loads(value)
        except (TypeError, ValueError):
            frappe.throw('Guided Questions must be a JSON object.')
            return
        if not isinstance(questions, dict) or any(k not in {'English','Urdu','Roman Urdu'} or not isinstance(v,str) or not v.strip() or len(v)>500 for k,v in questions.items()):
            frappe.throw('Use English, Urdu or Roman Urdu question strings of at most 500 characters.')
    if doc.get('related_intent') and doc.related_intent not in INTENT_CATALOG:
        frappe.throw('Related Intent must be a registered application intent.')
    if doc.get('effective_from') and doc.get('effective_to') and frappe.utils.getdate(doc.effective_from)>frappe.utils.getdate(doc.effective_to):
        frappe.throw('Effective To cannot be before Effective From.')
