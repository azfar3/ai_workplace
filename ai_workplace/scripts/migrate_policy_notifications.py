"""
Migrate System Notifications of type 'Policy' directly into AI Workplace Knowledge Chunk.

Usage via bench command:
  bench --site erp.v15 execute ai_workplace.scripts.migrate_policy_notifications.execute
"""

from __future__ import annotations

import frappe
from ai_workplace.services.policy_notifications import sync_all_policy_notifications


def execute(dry_run: bool = False) -> dict:
    """
    Sync all System Notifications of type 'Policy' directly into AI Workplace Knowledge Chunk,
    removing obsolete individual Knowledge Source records.
    """
    if dry_run:
        notifications = frappe.db.get_all(
            "System Notifications",
            filters={"notification_type": "Policy", "is_published": 1},
            pluck="name",
        )
        return {"status": "dry_run", "found": len(notifications)}

    result = sync_all_policy_notifications()
    print(f"Policy Notification Direct Chunk Sync finished: {result}")
    return {"status": "success", **result}
