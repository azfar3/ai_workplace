"""
ai_workplace/services/message_delivery.py
──────────────────────────────────────────
WhatsApp outbound delivery/read status tracking via Meta webhooks.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe

from ai_workplace.services.hr_chat import get_session_doc, publish_session_update

VALID_DELIVERY_STATUSES = frozenset({"sent", "delivered", "read", "failed"})
DELIVERY_RANK = {"failed": 0, "sent": 1, "delivered": 2, "read": 3}


def normalize_delivery_status(status: str) -> str:
    clean = (status or "").strip().lower()
    return {
        "sent": "Sent",
        "delivered": "Delivered",
        "read": "Read",
        "failed": "Failed",
    }.get(clean, "")


def should_advance_delivery(current: str, new: str) -> bool:
    current_key = (current or "Sent").strip().lower()
    new_key = (new or "").strip().lower()
    if new_key == "failed":
        return True
    if current_key == "failed":
        return False
    return DELIVERY_RANK.get(new_key, 0) > DELIVERY_RANK.get(current_key, 1)


def handle_delivery_status_webhook(parsed: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Apply Meta delivery/read webhook to WhatsApp Message Log."""
    meta_message_id = (parsed.get("message_id") or "").strip()
    raw_status = (parsed.get("delivery_status") or "").strip().lower()
    if not meta_message_id or raw_status not in VALID_DELIVERY_STATUSES:
        return None

    log = frappe.db.get_value(
        "WhatsApp Message Log",
        {"meta_message_id": meta_message_id},
        ["name", "delivery_status", "hr_live_chat_session", "direction"],
        as_dict=True,
    )
    if not log or log.direction != "Outbound":
        return None

    new_status = normalize_delivery_status(raw_status)
    current = log.delivery_status or "Sent"
    if not should_advance_delivery(current, new_status):
        return None

    frappe.db.set_value(
        "WhatsApp Message Log",
        log.name,
        "delivery_status",
        new_status,
    )
    frappe.db.commit()

    result = {
        "log_name": log.name,
        "meta_message_id": meta_message_id,
        "delivery_status": new_status,
    }

    if log.hr_live_chat_session:
        try:
            session = get_session_doc(log.hr_live_chat_session)
            publish_session_update(
                session,
                {
                    "event": "delivery_status_update",
                    **result,
                },
            )
        except Exception as exc:
            frappe.logger("ai_workplace").warning(
                f"AI Workplace: Failed to publish delivery status update: {exc}"
            )

    return result
