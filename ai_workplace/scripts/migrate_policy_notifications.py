"""
Migrate System Notifications of type 'Policy' to AI Workplace Knowledge Source.

Usage via bench command:
  bench --site erp.v15 execute ai_workplace.scripts.migrate_policy_notifications.execute
"""

from __future__ import annotations

import re
import frappe
from frappe.utils import strip_html


def clean_text_content(html_content: str) -> str:
    """Clean HTML content into plain text for knowledge indexing."""
    if not html_content:
        return ""
    text = strip_html(html_content or "")
    text = re.sub(r"\n\s*\n", "\n\n", text).strip()
    return text


def execute(dry_run: bool = False) -> dict:
    """
    Fetch all System Notifications where notification_type == 'Policy'
    and create or update corresponding AI Workplace Knowledge Source entries.
    """
    notifications = frappe.db.get_all(
        "System Notifications",
        filters={"notification_type": "Policy"},
        fields=[
            "name",
            "subject",
            "notification_type",
            "version",
            "policy_document",
            "notifiction",
            "last_updated_on",
            "is_published",
        ],
    )

    created_count = 0
    updated_count = 0
    skipped_count = 0
    details = []

    print(f"Found {len(notifications)} System Notification(s) of type 'Policy'.")

    for notif in notifications:
        source_name = (notif.get("subject") or notif.get("name") or "").strip()
        if not source_name:
            skipped_count += 1
            continue

        raw_notif_text = clean_text_content(notif.get("notifiction") or "")
        policy_doc_path = notif.get("policy_document") or ""
        doc_version = notif.get("version") or "1.0"

        existing_name = frappe.db.exists("AI Workplace Knowledge Source", source_name)

        if existing_name:
            doc = frappe.get_doc("AI Workplace Knowledge Source", existing_name)
            doc.source_type = "Policy"
            if policy_doc_path:
                doc.file_attachment = policy_doc_path

            if raw_notif_text and raw_notif_text not in (doc.content or ""):
                doc.content = f"{raw_notif_text}\n\n{doc.content or ''}".strip()

            doc.version = doc_version
            doc.description = f"Migrated from System Notification ({notif.get('name')})"
            doc.is_active = 1

            if not dry_run:
                doc.save(ignore_permissions=True)

            updated_count += 1
            details.append({"action": "updated", "source_name": source_name, "notification_id": notif.get("name")})
            print(f"[UPDATED] AI Workplace Knowledge Source: '{source_name}'")

        else:
            doc = frappe.new_doc("AI Workplace Knowledge Source")
            doc.source_name = source_name
            doc.source_type = "Policy"
            doc.file_attachment = policy_doc_path
            doc.content = raw_notif_text
            doc.version = doc_version
            doc.description = f"Migrated from System Notification ({notif.get('name')})"
            doc.is_active = 1

            if not dry_run:
                doc.insert(ignore_permissions=True)

            created_count += 1
            details.append({"action": "created", "source_name": source_name, "notification_id": notif.get("name")})
            print(f"[CREATED] AI Workplace Knowledge Source: '{source_name}'")

    if not dry_run:
        frappe.db.commit()

    summary = {
        "status": "success",
        "total_found": len(notifications),
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "details": details,
    }
    print(f"Migration finished. Summary: {summary}")
    return summary
