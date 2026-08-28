"""
ai_workplace/api/whatsapp_webhook.py
─────────────────────────────────────
Public-facing Frappe API endpoints for Meta WhatsApp Cloud API.

Endpoints
─────────
GET  /api/method/ai_workplace.api.whatsapp_webhook.verify
     Meta webhook verification challenge.

POST /api/method/ai_workplace.api.whatsapp_webhook.receive
     Incoming WhatsApp messages / status updates.

Processing flow (POST):
  1.  Validate X-Hub-Signature-256 (HMAC-SHA256 using Meta App Secret).
  2.  Parse payload via payload_parser.
  3.  Extract message_id (idempotency key).
  4.  Check for duplicate message.
  5.  Create inbound WhatsApp Message Log.
  6.  Normalize sender phone → resolve ERPNext identity.
  7.  Build welcome message.
  8.  Send WhatsApp reply.
  9.  Create outbound WhatsApp Message Log.
  10. Return HTTP 200 to Meta.

Security requirements:
  - Signature must be validated BEFORE any payload processing.
  - Invalid signatures → 403, no message processing, security event logged.
  - Duplicate messages → 200 (acknowledged), no re-processing.
  - Unsupported message types → 200 (acknowledged), no processing.
  - Status events → 200 (acknowledged), no processing.

NOTE: frappe.request is not available in standard @whitelist functions for
raw body access.  We import frappe.local to access request.data.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import frappe
from frappe import _

from werkzeug.wrappers import Response

from ai_workplace.whatsapp.signature import validate_signature, get_app_secret
from ai_workplace.whatsapp.payload_parser import parse_webhook_payload, ParseError
from ai_workplace.whatsapp.sender import send_text_message
from ai_workplace.identity.resolver import resolve_identity
from ai_workplace.services.welcome import build_welcome_message
from ai_workplace.conversation.orchestrator import process_message


# ──────────────────────────────────────────────────────────────────────────────
# Non-recursive Webhook Handlers
# ──────────────────────────────────────────────────────────────────────────────

def _process_verify():
    """
    Handle Meta's GET verification challenge.
    """
    frappe.logger("ai_workplace").info("AI Workplace: Webhook GET verification request received")

    req = getattr(getattr(frappe, "local", None), "request", None)
    args = frappe.form_dict or (getattr(req, "args", {}) if req else {})

    mode = args.get("hub.mode") or args.get("hub_mode") or ""
    token = args.get("hub.verify_token") or args.get("hub_verify_token") or ""
    challenge = args.get("hub.challenge") or args.get("hub_challenge") or ""

    if mode != "subscribe":
        frappe.logger("ai_workplace").warning(f"AI Workplace: Webhook verification failed: invalid hub.mode={mode!r}")
        return Response("Invalid hub.mode", status=400, mimetype="text/plain")

    try:
        settings = frappe.get_single("AI Workplace Settings")
        configured_token = (
            settings.get_password("webhook_verify_token")
            or settings.get("webhook_verify_token")
            or ""
        )
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Settings error during webhook verification: {exc}"
        )
        return Response("Configuration error", status=500, mimetype="text/plain")

    if not configured_token:
        frappe.logger("ai_workplace").error(
            "AI Workplace: Webhook Verify Token is not configured"
        )
        return Response("Webhook verify token not configured", status=500, mimetype="text/plain")

    import hmac as _hmac
    if _hmac.compare_digest(token, configured_token):
        frappe.logger("ai_workplace").info("AI Workplace: Webhook GET verification SUCCESSFUL")
        return Response(str(challenge), status=200, mimetype="text/plain")

    # Token mismatch.
    _log_security_event(
        event_type="Invalid Webhook Verification",
        severity="Medium",
        description=f"Meta verification attempt with incorrect token: {token!r}",
    )
    frappe.logger("ai_workplace").warning(f"AI Workplace: Webhook verify token mismatch. Provided: {token!r}")
    return Response("Forbidden", status=403, mimetype="text/plain")


def _process_receive():
    """
    Handle incoming Meta webhook POST payload processing.
    """
    trace_id = str(uuid.uuid4())
    start_ts = datetime.utcnow()

    frappe.logger("ai_workplace").info(f"AI Workplace [{trace_id}]: Webhook POST received")

    # ── 1. Read raw body for signature validation ─────────────────────────────
    try:
        raw_body = frappe.local.request.data  # bytes
        if not raw_body:
            frappe.logger("ai_workplace").info(f"AI Workplace [{trace_id}]: Empty request body")
            return Response("ok", status=200, mimetype="text/plain")
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace [{trace_id}]: Cannot read request body: {exc}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    # ── 2. Validate signature ─────────────────────────────────────────────────
    sig_header = (
        frappe.local.request.headers.get("X-Hub-Signature-256")
        or frappe.local.request.headers.get("x-hub-signature-256")
        or ""
    )
    app_secret = get_app_secret()

    if not validate_signature(raw_body, sig_header, app_secret):
        _log_security_event(
            event_type="Invalid Webhook Signature",
            severity="High",
            trace_id=trace_id,
            description=(
                f"Webhook POST received with invalid signature. "
                f"Header: {sig_header!r}. Message not processed."
            ),
        )
        frappe.logger("ai_workplace").warning(
            f"AI Workplace [{trace_id}]: Invalid webhook signature (header={sig_header!r}) — rejected"
        )
        return Response("Forbidden", status=403, mimetype="text/plain")

    # ── 3. Parse payload ──────────────────────────────────────────────────────
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace [{trace_id}]: Malformed JSON payload: {exc}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    try:
        parsed = parse_webhook_payload(payload)
    except ParseError as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace [{trace_id}]: ParseError: {exc}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    if parsed is None:
        # No actionable message (e.g. heartbeat).
        return Response("ok", status=200, mimetype="text/plain")

    message_type = parsed.get("message_type", "unknown")

    # ── 4. Acknowledge non-text events early ──────────────────────────────────
    if message_type in ("status", "unsupported"):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Acknowledging {message_type} event "
            f"for message {parsed.get('message_id')}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    # ── 5. Idempotency check ──────────────────────────────────────────────────
    message_id = parsed.get("message_id", "")
    wa_id = parsed.get("wa_id", "")
    raw_phone = parsed.get("phone_number", wa_id)

    if _is_duplicate(message_id):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Duplicate message_id={message_id} — skipped"
        )
        _log_security_event(
            event_type="Duplicate Message",
            severity="Low",
            trace_id=trace_id,
            wa_id=wa_id,
            description=f"Duplicate wamid received: {message_id}",
        )
        return Response("ok", status=200, mimetype="text/plain")

    # ── 6. Log inbound message ────────────────────────────────────────────────
    inbound_log = _create_message_log(
        meta_message_id=message_id,
        direction="Inbound",
        sender=raw_phone,
        recipient="",
        wa_id=wa_id,
        message_type=message_type,
        message=parsed.get("text", ""),
        status="Processing",
        trace_id=trace_id,
    )

    # ── 7. Identity resolution ────────────────────────────────────────────────
    identity = resolve_identity(raw_phone)

    # Update inbound log with identity info.
    _update_log_identity(inbound_log, identity)

    # Log security events for non-matched identities.
    if identity.status in ("ambiguous", "inactive"):
        _log_security_event(
            event_type=f"{identity.status.title()} Identity",
            severity="Medium",
            trace_id=trace_id,
            wa_id=wa_id,
            phone_number=identity.normalized_phone,
            description=f"Identity resolution returned status: {identity.status}",
        )
    elif identity.status == "guest":
        _log_security_event(
            event_type="Unknown Identity",
            severity="Low",
            trace_id=trace_id,
            wa_id=wa_id,
            phone_number=identity.normalized_phone,
            description="No matching ERPNext identity found for incoming WhatsApp number",
        )

    # ── 8. Orchestrate conversation & generate reply ──────────────────────────
    response_text = process_message(
        message_text=parsed.get("text", ""),
        identity=identity,
        message_id=message_id,
        trace_id=trace_id,
        wa_id=wa_id,
    )

    # ── 9. Send WhatsApp reply ────────────────────────────────────────────────
    send_result = send_text_message(
        phone_number=identity.normalized_phone,
        message=response_text,
    )

    # ── 10. Mark inbound log as Received ──────────────────────────────────────
    _finalize_log(inbound_log, status="Received")

    # ── 11. Log outbound message ──────────────────────────────────────────────
    latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

    outbound_status = "Sent" if send_result.get("success") else "Failed"
    outbound_error = send_result.get("error") or ""

    _create_message_log(
        meta_message_id=send_result.get("message_id") or "",
        direction="Outbound",
        sender="",
        recipient=identity.normalized_phone,
        wa_id=wa_id,
        message_type="text",
        message=response_text,
        erp_user=identity.user,
        employee=identity.employee,
        identity_status=identity.status,
        status=outbound_status,
        trace_id=trace_id,
        latency=latency_ms,
        error=outbound_error,
    )

    if not send_result.get("success"):
        frappe.logger("ai_workplace").error(
            f"AI Workplace [{trace_id}]: Failed to send reply: {outbound_error}"
        )

    return Response("ok", status=200, mimetype="text/plain")


# ──────────────────────────────────────────────────────────────────────────────
# Whitelisted Endpoint Dispatchers (Non-recursive)
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def verify():
    """
    Handle Meta's GET verification challenge (or delegate to POST processing).
    """
    req = getattr(getattr(frappe, "local", None), "request", None)
    method_str = getattr(req, "method", "") if req else ""
    args = frappe.form_dict or (getattr(req, "args", {}) if req else {})
    has_hub_mode = bool(args.get("hub.mode") or args.get("hub_mode"))

    if method_str == "POST" or (method_str != "GET" and not has_hub_mode):
        return _process_receive()
    return _process_verify()


@frappe.whitelist(allow_guest=True)
def receive():
    """
    Handle an incoming Meta webhook POST (or delegate to GET verification).
    """
    req = getattr(getattr(frappe, "local", None), "request", None)
    method_str = getattr(req, "method", "") if req else ""
    args = frappe.form_dict or (getattr(req, "args", {}) if req else {})
    has_hub_mode = bool(args.get("hub.mode") or args.get("hub_mode"))

    if method_str == "GET" or has_hub_mode:
        return _process_verify()
    return _process_receive()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _is_duplicate(message_id: str) -> bool:
    """Return True if this Meta message_id has already been processed."""
    if not message_id:
        return False
    return bool(
        frappe.db.exists(
            "WhatsApp Message Log",
            {"meta_message_id": message_id, "direction": "Inbound"},
        )
    )


def _create_message_log(
    *,
    meta_message_id: str,
    direction: str,
    sender: str,
    recipient: str,
    wa_id: str,
    message_type: str,
    message: str,
    erp_user: str = "",
    employee: str = "",
    identity_status: str = "",
    status: str = "Received",
    trace_id: str = "",
    latency: int = 0,
    error: str = "",
) -> "frappe.Document":
    """Create and insert a WhatsApp Message Log record."""
    doc = frappe.new_doc("WhatsApp Message Log")
    doc.meta_message_id = meta_message_id
    doc.direction = direction
    doc.sender = sender
    doc.recipient = recipient
    doc.whatsapp_id = wa_id
    doc.message_type = message_type
    doc.message = message
    doc.erp_user = erp_user or ""
    doc.employee = employee or ""
    doc.identity_status = identity_status or ""
    doc.status = status
    doc.trace_id = trace_id
    doc.latency = latency
    doc.error = error
    doc.timestamp = frappe.utils.now_datetime()
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _update_log_identity(log_doc, identity) -> None:
    """Enrich an existing log record with resolved identity fields."""
    try:
        log_doc.erp_user = identity.user or ""
        log_doc.employee = identity.employee or ""
        log_doc.identity_status = identity.status
        log_doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to update log identity: {exc}"
        )


def _finalize_log(log_doc, status: str) -> None:
    """Update the status of an existing log record."""
    try:
        log_doc.status = status
        log_doc.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to finalize log status: {exc}"
        )


def _log_security_event(
    *,
    event_type: str,
    severity: str,
    trace_id: str = "",
    wa_id: str = "",
    phone_number: str = "",
    erp_user: str = "",
    employee: str = "",
    description: str = "",
) -> None:
    """Create an AI Security Event record."""
    try:
        doc = frappe.new_doc("AI Security Event")
        doc.event_type = event_type
        doc.severity = severity
        doc.whatsapp_id = wa_id
        doc.phone_number = phone_number
        doc.erp_user = erp_user
        doc.employee = employee
        doc.trace_id = trace_id
        doc.description = description
        doc.timestamp = frappe.utils.now_datetime()
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to log security event: {exc}"
        )
