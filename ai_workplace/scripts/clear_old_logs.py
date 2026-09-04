"""
ai_workplace/scripts/clear_old_logs.py
────────────────────────────────────────
Clean up transient message logs and AI action logs older than N days (default: 3 days).
Preserves conversations, live chat sessions, and knowledge base sources/entries.

Usage via bench command:
  bench --site erp.v15 execute ai_workplace.scripts.clear_old_logs.execute --kwargs "{'days': 3}"
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, today


LOG_DOCTYPES_TO_PURGE = (
    "WhatsApp Message Log",
    "AI Action Log",
    "AI Workplace Usage Log",
    "AI Security Event",
    "AI Feedback Log",
    "AI Knowledge Gap Log",
)

PRESERVED_DOCTYPES = (
    "WhatsApp Conversation",
    "HR Live Chat Session",
    "AI Workplace Knowledge Source",
    "AI Knowledge Entry",
    "AI Workplace Knowledge Chunk",
)


def execute(days: int = 3, dry_run: bool = False) -> dict:
    """
    Delete log records created more than `days` ago (default 3 days).
    Does NOT touch conversations, live chat threads, or knowledge base records.
    """
    cutoff_date = add_days(today(), -abs(int(days)))
    print(f"Cleaning up logs created on or before {cutoff_date} (older than {days} days)...")

    results = {}
    total_deleted = 0

    for doctype in LOG_DOCTYPES_TO_PURGE:
        if not frappe.db.table_exists(doctype):
            continue

        filters = [["creation", "<=", f"{cutoff_date} 23:59:59.999999"]]
        old_records = frappe.db.get_all(doctype, filters=filters, pluck="name")
        count = len(old_records)

        results[doctype] = count
        print(f"[{doctype}] Found {count} record(s) older than {days} days.")

        if count > 0 and not dry_run:
            # Delete in chunks using frappe.db.delete for fast log purging
            frappe.db.delete(doctype, {"name": ["in", old_records]})
            total_deleted += count

    if not dry_run:
        frappe.db.commit()

    summary = {
        "status": "success",
        "cutoff_date": str(cutoff_date),
        "days_retained": days,
        "total_deleted": total_deleted,
        "details": results,
    }
    print(f"Log cleanup finished. Summary: {summary}")
    return summary
