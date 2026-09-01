"""
ai_workplace/api/test_harness.py
─────────────────────────────────
Developer/admin test harness for simulating inbound WhatsApp messages.

IMPORTANT SECURITY:
  - Only accessible to users with "System Manager" role.
  - Passes simulated events through the EXACT SAME pipeline as real webhooks.
  - Does NOT bypass any processing step.
  - By default, the outbound WhatsApp send is mocked to prevent accidental
    real message delivery during testing (pass dry_run=0 to send for real).

Endpoint:
  POST /api/method/ai_workplace.api.test_harness.simulate

Parameters (JSON body):
  phone_number  str   — sender phone (any format)
  wa_id         str   — WhatsApp ID (digits, no +), defaults to phone_number digits
  message_id    str   — simulated Meta message ID (should be unique per test)
  message_type  str   — "text" (default)
  message       str   — message text
  timestamp     str   — Unix timestamp (defaults to now)
  dry_run       int   — 1 = mock send (default), 0 = actually send via Meta API

Returns:
  {
      "trace_id":      str,
      "identity":      dict,
      "welcome":       str,
      "send_result":   dict,
      "inbound_log":   str,   (docname)
      "outbound_log":  str,   (docname)
      "dry_run":       bool,
  }
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import frappe
from frappe import _

from ai_workplace.whatsapp.payload_parser import parse_webhook_payload
from ai_workplace.identity.resolver import resolve_identity
from ai_workplace.services.welcome import build_welcome_message
from ai_workplace.whatsapp.sender import send_message
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.api.whatsapp_webhook import (
    _is_duplicate,
    _create_message_log,
    _update_log_identity,
    _finalize_log,
    _log_security_event,
)


@frappe.whitelist()
def simulate(
    phone_number: str = "",
    wa_id: str = "",
    message_id: str = "",
    message_type: str = "text",
    message: str = "Hello",
    timestamp: str = "",
    dry_run: int = 1,
):
    """
    Simulate an inbound WhatsApp message through the full processing pipeline.
    Accessible to System Manager only.
    """
    # Permission guard.
    if not frappe.has_permission("AI Workplace Settings", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Test harness is restricted to System Manager"), frappe.PermissionError)

    if not phone_number:
        frappe.throw(_("phone_number is required"))

    if not message_id:
        message_id = f"test-{uuid.uuid4()}"

    if not timestamp:
        timestamp = str(int(time.time()))

    if not wa_id:
        import re
        wa_id = re.sub(r"\D", "", phone_number)

    # Build a fake Meta payload so we can reuse the real parser.
    fake_payload = _build_fake_payload(
        wa_id=wa_id,
        message_id=message_id,
        message_type=message_type,
        message_text=message,
        timestamp=timestamp,
    )

    trace_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()

    # ── Parse (same parser as real webhook) ───────────────────────────────────
    parsed = parse_webhook_payload(fake_payload)
    if parsed is None:
        frappe.throw(_("Test payload could not be parsed"))

    actual_message_type = parsed.get("message_type", "unknown")

    # ── Idempotency check ─────────────────────────────────────────────────────
    if _is_duplicate(message_id):
        return {
            "trace_id": trace_id,
            "error": f"Duplicate message_id: {message_id}",
            "identity": None,
            "welcome": None,
            "send_result": None,
            "inbound_log": None,
            "outbound_log": None,
            "dry_run": bool(dry_run),
        }

    # ── Inbound log ───────────────────────────────────────────────────────────
    inbound_log = _create_message_log(
        meta_message_id=message_id,
        direction="Inbound",
        sender=phone_number,
        recipient="",
        wa_id=wa_id,
        message_type=actual_message_type,
        message=parsed.get("text", ""),
        status="Processing",
        trace_id=trace_id,
    )

    # ── Identity resolution ───────────────────────────────────────────────────
    identity = resolve_identity(phone_number)
    _update_log_identity(inbound_log, identity)

    # ── Orchestrate conversation & generate reply ────────────────────────────
    outbound = process_message(
        message_text=parsed.get("text", ""),
        identity=identity,
        message_id=message_id,
        trace_id=trace_id,
        wa_id=wa_id,
    )

    # ── Send (or mock) ────────────────────────────────────────────────────────
    if dry_run:
        send_result = {
            "success": True,
            "message_id": f"mock-{uuid.uuid4()}",
            "error": None,
            "dry_run": True,
        }
    else:
        send_result = send_message(
            phone_number=identity.normalized_phone,
            outbound=outbound,
        )
        send_result["dry_run"] = False

    response_text = outbound.log_text() if hasattr(outbound, "log_text") else str(outbound)

    # ── Finalize inbound log ──────────────────────────────────────────────────
    _finalize_log(inbound_log, status="Received")

    # ── Outbound log ──────────────────────────────────────────────────────────
    latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
    outbound_status = "Sent" if send_result.get("success") else "Failed"

    outbound_log = _create_message_log(
        meta_message_id=send_result.get("message_id") or "",
        direction="Outbound",
        sender="",
        recipient=identity.normalized_phone,
        wa_id=wa_id,
        message_type="text",
        message=response_text,
        erp_user=identity.user or "",
        employee=identity.employee or "",
        identity_status=identity.status,
        status=outbound_status,
        trace_id=trace_id,
        latency=latency_ms,
        error=send_result.get("error") or "",
    )

    return {
        "trace_id": trace_id,
        "identity": identity.to_dict(),
        "welcome": response_text,
        "response": response_text,
        "send_result": send_result,
        "inbound_log": inbound_log.name,
        "outbound_log": outbound_log.name,
        "dry_run": bool(dry_run),
    }


def _build_fake_payload(
    *,
    wa_id: str,
    message_id: str,
    message_type: str,
    message_text: str,
    timestamp: str,
) -> dict:
    """
    Construct a Meta-shaped payload for the parser.
    This is the same structure Meta sends; we're just constructing it locally.
    """
    msg: dict = {
        "from": wa_id,
        "id": message_id,
        "timestamp": timestamp,
        "type": message_type,
    }
    if message_type == "text":
        msg["text"] = {"body": message_text}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "test-entry",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "",
                                "phone_number_id": "test-phone-id",
                            },
                            "contacts": [{"wa_id": wa_id}],
                            "messages": [msg],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
