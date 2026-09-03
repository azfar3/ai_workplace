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
from typing import Any

import frappe
from frappe import _

from werkzeug.wrappers import Response

from ai_workplace.whatsapp.signature import validate_signature, get_app_secret
from ai_workplace.whatsapp.payload_parser import MEDIA_TYPES, parse_webhook_payload, ParseError
from ai_workplace.whatsapp.sender import send_message
from ai_workplace.identity.resolver import resolve_identity, get_or_create_whatsapp_identity
from ai_workplace.services.welcome import build_welcome_message
from ai_workplace.whatsapp.outbound import OutboundMessage
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
    if message_type == "status":
        from ai_workplace.services.message_delivery import handle_delivery_status_webhook

        handle_delivery_status_webhook(parsed)
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Processed delivery status "
            f"{parsed.get('delivery_status')!r} for message {parsed.get('message_id')}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    if message_type == "unsupported":
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Acknowledging {message_type} event "
            f"for message {parsed.get('message_id')}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    if message_type in MEDIA_TYPES:
        return _process_inbound_media(parsed, trace_id)

    if message_type == "location":
        return _process_inbound_location(parsed, trace_id)

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

    # ── 5b. Identity resolution (before log for PIN redaction) ─────────────────
    identity = resolve_identity(raw_phone)
    wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id or "")
    identity.whatsapp_identity = wa_identity_name

    inbound_text = parsed.get("text", "")
    log_message = _redact_inbound_message(wa_identity_name, inbound_text)

    # ── 6. Log inbound message ────────────────────────────────────────────────
    inbound_log = _create_message_log(
        meta_message_id=message_id,
        direction="Inbound",
        sender=raw_phone,
        recipient="",
        wa_id=wa_id,
        message_type=message_type,
        message=log_message,
        status="Processing",
        trace_id=trace_id,
    )

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

    # ── 7. Enqueue background processing if async is enabled ─────────────────
    use_async = not bool(getattr(frappe.flags, "in_test", False))
    try:
        settings = frappe.get_single("AI Workplace Settings")
        if hasattr(settings, "async_whatsapp_enabled") and not settings.async_whatsapp_enabled:
            use_async = False
    except Exception:
        pass

    if use_async:
        frappe.enqueue(
            "ai_workplace.api.whatsapp_webhook.process_async_whatsapp_message",
            queue="short",
            timeout=120,
            is_async=True,
            inbound_log_name=inbound_log.name,
            message_id=message_id,
            wa_id=wa_id,
            raw_phone=raw_phone,
            message_text=inbound_text,
            trace_id=trace_id,
        )
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Enqueued background job for message_id={message_id}"
        )
        return Response("ok", status=200, mimetype="text/plain")

    # ── 8. Orchestrate conversation & generate reply (Synchronous / Test mode)
    outbound = None
    processing_error = ""
    try:
        outbound = process_message(
            message_text=parsed.get("text", ""),
            identity=identity,
            message_id=message_id,
            trace_id=trace_id,
            wa_id=wa_id,
        )
    except Exception:
        processing_error = frappe.get_traceback()
        frappe.log_error(
            title=f"WhatsApp orchestrator failed [{trace_id}]",
            message=processing_error,
        )
        outbound = OutboundMessage(
            body_text=(
                "Sorry, something went wrong while opening that service. "
                "Please try again in a moment or type *menu*."
            )
        )

    if outbound is None:
        outbound = OutboundMessage(
            body_text="Sorry, we could not process your request. Please type *menu* to continue."
        )

    # ── 9. Send WhatsApp reply ────────────────────────────────────────────────
    skip_send = isinstance(outbound, OutboundMessage) and outbound.skip_send
    if skip_send:
        send_result = {"success": True, "message_id": "", "skipped": True}
    else:
        send_result = send_message(
            phone_number=identity.normalized_phone,
            outbound=outbound,
        )
    _maybe_store_attendance_location_request_id(
        identity, outbound, send_result, wa_id=wa_id, trace_id=trace_id
    )

    response_text = outbound.log_text() if hasattr(outbound, "log_text") else str(outbound)
    outbound_type = outbound.message_type if hasattr(outbound, "message_type") else "text"

    # ── 10. Mark inbound log as Received ──────────────────────────────────────
    _finalize_log(inbound_log, status="Received")

    # Link inbound message to active HR chat session when applicable
    _link_inbound_to_hr_session(inbound_log, identity, parsed.get("text", ""))

    # ── 11. Log outbound message ──────────────────────────────────────────────
    latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

    if not skip_send:
        outbound_status = "Sent" if send_result.get("success") else "Failed"
        outbound_error = send_result.get("error") or ""

        _create_message_log(
            meta_message_id=send_result.get("message_id") or "",
            direction="Outbound",
            sender="",
            recipient=identity.normalized_phone,
            wa_id=wa_id,
            message_type=outbound_type,
            message=response_text,
            erp_user=identity.user,
            employee=identity.employee,
            identity_status=identity.status,
            status=outbound_status,
            trace_id=trace_id,
            latency=latency_ms,
            error=outbound_error,
            sender_type="System",
        )

        if not send_result.get("success"):
            frappe.logger("ai_workplace").error(
                f"AI Workplace [{trace_id}]: Failed to send reply: {outbound_error}"
            )

    return Response("ok", status=200, mimetype="text/plain")


@frappe.whitelist(allow_guest=True)
def process_async_whatsapp_message(
    inbound_log_name: str = "",
    message_id: str = "",
    wa_id: str = "",
    raw_phone: str = "",
    message_text: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    """
    Background worker job for processing incoming WhatsApp messages asynchronously.
    Enforces idempotency to prevent duplicate outbound messages.
    """
    if not message_id or not inbound_log_name:
        return {"success": False, "error": "Missing log name or message ID"}

    lock_key = f"ai_workplace:job_processed:{message_id}"
    if frappe.cache().get_value(lock_key):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Skipping background processing for message_id={message_id} (already completed)"
        )
        return {"success": True, "skipped": True}

    if frappe.db.exists("WhatsApp Message Log", {"meta_message_id": message_id, "direction": "Outbound"}):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Skipping background processing for message_id={message_id} (outbound already exists)"
        )
        frappe.cache().set_value(lock_key, "1")
        return {"success": True, "skipped": True}

    start_ts = datetime.utcnow()

    identity = resolve_identity(raw_phone)
    wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id or "")
    identity.whatsapp_identity = wa_identity_name

    inbound_log = frappe.get_doc("WhatsApp Message Log", inbound_log_name)

    outbound = None
    processing_error = ""

    try:
        outbound = process_message(
            message_text=message_text,
            identity=identity,
            message_id=message_id,
            trace_id=trace_id,
            wa_id=wa_id,
        )
    except Exception:
        processing_error = frappe.get_traceback()
        frappe.log_error(
            title=f"WhatsApp async worker failed [{trace_id}]",
            message=processing_error,
        )
        _handle_async_job_failure(inbound_log, identity, trace_id, processing_error)
        outbound = OutboundMessage(
            body_text=(
                "We experienced a temporary issue while processing your request. "
                "Please try again in a moment or type *menu*."
            )
        )

    if outbound is None:
        outbound = OutboundMessage(
            body_text="Sorry, we could not process your request. Please type *menu* to continue."
        )

    skip_send = isinstance(outbound, OutboundMessage) and outbound.skip_send
    if skip_send:
        send_result = {"success": True, "message_id": "", "skipped": True}
    else:
        send_result = send_message(
            phone_number=identity.normalized_phone,
            outbound=outbound,
        )
    _maybe_store_attendance_location_request_id(
        identity, outbound, send_result, wa_id=wa_id, trace_id=trace_id
    )

    response_text = outbound.log_text() if hasattr(outbound, "log_text") else str(outbound)
    outbound_type = outbound.message_type if hasattr(outbound, "message_type") else "text"

    _finalize_log(inbound_log, status="Received")
    _link_inbound_to_hr_session(inbound_log, identity, message_text)

    latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

    if not skip_send:
        outbound_status = "Sent" if send_result.get("success") else "Failed"
        outbound_error = send_result.get("error") or ""

        _create_message_log(
            meta_message_id=send_result.get("message_id") or "",
            direction="Outbound",
            sender="",
            recipient=identity.normalized_phone,
            wa_id=wa_id,
            message_type=outbound_type,
            message=response_text,
            erp_user=identity.user,
            employee=identity.employee,
            identity_status=identity.status,
            status=outbound_status,
            trace_id=trace_id,
            latency=latency_ms,
            error=outbound_error,
            sender_type="System",
        )

    frappe.cache().set_value(lock_key, "1")
    return {"success": True}


def _handle_async_job_failure(
    inbound_log: Any,
    identity: Any,
    trace_id: str,
    error_trace: str,
) -> None:
    """Part J: Job Failure Handling — update conversation, log failure, notify escalation."""
    try:
        _finalize_log(inbound_log, status="Failed")
        from ai_workplace.conversation.manager import get_or_create_conversation, update_conversation
        from ai_workplace.conversation.state import ConversationState

        conv = get_or_create_conversation(identity, trace_id=trace_id)
        if conv.current_state == ConversationState.PROCESSING:
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None)

        _log_security_event(
            event_type="Async Worker Failure",
            severity="Medium",
            trace_id=trace_id,
            wa_id=getattr(identity, "wa_id", ""),
            description=f"Async job failed permanently for log {inbound_log.name}: {error_trace[:300]}",
        )
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Failed to execute job failure cleanup: {exc}")


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
    hr_live_chat_session: str = "",
    sender_type: str = "",
    media_file: str = "",
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
    doc.media_file = media_file or ""
    doc.erp_user = erp_user or ""
    doc.employee = employee or ""
    doc.identity_status = identity_status or ""
    doc.status = status
    doc.trace_id = trace_id
    doc.latency = latency
    doc.error = error
    doc.hr_live_chat_session = hr_live_chat_session or ""
    doc.sender_type = sender_type or ""
    doc.timestamp = frappe.utils.now_datetime()
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _update_log_identity(log_doc, identity) -> None:
    """Enrich an existing log record with resolved identity fields."""
    try:
        frappe.db.set_value(
            "WhatsApp Message Log",
            log_doc.name,
            {
                "erp_user": identity.user or "",
                "employee": identity.employee or "",
                "identity_status": identity.status,
            },
            update_modified=False,
        )
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to update log identity: {exc}"
        )


def _finalize_log(log_doc, status: str) -> None:
    """Update the status of an existing log record."""
    try:
        frappe.db.set_value(
            "WhatsApp Message Log",
            log_doc.name,
            "status",
            status,
            update_modified=False,
        )
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to finalize log status: {exc}"
        )


def _link_inbound_to_hr_session(
    log_doc,
    identity,
    message_text: str,
    *,
    message_type: str = "text",
    media_file: str = "",
) -> None:
    """Attach inbound WhatsApp Message Log to an active HR live chat session."""
    try:
        wa_identity = getattr(identity, "whatsapp_identity", "") or ""
        if not wa_identity:
            return

        from ai_workplace.services.hr_chat import get_active_session_for_identity

        session_name = get_active_session_for_identity(wa_identity)
        if not session_name:
            conv_name = frappe.db.get_value(
                "WhatsApp Conversation",
                {
                    "whatsapp_identity": wa_identity,
                    "conversation_status": "Active",
                    "current_state": "LIVE_HR_CHAT",
                },
                "name",
            )
            if conv_name:
                session_name = frappe.db.get_value(
                    "WhatsApp Conversation",
                    conv_name,
                    "active_hr_chat_session",
                )
        if not session_name:
            return

        if not log_doc.hr_live_chat_session:
            frappe.db.set_value(
                "WhatsApp Message Log",
                log_doc.name,
                {
                    "hr_live_chat_session": session_name,
                    "sender_type": "Employee",
                },
            )
            frappe.db.commit()

        from ai_workplace.services.hr_chat import get_session_doc, publish_session_update

        session = get_session_doc(session_name)
        publish_session_update(
            session,
            {
                "event": "inbound_message",
                "message": message_text,
                "meta_message_id": log_doc.meta_message_id or log_doc.name,
                "direction": "Inbound",
                "sender_type": "Employee",
                "timestamp": frappe.utils.now(),
                "message_type": message_type or "text",
                "media_file": media_file or log_doc.media_file or "",
            },
        )
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"AI Workplace: Failed to link inbound message to HR session: {exc}"
        )


def _process_inbound_media(parsed: dict, trace_id: str) -> Response:
    """Handle inbound WhatsApp image/document/video/audio messages."""
    message_id = parsed.get("message_id", "")
    wa_id = parsed.get("wa_id", "")
    raw_phone = parsed.get("phone_number", wa_id)
    message_type = parsed.get("message_type", "media")

    if _is_duplicate(message_id):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Duplicate media message_id={message_id} — skipped"
        )
        return Response("ok", status=200, mimetype="text/plain")

    identity = resolve_identity(raw_phone)
    wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id or "")
    identity.whatsapp_identity = wa_identity_name

    from ai_workplace.whatsapp.media import fetch_inbound_media

    media_result = fetch_inbound_media(parsed)
    file_url = media_result.get("file_url") or ""
    display_message = (parsed.get("text") or "").strip()
    if not display_message:
        display_message = media_result.get("filename") or _("[Media]")

    inbound_log = _create_message_log(
        meta_message_id=message_id,
        direction="Inbound",
        sender=raw_phone,
        recipient="",
        wa_id=wa_id,
        message_type=message_type,
        message=display_message,
        status="Processing",
        trace_id=trace_id,
        media_file=file_url,
    )
    _update_log_identity(inbound_log, identity)

    if not media_result.get("success"):
        frappe.logger("ai_workplace").warning(
            f"AI Workplace [{trace_id}]: Media download failed for {message_id}: "
            f"{media_result.get('error')}"
        )

    from ai_workplace.services.hr_chat import (
        append_inbound_message,
        get_active_session_for_identity,
        get_session_doc,
    )
    from ai_workplace.conversation.manager import (
        get_or_create_conversation,
        conversation_priority_expects_media,
    )

    conv_for_route = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id)
    priority_media_flow = conversation_priority_expects_media(conv_for_route)

    session_name = get_active_session_for_identity(wa_identity_name)
    if not session_name:
        conv_name = frappe.db.get_value(
            "WhatsApp Conversation",
            {
                "whatsapp_identity": wa_identity_name,
                "conversation_status": "Active",
                "current_state": "LIVE_HR_CHAT",
            },
            "name",
        )
        if conv_name:
            session_name = frappe.db.get_value(
                "WhatsApp Conversation",
                conv_name,
                "active_hr_chat_session",
            )

    if session_name and not priority_media_flow:
        session = get_session_doc(session_name)
        if session.ready_for_hr and session.status in ("Queued", "Assigned", "Active"):
            _finalize_log(inbound_log, status="Received")
            append_inbound_message(
                session,
                display_message,
                meta_message_id=message_id,
                message_type=message_type,
                media_file=file_url,
            )
            frappe.logger("ai_workplace").info(
                f"AI Workplace [{trace_id}]: Stored inbound {message_type} for HR session {session_name}"
            )
            return Response("ok", status=200, mimetype="text/plain")

    if file_url:
        # Track media temporarily for multi-step workflows
        if media_result.get("file_doc_name") and conv_for_route:
            try:
                frappe.get_doc({
                    "doctype": "WhatsApp Temporary Media",
                    "conversation_id": conv_for_route.name,
                    "employee": identity.employee if identity.is_employee else "",
                    "document_type": message_type,
                    "media_id": parsed.get("media_id", ""),
                    "file_reference": media_result.get("file_doc_name"),
                    "status": "Pending"
                }).insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                frappe.log_error(title="Failed to track temporary media", message=frappe.get_traceback())

        from ai_workplace.conversation.orchestrator import process_inbound_media
        from ai_workplace.whatsapp.sender import send_message

        try:
            outbound = process_inbound_media(
                identity=identity,
                file_url=file_url,
                filename=media_result.get("filename") or display_message,
                message_id=message_id,
                trace_id=trace_id,
                wa_id=wa_id,
            )
        except Exception as exc:
            frappe.log_error(title="WhatsApp media flow failed", message=frappe.get_traceback())
            outbound = OutboundMessage(
                body_text=_("Sorry, we could not process your file. Please try sending it again.")
            )

        if outbound is not None:
            _finalize_log(inbound_log, status="Received")
            send_result = send_message(phone_number=identity.normalized_phone, outbound=outbound)
            _create_message_log(
                meta_message_id=send_result.get("message_id") or "",
                direction="Outbound",
                sender="",
                recipient=identity.normalized_phone,
                wa_id=wa_id,
                message_type=outbound.message_type if hasattr(outbound, "message_type") else "text",
                message=outbound.log_text() if hasattr(outbound, "log_text") else str(outbound),
                status="Sent" if send_result.get("success") else "Failed",
                trace_id=trace_id,
            )
            frappe.logger("ai_workplace").info(
                f"AI Workplace [{trace_id}]: Processed inbound {message_type} for deliverable flow"
            )
            return Response("ok", status=200, mimetype="text/plain")

    # Media download failed — notify user if they are mid profile upload flow.
    from ai_workplace.conversation.orchestrator import process_inbound_media_failure
    from ai_workplace.whatsapp.sender import send_message

    fail_out = process_inbound_media_failure(
        identity=identity,
        message_id=message_id,
        trace_id=trace_id,
        wa_id=wa_id,
        error=media_result.get("error") or "download failed",
    )
    if fail_out is not None:
        _finalize_log(inbound_log, status="Received")
        send_result = send_message(phone_number=identity.normalized_phone, outbound=fail_out)
        _create_message_log(
            meta_message_id=send_result.get("message_id") or "",
            direction="Outbound",
            sender="",
            recipient=identity.normalized_phone,
            wa_id=wa_id,
            message_type="text",
            message=fail_out.log_text() if hasattr(fail_out, "log_text") else str(fail_out),
            status="Sent" if send_result.get("success") else "Failed",
            trace_id=trace_id,
        )
        return Response("ok", status=200, mimetype="text/plain")

    _finalize_log(inbound_log, status="Received")
    _link_inbound_to_hr_session(
        inbound_log,
        identity,
        display_message,
        message_type=message_type,
        media_file=file_url,
    )
    frappe.logger("ai_workplace").info(
        f"AI Workplace [{trace_id}]: Acknowledged inbound {message_type} message {message_id}"
    )
    return Response("ok", status=200, mimetype="text/plain")


def _maybe_store_attendance_location_request_id(
    identity: Any,
    outbound: Any,
    send_result: dict[str, Any],
    wa_id: str = "",
    trace_id: str = "",
) -> None:
    """After sending a location-request message, store wamid on the attendance draft."""
    if not isinstance(outbound, OutboundMessage) or not outbound.is_location_request():
        return
    if not send_result.get("success") or not send_result.get("message_id"):
        return
    try:
        from ai_workplace.conversation.manager import get_or_create_conversation
        from ai_workplace.services.attendance_location import store_location_request_message_id

        conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id or "")
        store_location_request_message_id(conv, send_result["message_id"])
    except Exception:
        frappe.log_error(
            title="WhatsApp location request id store failed",
            message=frappe.get_traceback(),
        )


def _process_inbound_location(parsed: dict, trace_id: str) -> Response:
    """Handle inbound WhatsApp location messages for attendance check-in/out."""
    message_id = parsed.get("message_id", "")
    wa_id = parsed.get("wa_id", "")
    raw_phone = parsed.get("phone_number", wa_id)

    if _is_duplicate(message_id):
        frappe.logger("ai_workplace").info(
            f"AI Workplace [{trace_id}]: Duplicate location message_id={message_id} — skipped"
        )
        return Response("ok", status=200, mimetype="text/plain")

    identity = resolve_identity(raw_phone)
    wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id or "")
    identity.whatsapp_identity = wa_identity_name

    loc_text = parsed.get("location_name") or parsed.get("location_address") or "[Location]"
    inbound_log = _create_message_log(
        meta_message_id=message_id,
        direction="Inbound",
        sender=raw_phone,
        recipient="",
        wa_id=wa_id,
        message_type="location",
        message=loc_text,
        status="Processing",
        trace_id=trace_id,
    )
    _update_log_identity(inbound_log, identity)

    from ai_workplace.services.hr_chat import (
        append_inbound_message,
        get_active_session_for_identity,
        get_session_doc,
    )
    from ai_workplace.conversation.manager import (
        get_or_create_conversation,
        conversation_priority_expects_location,
    )

    conv_for_route = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id)
    priority_location_flow = conversation_priority_expects_location(conv_for_route)

    session_name = get_active_session_for_identity(wa_identity_name)
    if session_name and not priority_location_flow:
        session = get_session_doc(session_name)
        if session.ready_for_hr and session.status in ("Queued", "Assigned", "Active"):
            _finalize_log(inbound_log, status="Received")
            append_inbound_message(
                session,
                loc_text,
                meta_message_id=message_id,
                message_type="location",
            )
            return Response("ok", status=200, mimetype="text/plain")

    from ai_workplace.conversation.orchestrator import process_inbound_location

    try:
        outbound = process_inbound_location(
            identity=identity,
            location={
                "latitude": parsed.get("latitude"),
                "longitude": parsed.get("longitude"),
                "location_name": parsed.get("location_name") or "",
                "location_address": parsed.get("location_address") or "",
            },
            message_id=message_id,
            trace_id=trace_id,
            wa_id=wa_id,
            context_message_id=parsed.get("context_message_id") or "",
        )
    except Exception:
        frappe.log_error(title="WhatsApp location flow failed", message=frappe.get_traceback())
        outbound = OutboundMessage(
            body_text=_("Sorry, we could not process your location. Please try again.")
        )

    if outbound is not None:
        _finalize_log(inbound_log, status="Received")
        send_result = send_message(phone_number=identity.normalized_phone, outbound=outbound)
        _maybe_store_attendance_location_request_id(
            identity, outbound, send_result, wa_id=wa_id, trace_id=trace_id
        )
        _create_message_log(
            meta_message_id=send_result.get("message_id") or "",
            direction="Outbound",
            sender="",
            recipient=identity.normalized_phone,
            wa_id=wa_id,
            message_type=outbound.message_type if hasattr(outbound, "message_type") else "text",
            message=outbound.log_text() if hasattr(outbound, "log_text") else str(outbound),
            status="Sent" if send_result.get("success") else "Failed",
            trace_id=trace_id,
        )
    else:
        _finalize_log(inbound_log, status="Received")

    return Response("ok", status=200, mimetype="text/plain")


def _redact_inbound_message(wa_identity_name: str, message_text: str) -> str:
    """Redact PIN-shaped inbound text before WhatsApp Message Log insert."""
    from ai_workplace.security.credential_redaction import (
        redact_message_for_log,
        should_redact_inbound,
        is_pin_shaped_text,
    )

    conv_state = frappe.db.get_value(
        "WhatsApp Conversation",
        {
            "whatsapp_identity": wa_identity_name,
            "conversation_status": "Active",
        },
        "current_state",
    )
    if should_redact_inbound(conv_state or "") or is_pin_shaped_text(message_text):
        return redact_message_for_log(message_text, force=True)
    return message_text


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
