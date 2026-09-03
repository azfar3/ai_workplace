"""
ai_workplace/services/cascade_delete.py
────────────────────────────────────────
Targeted cascade deletion for Log and related DocTypes across AI Workplace.
When a record is deleted, checks if matching link or reference fields exist
in target DocTypes (Logs, Conversations, Sessions, Chunks) and cleans up those
linked records.
"""

from __future__ import annotations

from typing import Any
import frappe

TARGET_DOCTYPES = (
    "WhatsApp Message Log",
    "AI Action Log",
    "AI Feedback Log",
    "AI Knowledge Gap Log",
    "AI Workplace Usage Log",
    "AI Security Event",
    "WhatsApp Conversation",
    "HR Live Chat Session",
    "AI Workplace Knowledge Chunk",
    "WhatsApp Security Profile",
)


def handle_cascade_delete(doc: Any, method: str | None = None) -> None:
    """
    Hook called on_trash for any document.
    Checks if target DocTypes contain field options/names linking to doc.doctype,
    and deletes all matching linked records.
    """
    if not doc or not getattr(doc, "doctype", None) or not getattr(doc, "name", None):
        return

    parent_doctype = doc.doctype
    parent_docname = doc.name
    wa_id = getattr(doc, "whatsapp_id", "") or ""

    _cascade_delete_linked_records(parent_doctype, parent_docname, wa_id)


def _cascade_delete_linked_records(parent_doctype: str, parent_docname: str, wa_id: str = "") -> None:
    """Find and delete records in target DocTypes that link to parent_doctype or parent_docname."""
    snake_name = parent_doctype.lower().replace(" ", "_")
    short_snake = snake_name.replace("whatsapp_", "").replace("ai_workplace_", "")

    candidate_fieldnames = {
        snake_name,
        short_snake,
        f"{snake_name}_id",
        f"{snake_name}_name",
        f"{short_snake}_id",
        f"{short_snake}_name",
    }

    for dt in TARGET_DOCTYPES:
        if dt == parent_doctype:
            continue

        try:
            meta = frappe.get_meta(dt)
            fields = meta.get("fields", [])

            for df in fields:
                fname = df.fieldname
                foptions = getattr(df, "options", "") or ""

                # Check if field options or fieldname matches the parent doctype
                if foptions == parent_doctype or fname in candidate_fieldnames:
                    matching_names = frappe.get_all(dt, filters={fname: parent_docname}, pluck="name")
                    for name in matching_names:
                        _safe_delete(dt, name)

                    # Special case for WhatsApp Identity: also check by wa_id if available
                    if parent_doctype == "WhatsApp Identity" and wa_id and fname in ("wa_id", "whatsapp_id"):
                        matching_by_wa_id = frappe.get_all(dt, filters={fname: wa_id}, pluck="name")
                        for name in matching_by_wa_id:
                            _safe_delete(dt, name)

            # Check for generic reference fields (reference_doctype + reference_name)
            has_ref_dt = any(df.fieldname in ("reference_doctype", "ref_doctype", "doctype_name") for df in fields)
            has_ref_dn = any(df.fieldname in ("reference_name", "ref_name", "doc_name") for df in fields)

            if has_ref_dt and has_ref_dn:
                ref_dt_field = (
                    "reference_doctype"
                    if meta.has_field("reference_doctype")
                    else ("ref_doctype" if meta.has_field("ref_doctype") else "doctype_name")
                )
                ref_dn_field = (
                    "reference_name"
                    if meta.has_field("reference_name")
                    else ("ref_name" if meta.has_field("ref_name") else "doc_name")
                )

                matching_refs = frappe.get_all(
                    dt,
                    filters={ref_dt_field: parent_doctype, ref_dn_field: parent_docname},
                    pluck="name",
                )
                for name in matching_refs:
                    _safe_delete(dt, name)

        except Exception as exc:
            frappe.logger("ai_workplace").warning(
                f"Cascade delete check failed for {dt}: {exc}"
            )


def _safe_delete(doctype: str, name: str) -> None:
    """Safely delete a document using Frappe API."""
    if not frappe.db.exists(doctype, name):
        return
    try:
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"Cascade delete warning: failed to delete {doctype} {name}: {exc}"
        )
