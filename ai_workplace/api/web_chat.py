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


def _resolve_identity_from_wa_identity_name(wa_identity_name: str) -> tuple[Optional["IdentityResult"], str]:
    """
    Fallback resolver: given a WhatsApp Identity docname, reconstruct the
    IdentityResult and wa_id without relying on frappe.session.user.

    Returns (identity, wa_id) or (None, "") if lookup fails.
    """
    try:
        wi = frappe.db.get_value(
            "WhatsApp Identity",
            wa_identity_name,
            ["name", "erp_user", "employee", "guest_name", "guest_email",
             "normalized_phone", "phone_number", "whatsapp_id", "status"],
            as_dict=True,
        )
        if not wi:
            return None, ""

        erp_user = wi.get("erp_user") or ""
        if erp_user and erp_user != "Guest":
            # Reconstruct as a matched (logged-in) identity
            identity = resolve_web_identity(user_email=erp_user)
            wa_id = f"WEB-{erp_user}"
            return identity, wa_id

        # Guest identity
        guest_phone = wi.get("normalized_phone") or wi.get("phone_number") or ""
        guest_email = wi.get("guest_email") or ""
        guest_name = wi.get("guest_name") or "Web Guest"
        if not guest_phone:
            return None, ""

        guest_info = {"name": guest_name, "email": guest_email, "phone": guest_phone}
        identity = resolve_web_identity(guest_info=guest_info)
        wa_id = wi.get("whatsapp_id") or f"WEB-GUEST-{guest_phone}"
        return identity, wa_id
    except Exception:
        frappe.log_error(title="XpertChat: wa_identity fallback failed", message=frappe.get_traceback())
        return None, ""


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

        from ai_workplace.services.hr_chat import get_employee_image
        user_img = get_employee_image(employee=identity.employee, erp_user=user_email)

        return {
            "success": True,
            "is_guest": False,
            "user": user_email,
            "full_name": identity.full_name,
            "employee": identity.employee,
            "user_image": user_img,
            "whatsapp_identity": wa_identity_name,
            "welcome": _outbound_to_dict(welcome_msg),
            "menu": _outbound_to_dict(menu_msg),
            "active_hr_session": active_hr_session,
            "previous_sessions": get_user_sessions(),
            "history": get_chat_history(wa_identity_name=wa_identity_name, start=0, limit=10),
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

        from ai_workplace.services.hr_chat import get_employee_image
        user_img = get_employee_image(employee=identity.employee, erp_user="")

        return {
            "success": True,
            "is_guest": True,
            "needs_intake": False,
            "full_name": identity.full_name or guest_name,
            "email": identity.guest_email or guest_email,
            "phone": guest_phone,
            "user_image": user_img,
            "whatsapp_identity": wa_identity_name,
            "welcome": _outbound_to_dict(welcome_msg),
            "menu": _outbound_to_dict(menu_msg),
            "active_hr_session": active_hr_session,
            "previous_sessions": get_user_sessions(
                guest_phone=guest_phone,
                guest_email=guest_email or identity.guest_email,
                wa_identity_name=wa_identity_name,
            ),
            "history": get_chat_history(
                wa_identity_name=wa_identity_name,
                guest_phone=guest_phone,
                guest_email=guest_email or identity.guest_email,
                start=0,
                limit=10,
            ),
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
    wa_identity_name: Optional[str] = None,
    media_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Process an inbound text or button command from XpertChat.

    Identity resolution priority:
      1. frappe.session.user  — normal authenticated flow (session cookie present)
      2. wa_identity_name     — fallback when session cookie is missing but the
                                frontend supplies the stored WhatsApp Identity name
      3. guest_phone          — explicit guest flow
      4. Error                — cannot resolve identity
    """
    clean_text = (message_text or "").strip()
    if not clean_text and not media_url:
        return {"success": False, "error": _("Message text or media cannot be empty.")}

    user_email = frappe.session.user
    is_logged_in = user_email and user_email != "Guest"
    trace_id = str(uuid.uuid4())

    if is_logged_in:
        # ── Tier 1: Normal authenticated session ───────────────────────────────
        identity = resolve_web_identity(user_email=user_email)
        wa_id = f"WEB-{user_email}"

    elif wa_identity_name:
        # ── Tier 2: Session cookie missing — reconstruct from stored identity ──
        identity, wa_id = _resolve_identity_from_wa_identity_name(wa_identity_name)
        if not identity:
            return {"success": False, "error": _("Could not resolve identity. Please refresh and try again.")}
        # Promote is_logged_in flag if we resolved a real ERP user
        is_logged_in = bool(identity.user and identity.user != "Guest")

    elif guest_phone:
        # ── Tier 3: Explicit guest data ────────────────────────────────────────
        guest_info = {
            "name": guest_name or "Web Guest",
            "email": guest_email or "",
            "phone": guest_phone,
        }
        identity = resolve_web_identity(guest_info=guest_info)
        wa_id = f"WEB-GUEST-{guest_phone}"

    else:
        # ── Tier 4: Unresolvable ───────────────────────────────────────────────
        return {"success": False, "error": _("Guest phone number required.")}

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
        media_url=media_url,
    )

    # Execute orchestrator logic
    try:
        outbound = process_message(
            message_text=clean_text,
            identity=identity,
            message_id=meta_msg_id,
            trace_id=trace_id,
            wa_id=wa_id,
            media_url=media_url,
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
    outbound_log = _create_web_message_log(
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
    if outbound_log:
        outbound_dict["log_name"] = outbound_log.name

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
def get_user_sessions(
    guest_phone: Optional[str] = None,
    guest_email: Optional[str] = None,
    wa_identity_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Get all previous chat sessions for the logged-in user or guest.
    """
    user_email = frappe.session.user
    is_logged_in = user_email and user_email != "Guest"

    or_filters = []
    if is_logged_in:
        identity = resolve_web_identity(user_email=user_email)
        if identity.employee:
            or_filters.append({"employee": identity.employee})
        if identity.user:
            or_filters.append({"erp_user": identity.user})
        if identity.whatsapp_identity:
            or_filters.append({"whatsapp_identity": identity.whatsapp_identity})
        or_filters.append({"wa_id": f"WEB-{user_email}"})
    else:
        if wa_identity_name:
            or_filters.append({"whatsapp_identity": wa_identity_name})
            or_filters.append({"wa_id": wa_identity_name})
        if guest_email:
            or_filters.append({"guest_email": guest_email})
        if guest_phone:
            wa_id = f"WEB-GUEST-{guest_phone}"
            or_filters.append({"wa_id": wa_id})
            try:
                from ai_workplace.identity.phone import normalize_phone_number
                norm = normalize_phone_number(guest_phone)
                or_filters.append({"wa_id": norm})
            except Exception:
                pass
            or_filters.append({"wa_id": guest_phone})

    if not or_filters:
        return []

    sessions = frappe.get_all(
        "HR Live Chat Session",
        or_filters=or_filters,
        fields=[
            "name",
            "status",
            "display_name",
            "initial_query",
            "opened_at",
            "modified",
            "channel",
            "assigned_to",
            "whatsapp_identity",
        ],
        order_by="modified desc",
        limit_page_length=30,
    )

    result = []
    for s in sessions:
        last_log = frappe.get_all(
            "WhatsApp Message Log",
            filters={"hr_live_chat_session": s.name},
            fields=["message", "timestamp", "direction", "sender_type"],
            order_by="timestamp desc",
            limit_page_length=1,
        )
        last_msg = ""
        if last_log:
            last_msg = last_log[0].message
        else:
            last_msg = s.initial_query or "HR Live Support Chat"

        result.append({
            "name": s.name,
            "display_title": s.display_name or s.initial_query or f"Chat Session ({s.name})",
            "status": s.status or "Active",
            "last_message": last_msg,
            "whatsapp_identity": s.whatsapp_identity or "",
            "opened_at": str(s.opened_at) if s.opened_at else str(s.modified),
            "modified": str(s.modified),
        })

    return result


@frappe.whitelist(allow_guest=True)
def get_chat_history(
    wa_identity_name: str = "",
    session_name: str = "",
    guest_phone: str = "",
    guest_email: str = "",
    start: int = 0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch message log history for the specified web chat session or identity with pagination support.
    Ordered from newest to oldest in DB query, then returned in chronological order.
    """
    start = max(0, int(start or 0))
    limit = max(1, int(limit or 10))

    if session_name:
        logs = frappe.get_all(
            "WhatsApp Message Log",
            filters={"hr_live_chat_session": session_name},
            fields=["name", "direction", "message", "timestamp", "creation", "sender_type", "media_file", "message_type", "hr_live_chat_session"],
            order_by="creation desc, name desc",
            start=start,
            page_length=limit,
        )
    else:
        user_email = frappe.session.user
        is_logged_in = user_email and user_email != "Guest"

        session_names = []
        if is_logged_in:
            identity = resolve_web_identity(user_email=user_email)
            s_or_filters = [{"erp_user": user_email}]
            if identity.employee:
                s_or_filters.append({"employee": identity.employee})
            if identity.whatsapp_identity:
                s_or_filters.append({"whatsapp_identity": identity.whatsapp_identity})
            session_names = frappe.get_all("HR Live Chat Session", or_filters=s_or_filters, pluck="name")
        elif wa_identity_name or guest_email or guest_phone:
            s_or_filters = []
            if wa_identity_name:
                s_or_filters.append({"whatsapp_identity": wa_identity_name})
                s_or_filters.append({"wa_id": wa_identity_name})
            if guest_email:
                s_or_filters.append({"guest_email": guest_email})
            if guest_phone:
                s_or_filters.append({"wa_id": f"WEB-GUEST-{guest_phone}"})
                s_or_filters.append({"wa_id": guest_phone})
            session_names = frappe.get_all("HR Live Chat Session", or_filters=s_or_filters, pluck="name")

        or_filters = []
        if session_names:
            or_filters.append({"hr_live_chat_session": ["in", session_names]})
        if wa_identity_name:
            or_filters.append({"whatsapp_id": ["like", f"%{wa_identity_name}%"]})
            or_filters.append({"whatsapp_id": wa_identity_name})
        if guest_email:
            or_filters.append({"sender": guest_email})
            or_filters.append({"recipient": guest_email})
        if guest_phone:
            or_filters.append({"whatsapp_id": f"WEB-GUEST-{guest_phone}"})
            or_filters.append({"whatsapp_id": guest_phone})
            try:
                from ai_workplace.identity.phone import normalize_phone_number
                norm = normalize_phone_number(guest_phone)
                or_filters.append({"whatsapp_id": norm})
            except Exception:
                pass

        if is_logged_in:
            identity = resolve_web_identity(user_email=user_email)
            or_filters.append({"erp_user": user_email})
            if identity.employee:
                or_filters.append({"employee": identity.employee})
            if identity.whatsapp_identity:
                or_filters.append({"whatsapp_id": identity.whatsapp_identity})

        if not or_filters:
            return []

        logs = frappe.get_all(
            "WhatsApp Message Log",
            or_filters=or_filters,
            fields=["name", "direction", "message", "timestamp", "creation", "sender_type", "media_file", "message_type", "hr_live_chat_session"],
            order_by="creation desc, name desc",
            start=start,
            page_length=limit,
        )

    # Reverse to ascending chronological order for display
    logs.reverse()

    history = []
    seen_ids = set()
    for l in logs:
        if l.name in seen_ids:
            continue
        msg_text = (l.message or "").strip()
        media_file = (l.media_file or "").strip()
        if not msg_text and not media_file:
            continue
        seen_ids.add(l.name)
        ts_val = l.timestamp or l.creation
        history.append({
            "name": l.name,
            "direction": l.direction,
            "message": l.message,
            "timestamp": str(ts_val) if ts_val else "",
            "creation": str(l.creation) if l.creation else "",
            "sender_type": l.sender_type or ("Employee" if l.direction == "Inbound" else "System"),
            "media_file": l.media_file or "",
            "message_type": l.message_type or "text",
            "session": l.hr_live_chat_session or "",
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
    media_url: str = "",
) -> "frappe.Document":
    """Helper to insert a Web Chat entry into WhatsApp Message Log."""
    if not (message or "").strip() and not media_url:
        return None

    doc = frappe.new_doc("WhatsApp Message Log")
    doc.channel = "Web Chat"
    doc.meta_message_id = meta_message_id
    doc.direction = direction
    doc.sender = sender
    doc.recipient = recipient
    doc.whatsapp_id = wa_id
    doc.message_type = "image" if media_url else "text"
    doc.message = message
    if media_url:
        doc.media_file = media_url
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

    media_url = getattr(outbound, "media_url", None)
    doc_bytes = getattr(outbound, "document_bytes", None) or getattr(outbound, "image_bytes", None)
    doc_filename = getattr(outbound, "document_filename", None) or getattr(outbound, "filename", None)

    if doc_bytes and not media_url:
        try:
            fname = doc_filename or f"doc_{frappe.generate_hash(length=8)}.pdf"
            _file = frappe.get_doc({
                "doctype": "File",
                "file_name": fname,
                "content": doc_bytes,
                "is_private": 0,
            })
            _file.insert(ignore_permissions=True)
            frappe.db.commit()
            media_url = _file.file_url
        except Exception as e:
            frappe.logger("ai_workplace").error(f"Failed to save web chat document bytes to File: {e}")

    return {
        "body_text": body,
        "buttons": buttons,
        "follow_up": follow_up_dicts,
        "message_type": getattr(outbound, "message_type", "text"),
        "media_url": media_url,
        "filename": doc_filename,
    }
