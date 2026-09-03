"""
ai_workplace/services/cascade_delete.py
────────────────────────────────────────
Automatic cascade deletion for linked records across AI Workplace DocTypes.
When a record in an AI Workplace DocType is deleted, all dependent/linked
records within AI Workplace are automatically cleaned up to prevent orphaned records
and avoid LinkExistsError.
"""

from __future__ import annotations

from typing import Any
import frappe

AI_WORKPLACE_DOCTYPES = {
    "WhatsApp Identity",
    "WhatsApp Conversation",
    "HR Live Chat Session",
    "WhatsApp Message Log",
    "WhatsApp Temporary Media",
    "WhatsApp Menu Item",
    "WhatsApp Security Profile",
    "WhatsApp Service Security Policy",
    "AI Workplace Knowledge Source",
    "AI Workplace Knowledge Chunk",
    "AI Workplace Provider",
    "AI Workplace Model",
    "AI Workplace Agent",
    "AI Workplace HR Chat Agent",
    "AI Workplace HR Working Day",
    "AI Workplace Settings",
    "AI Workplace Usage Log",
    "AI Action Log",
    "AI Feedback Log",
    "AI Knowledge Entry",
    "AI Knowledge Gap Log",
    "AI Onboarding Playbook",
    "AI Security Event",
    "AI Intent Pattern",
    "Employee Profile Change Request",
    "Profile Change Item",
    "Groq AI Settings",
}


def handle_cascade_delete(doc: Any, method: str | None = None) -> None:
    """
    Hook called on_trash for any document.
    If the document belongs to AI Workplace, cascade-delete all linked child/referencing
    records in AI Workplace to maintain clean database state and prevent LinkExistsError.
    """
    if not doc or not getattr(doc, "doctype", None) or not getattr(doc, "name", None):
        return

    doctype = doc.doctype
    docname = doc.name

    if doctype not in AI_WORKPLACE_DOCTYPES:
        return

    # Specific high-priority parent-child cascading relationships
    _cascade_delete_specific_relations(doc)

    # Dynamic cascade delete for any other AI Workplace Link fields pointing to this document
    _cascade_delete_dynamic_links(doctype, docname)


def _cascade_delete_specific_relations(doc: Any) -> None:
    doctype = doc.doctype
    docname = doc.name

    if doctype == "WhatsApp Identity":
        # Delete Conversations linked to this Identity
        for conv in frappe.get_all("WhatsApp Conversation", filters={"whatsapp_identity": docname}, pluck="name"):
            _safe_delete("WhatsApp Conversation", conv)

        # Delete HR Live Chat Sessions linked to this Identity
        for session in frappe.get_all("HR Live Chat Session", filters={"whatsapp_identity": docname}, pluck="name"):
            _safe_delete("HR Live Chat Session", session)

        # Delete Message Logs for this Identity
        wa_id = getattr(doc, "whatsapp_id", "") or ""
        filters = []
        if wa_id:
            filters.append({"whatsapp_id": wa_id})
        filters.append({"sender": docname})
        filters.append({"recipient": docname})

        for f in filters:
            for msg in frappe.get_all("WhatsApp Message Log", filters=f, pluck="name"):
                _safe_delete("WhatsApp Message Log", msg)

        # Delete Security Profiles linked to this Identity
        for prof in frappe.get_all("WhatsApp Security Profile", filters={"whatsapp_identity": docname}, pluck="name"):
            _safe_delete("WhatsApp Security Profile", prof)

    elif doctype == "WhatsApp Conversation":
        # Delete HR Live Chat Sessions linked to this Conversation
        for session in frappe.get_all("HR Live Chat Session", filters={"conversation": docname}, pluck="name"):
            _safe_delete("HR Live Chat Session", session)

    elif doctype == "HR Live Chat Session":
        # Delete Message Logs linked to this HR Chat Session
        for msg in frappe.get_all("WhatsApp Message Log", filters={"hr_live_chat_session": docname}, pluck="name"):
            _safe_delete("WhatsApp Message Log", msg)

    elif doctype == "AI Workplace Knowledge Source":
        # Delete Chunks linked to this Knowledge Source
        for chunk in frappe.get_all("AI Workplace Knowledge Chunk", filters={"knowledge_source": docname}, pluck="name"):
            _safe_delete("AI Workplace Knowledge Chunk", chunk)

    elif doctype == "AI Workplace Provider":
        # Delete Models linked to this Provider
        for model in frappe.get_all("AI Workplace Model", filters={"provider": docname}, pluck="name"):
            _safe_delete("AI Workplace Model", model)


def _cascade_delete_dynamic_links(parent_doctype: str, parent_docname: str) -> None:
    """Find and delete any remaining linked records in AI Workplace DocTypes."""
    for dt in AI_WORKPLACE_DOCTYPES:
        if dt == parent_doctype:
            continue
        try:
            meta = frappe.get_meta(dt)
            for df in meta.get("fields", []):
                if df.fieldtype == "Link" and df.options == parent_doctype:
                    fieldname = df.fieldname
                    linked_names = frappe.get_all(dt, filters={fieldname: parent_docname}, pluck="name")
                    for name in linked_names:
                        _safe_delete(dt, name)
        except Exception:
            pass


def _safe_delete(doctype: str, name: str) -> None:
    """Safely delete a document using Frappe API while suppressing recursive link errors."""
    if not frappe.db.exists(doctype, name):
        return
    try:
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"Cascade delete warning: failed to delete {doctype} {name}: {exc}"
        )
