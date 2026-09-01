"""
WhatsApp notifications for Employee Profile Change Request status updates.
"""

from __future__ import annotations

from typing import Any

import frappe
from ai_workplace.whatsapp.sender import send_message, OutboundMessage


def handle_epcr_update(doc: Any, method: str = "") -> None:
    """Document hook for Employee Profile Change Request on_update."""
    if doc.is_new():
        return

    doc_before = doc.get_doc_before_save()
    if not doc_before:
        return

    previous_state = doc_before.workflow_state
    new_state = doc.workflow_state

    if previous_state != new_state and new_state in ("Approved", "Rejected"):
        # Enqueue async delivery to avoid blocking transaction and avoid rollback on failure
        frappe.enqueue(
            "ai_workplace.services.profile_notifications.send_epcr_notification_async",
            queue="short",
            epcr_name=doc.name,
            new_state=new_state,
            rejection_reason=doc.rejection_reason,
            hr_remarks=doc.hr_remarks,
            is_async=True
        )


@frappe.whitelist()
def send_epcr_notification_async(epcr_name: str, new_state: str, rejection_reason: str = "", hr_remarks: str = ""):
    """Background job for sending EPCR notifications with duplicate prevention."""
    # Idempotency key check
    lock_key = f"ai_workplace:epcr_notification:{epcr_name}:{new_state}"
    if frappe.cache().get_value(lock_key):
        frappe.logger("ai_workplace").info(f"Notification already sent for {epcr_name} state {new_state}")
        return

    doc = frappe.get_doc("Employee Profile Change Request", epcr_name)
    phone = _employee_whatsapp_phone(doc.employee)
    if not phone:
        frappe.logger("ai_workplace").warning(f"No WhatsApp phone found for employee {doc.employee} (EPCR {epcr_name})")
        return

    message_text = _build_message(epcr_name, new_state, rejection_reason, hr_remarks)
    if not message_text:
        return

    # Create idempotency lock
    frappe.cache().set_value(lock_key, "1")

    try:
        outbound = OutboundMessage(body_text=message_text)
        res = send_message(phone, outbound)
        if res.get("success"):
            # Create outbound log
            from ai_workplace.api.whatsapp_webhook import _create_message_log
            _create_message_log(
                meta_message_id=res.get("message_id") or "",
                direction="Outbound",
                sender="",
                recipient=phone,
                wa_id="",
                message_type="text",
                message=message_text,
                erp_user=frappe.db.get_value("Employee", doc.employee, "user_id"),
                employee=doc.employee,
                identity_status="Linked",
                status="Sent",
                trace_id=f"epcr_notify_{epcr_name}",
                latency=0,
                error="",
                sender_type="System",
            )
        else:
            frappe.logger("ai_workplace").error(f"Failed to send EPCR notification {epcr_name}: {res.get('error')}")
            # Do not clear lock so we don't retry endlessly, or clear it if we want retry
            # We'll allow retry by clearing the lock if sending actually failed at WhatsApp level
            frappe.cache().delete_value(lock_key)

    except Exception:
        frappe.cache().delete_value(lock_key)
        frappe.logger("ai_workplace").error(
            f"Error in send_epcr_notification_async for EPCR {epcr_name}\n{frappe.get_traceback()}"
        )


def _employee_whatsapp_phone(employee: str) -> str | None:
    identity = frappe.db.get_value(
        "WhatsApp Identity",
        {"employee": employee, "is_active": 1},
        "normalized_phone",
        order_by="modified desc",
    )
    if identity:
        return identity
    cell = frappe.db.get_value("Employee", employee, "cell_number")
    return cell or None


def _build_message(epcr_name: str, state: str, rejection_reason: str, hr_remarks: str) -> str:
    if state == "Approved":
        return (
            f"Your Employee Profile Change Request has been approved.\n\n"
            f"Request: {epcr_name}\n"
            f"Status: Approved"
        )
    if state == "Rejected":
        reason = rejection_reason or hr_remarks or ""
        msg = (
            f"Your Employee Profile Change Request has been reviewed and rejected.\n\n"
            f"Request: {epcr_name}\n"
            f"Status: Rejected"
        )
        if reason:
            msg += f"\nReason: {reason}"
        return msg
    return ""
