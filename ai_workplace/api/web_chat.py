"""
ai_workplace/api/web_chat.py
─────────────────────────────
Public-facing & Authenticated Web Chat APIs for XpertChat.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import frappe
from frappe import _

from ai_workplace.identity.resolver import (
    resolve_web_identity,
    get_or_create_whatsapp_identity,
    IdentityResult,
)
from ai_workplace.context.resolver import get_user_context
from ai_workplace.conversation.manager import get_or_create_conversation
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.conversation.menu import build_menu
from ai_workplace.services.welcome import build_welcome_message
from ai_workplace.services.hr_chat import get_active_session_for_identity, get_session_doc
from ai_workplace.whatsapp.outbound import OutboundMessage


@frappe.whitelist(allow_guest=True)
def init_session(
    guest_name: Optional[str] = None,
    guest_email: Optional[str] = None,
    guest_phone: Optional[str] = None,
) -> dict[str, Any]:
    """
    Initialize or restore an XpertChat session for logged-in ERP user or Guest.
    """
    user_email = frappe.session.user
    is_logged_in = user_email and user_email != "Guest"

    if is_logged_in:
        identity = resolve_web_identity(user_email=user_email)
        wa_id = f"WEB-{user_email}"
        wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id)
        identity.whatsapp_identity = wa_identity_name

        context = get_user_context(identity)
        conv = get_or_create_conversation(identity, wa_id=wa_id)
        if conv.preferred_language:
            context["preferred_language"] = conv.preferred_language

        welcome_msg = build_welcome_message(context)
        menu_msg, _ = build_menu(context)
        active_hr_session = get_active_session_for_identity(
            whatsapp_identity=wa_identity_name,
            employee=identity.employee or "",
            wa_id=identity.normalized_phone or wa_id,
        )

        return {
            "success": True,
            "is_guest": False,
            "user": user_email,
            "full_name": identity.full_name,
            "employee": identity.employee,
            "whatsapp_identity": wa_identity_name,
            "welcome": _outbound_to_dict(welcome_msg),
            "menu": _outbound_to_dict(menu_msg),
            "active_hr_session": active_hr_session,
            "history": get_chat_history(wa_identity_name=wa_identity_name),
        }

    # Guest user flow
    if guest_phone and guest_name:
        guest_info = {
            "name": guest_name,
            "email": guest_email or "",
            "phone": guest_phone,
        }
        identity = resolve_web_identity(guest_info=guest_info)
        wa_id = f"WEB-GUEST-{guest_phone}"
        wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id)
        identity.whatsapp_identity = wa_identity_name

        context = get_user_context(identity)
        conv = get_or_create_conversation(identity, wa_id=wa_id)

        welcome_msg = build_welcome_message(context)
        menu_msg, _ = build_menu(context)
        active_hr_session = get_active_session_for_identity(
            whatsapp_identity=wa_identity_name, wa_id=wa_id
        )

        return {
            "success": True,
            "is_guest": True,
            "needs_intake": False,
            "full_name": guest_name,
            "email": guest_email,
            "phone": guest_phone,
            "whatsapp_identity": wa_identity_name,
            "welcome": _outbound_to_dict(welcome_msg),
            "menu": _outbound_to_dict(menu_msg),
            "active_hr_session": active_hr_session,
            "history": get_chat_history(wa_identity_name=wa_identity_name),
        }

    return {
        "success": True,
        "is_guest": True,
        "needs_intake": True,
    }


@frappe.whitelist(allow_guest=True)
def send_message(
    message_text: str,
    guest_name: Optional[str] = None,
    guest_email: Optional[str] = None,
    guest_phone: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process an inbound text or button command from XpertChat.
    """
    clean_text = (message_text or "").strip()
    if not clean_text:
        return {"success": False, "error": _("Message text cannot be empty.")}

    user_email = frappe.session.user
    is_logged_in = user_email and user_email != "Guest"
    trace_id = str(uuid.uuid4())

    if is_logged_in:
        identity = resolve_web_identity(user_email=user_email)
        wa_id = f"WEB-{user_email}"
    else:
        if not guest_phone:
            return {"success": False, "error": _("Guest phone number required.")}
        guest_info = {
            "name": guest_name or "Web Guest",
            "email": guest_email or "",
            "phone": guest_phone,
        }
        identity = resolve_web_identity(guest_info=guest_info)
        wa_id = f"WEB-GUEST-{guest_phone}"

    wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=wa_id)
    identity.whatsapp_identity = wa_identity_name

    meta_msg_id = f"WEB-{uuid.uuid4().hex[:12]}"

    # Log Inbound Web Message
    inbound_log = _create_web_message_log(
        meta_message_id=meta_msg_id,
        direction="Inbound",
        sender=user_email if is_logged_in else (guest_email or guest_phone),
        recipient="XpertChat",
        wa_id=wa_id,
        message=clean_text,
        erp_user=identity.user or "",
        employee=identity.employee or "",
        identity_status=identity.status,
        status="Processing",
        trace_id=trace_id,
    )

    # Execute orchestrator logic
    try:
        outbound = process_message(
            message_text=clean_text,
            identity=identity,
            message_id=meta_msg_id,
            trace_id=trace_id,
            wa_id=wa_id,
        )
    except Exception as exc:
        frappe.log_error(title=f"XpertChat Orchestrator Failed [{trace_id}]", message=frappe.get_traceback())
        outbound = OutboundMessage(
            body_text=_("Sorry, something went wrong while processing your request. Please try again or type *menu*.")
        )

    # Finalize Inbound Log
    frappe.db.set_value("WhatsApp Message Log", inbound_log.name, "status", "Received", update_modified=False)

    outbound_dict = _outbound_to_dict(outbound)
    response_text = outbound.log_text() if hasattr(outbound, "log_text") else str(outbound)

    # Log Outbound Web Message
    _create_web_message_log(
        meta_message_id=f"OUT-{meta_msg_id}",
        direction="Outbound",
        sender="System",
        recipient=user_email if is_logged_in else (guest_email or guest_phone),
        wa_id=wa_id,
        message=response_text,
        erp_user=identity.user or "",
        employee=identity.employee or "",
        identity_status=identity.status,
        status="Sent",
        trace_id=trace_id,
        sender_type="System",
    )

    active_hr_session = get_active_session_for_identity(
        whatsapp_identity=wa_identity_name,
        employee=identity.employee or "",
        wa_id=identity.normalized_phone or wa_id,
    )

    # If active HR session exists and channel is Web Chat, set channel field
    if active_hr_session:
        frappe.db.set_value("HR Live Chat Session", active_hr_session, "channel", "Web Chat", update_modified=False)
        frappe.db.commit()

    return {
        "success": True,
        "response": outbound_dict,
        "active_hr_session": active_hr_session,
    }


@frappe.whitelist(allow_guest=True)
def get_chat_history(wa_identity_name: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """
    Fetch message log history for the specified web chat session.
    """
    if not wa_identity_name:
        user_email = frappe.session.user
        if user_email and user_email != "Guest":
            identity = resolve_web_identity(user_email=user_email)
            wa_identity_name = get_or_create_whatsapp_identity(identity, wa_id=f"WEB-{user_email}")
        else:
            return []

    logs = frappe.get_all(
        "WhatsApp Message Log",
        filters={"channel": "Web Chat", "whatsapp_id": ["like", f"%{wa_identity_name}%"]},
        fields=["name", "direction", "message", "timestamp", "sender_type", "media_file", "message_type"],
        order_by="timestamp asc",
        limit_page_length=limit,
    )

    history = []
    for l in logs:
        history.append({
            "name": l.name,
            "direction": l.direction,
            "message": l.message,
            "timestamp": str(l.timestamp) if l.timestamp else "",
            "sender_type": l.sender_type or ("Employee" if l.direction == "Inbound" else "System"),
            "media_file": l.media_file or "",
            "message_type": l.message_type or "text",
        })
    return history


def _create_web_message_log(
    *,
    meta_message_id: str,
    direction: str,
    sender: str,
    recipient: str,
    wa_id: str,
    message: str,
    erp_user: str = "",
    employee: str = "",
    identity_status: str = "",
    status: str = "Sent",
    trace_id: str = "",
    sender_type: str = "",
) -> "frappe.Document":
    """Helper to insert a Web Chat entry into WhatsApp Message Log."""
    doc = frappe.new_doc("WhatsApp Message Log")
    doc.channel = "Web Chat"
    doc.meta_message_id = meta_message_id
    doc.direction = direction
    doc.sender = sender
    doc.recipient = recipient
    doc.whatsapp_id = wa_id
    doc.message_type = "text"
    doc.message = message
    doc.erp_user = erp_user or ""
    doc.employee = employee or ""
    doc.identity_status = identity_status or ""
    doc.status = status
    doc.trace_id = trace_id
    doc.sender_type = sender_type or ("Employee" if direction == "Inbound" else "System")
    doc.timestamp = frappe.utils.now_datetime()
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _outbound_to_dict(outbound: Any) -> dict[str, Any]:
    """Convert OutboundMessage object to frontend-friendly dict."""
    if not outbound:
        return {"body_text": "", "buttons": [], "follow_up": []}

    body = getattr(outbound, "body_text", "") or str(outbound)
    buttons = []
    interactive = getattr(outbound, "interactive", None)
    if interactive and isinstance(interactive, dict):
        action = interactive.get("action", {})
        btn_list = action.get("buttons", [])
        for b in btn_list:
            reply = b.get("reply", {})
            buttons.append({
                "id": reply.get("id"),
                "title": reply.get("title"),
            })
        sections = action.get("sections", [])
        for s in sections:
            for r in s.get("rows", []):
                buttons.append({
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "description": r.get("description", ""),
                })

    follow_up_dicts = []
    follow_ups = getattr(outbound, "follow_up", []) or []
    for f in follow_ups:
        follow_up_dicts.append(_outbound_to_dict(f))

    return {
        "body_text": body,
        "buttons": buttons,
        "follow_up": follow_up_dicts,
        "message_type": getattr(outbound, "message_type", "text"),
        "media_url": getattr(outbound, "media_url", None),
        "filename": getattr(outbound, "filename", None),
    }
