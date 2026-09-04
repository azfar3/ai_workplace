"""
ai_workplace/services/hr_chat.py
────────────────────────────────
HR Live Chat session lifecycle, 24-hour window enforcement, and messaging.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Optional

import frappe
from frappe import _

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.office_hours import (
    build_off_hours_message,
    build_session_open_message,
    get_office_hours_info,
    is_hr_available,
    is_hr_live_chat_enabled,
)
from ai_workplace.whatsapp.media import read_frappe_file_bytes
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.sender import (
    send_document_message,
    send_image_message,
    send_text_message,
    upload_media_bytes,
)

SESSION_WINDOW_HOURS = 24
SESSION_PERSON_TYPES = frozenset({"Employee", "Consultant", "Guest", "Former Employee"})
OPEN_STATUSES = ("Queued", "Assigned", "Active")
INBOX_STATUSES = OPEN_STATUSES + ("Closed", "Expired")
HR_AGENT_ROLES = ("HR Workplace Agent", "HR Manager", "System Manager")
REALTIME_EVENT = "hr_chat_update"
CONTACT_HR_SERVICE_KEYS = ("contact_hr", "guest_contact")
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
DOCUMENT_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".zip"})
MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024


def normalize_session_person_type(person_type: str = "") -> str:
    """Map WhatsApp context person_type to HR Live Chat Session select options."""
    clean = (person_type or "").strip()
    if clean in SESSION_PERSON_TYPES:
        return clean
    if clean in ("Former Employee", "Inactive"):
        return "Former Employee"
    return "Employee"


def get_configured_hr_chat_agents(active_only: bool = True) -> list[str]:
    """Return users configured in AI Workplace Settings → HR Chat Agents."""
    try:
        settings = frappe.get_single("AI Workplace Settings")
    except Exception:
        return []

    agents: list[str] = []
    for row in settings.get("hr_chat_agents") or []:
        if not row.user:
            continue
        if active_only and not row.is_active:
            continue
        if not frappe.db.get_value("User", row.user, "enabled"):
            continue
        agents.append(row.user)
    return agents


def user_is_hr_agent(user: Optional[str] = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    if user_is_hr_manager(user):
        return True

    configured = get_configured_hr_chat_agents()
    if configured:
        return user in configured

    roles = frappe.get_roles(user)
    return any(role in roles for role in HR_AGENT_ROLES)


def _now() -> Any:
    return frappe.utils.now_datetime()


def _compute_window_expires(last_user_message_at: Any) -> Any:
    return last_user_message_at + timedelta(hours=SESSION_WINDOW_HOURS)


def _session_payload(session: Any) -> dict[str, Any]:
    can_reply, reason = evaluate_reply_permission(session)
    office = get_office_hours_info()
    return {
        "name": session.name,
        "status": session.status,
        "assigned_to": session.assigned_to,
        "employee": session.employee,
        "erp_user": session.erp_user,
        "wa_id": session.wa_id,
        "whatsapp_identity": session.whatsapp_identity,
        "last_user_message_at": session.last_user_message_at,
        "last_hr_reply_at": getattr(session, "last_hr_reply_at", None),
        "session_window_expires_at": session.session_window_expires_at,
        "can_reply": can_reply,
        "can_reply_reason": reason,
        "is_office_hours": office["is_office_hours"],
        "hr_support_status": office.get("hr_support_status"),
        "is_holiday": office.get("is_holiday"),
        "closed_reason": office.get("closed_reason"),
        "office_timezone": office["timezone"],
        "office_local_time": office["local_time"],
        "office_local_date": office["local_date"],
    }


def publish_session_update(session: Any, extra: Optional[dict[str, Any]] = None) -> None:
    payload = _session_payload(session)
    if extra:
        payload.update(extra)
    try:
        # Emit immediately — callers commit before publishing. Using after_commit=True
        # after an explicit commit drops events until a later unrelated transaction.
        frappe.publish_realtime(REALTIME_EVENT, payload, room="all", after_commit=False)
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"AI Workplace: Failed to publish hr_chat_update: {exc}"
        )


def user_is_hr_manager(user: Optional[str] = None) -> bool:
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = frappe.get_roles(user)
    return "HR Manager" in roles or "System Manager" in roles


def get_active_session_for_identity(whatsapp_identity: str) -> Optional[str]:
    if not whatsapp_identity:
        return None
    return frappe.db.get_value(
        "HR Live Chat Session",
        {
            "whatsapp_identity": whatsapp_identity,
            "status": ["in", list(OPEN_STATUSES)],
        },
        "name",
        order_by="modified desc",
    )


def get_session_doc(session_name: str) -> Any:
    if not frappe.db.exists("HR Live Chat Session", session_name):
        frappe.throw(_("HR Live Chat Session {0} not found.").format(session_name))
    return frappe.get_doc("HR Live Chat Session", session_name)


def refresh_session_window(session: Any, now: Optional[Any] = None) -> None:
    now = now or _now()
    session.last_user_message_at = now
    session.session_window_expires_at = _compute_window_expires(now)
    if session.status == "Expired":
        session.status = "Active" if session.assigned_to else "Queued"


def get_hr_agent_role_access(user: Optional[str] = None) -> str:
    """Return access role for given HR user: Main HR User or Assigned HR User."""
    user = user or frappe.session.user
    if user == "Administrator":
        return "Main HR User (View & Reply All)"

    try:
        settings = frappe.get_single("AI Workplace Settings")
        for row in settings.get("hr_chat_agents") or []:
            if row.user == user and row.is_active:
                return getattr(row, "agent_role", None) or "Main HR User (View & Reply All)"
    except Exception:
        pass

    return "Main HR User (View & Reply All)"


def evaluate_reply_permission(
    session: Any,
    user: Optional[str] = None,
) -> tuple[bool, str]:
    user = user or frappe.session.user
    now = _now()

    if session.status == "Queued":
        access_role = get_hr_agent_role_access(user)
        if access_role == "Assigned HR User (View & Reply Assigned Only)":
            return False, _("Access Restricted: Assigned HR users can only respond to chats assigned to them.")
        return False, _("Please click *Take Chat* to start responding.")

    if session.status not in ("Assigned", "Active"):
        return False, _("Session is not active.")

    if not session.assigned_to:
        return False, _("No HR agent assigned to this chat.")

    if session.assigned_to != user:
        access_role = get_hr_agent_role_access(user)
        if access_role == "Assigned HR User (View & Reply Assigned Only)":
            return False, _("Access Restricted: You can only view and reply to chats assigned to you.")
        if not user_is_hr_manager(user):
            return False, _("This chat is assigned to another HR agent.")

    if not session.last_user_message_at or not session.session_window_expires_at:
        return False, _("Waiting for an employee message on WhatsApp.")

    if now > session.session_window_expires_at:
        return False, _(
            "WhatsApp 24-hour window expired. The employee must send a new message on WhatsApp before you can reply."
        )

    return True, ""


def resolve_display_name(
    *,
    context: Optional[dict[str, Any]] = None,
    employee: str = "",
    erp_user: str = "",
    explicit_name: str = "",
) -> str:
    if explicit_name:
        return explicit_name
    if context:
        if context.get("full_name"):
            return context["full_name"]
        employee = employee or context.get("employee") or ""
    if employee and frappe.db.exists("Employee", employee):
        name = frappe.db.get_value("Employee", employee, "employee_name")
        if name:
            return name
    if erp_user and frappe.db.exists("User", erp_user):
        name = frappe.db.get_value("User", erp_user, "full_name")
        if name:
            return name
    return ""


def get_existing_session_for_identity(
    whatsapp_identity: str = "",
    employee: str = "",
    wa_id: str = "",
) -> Optional[str]:
    """Return active session first, or falling back to the most recent closed/expired session."""
    filters_or = []
    if whatsapp_identity:
        filters_or.append({"whatsapp_identity": whatsapp_identity})
    if employee:
        filters_or.append({"employee": employee})
    if wa_id:
        filters_or.append({"wa_id": wa_id})

    if not filters_or:
        return None

    active = frappe.get_all(
        "HR Live Chat Session",
        or_filters=filters_or,
        filters={"status": ["in", list(OPEN_STATUSES)]},
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if active:
        return active[0]["name"]

    any_session = frappe.get_all(
        "HR Live Chat Session",
        or_filters=filters_or,
        fields=["name"],
        order_by="modified desc",
        limit=1,
    )
    if any_session:
        return any_session[0]["name"]

    return None


def open_session(
    *,
    whatsapp_identity: str,
    whatsapp_conversation: str,
    wa_id: str = "",
    employee: str = "",
    erp_user: str = "",
    display_name: str = "",
    guest_email: str = "",
    initial_query: str = "",
    person_type: str = "",
    contact_hr_selected: bool = False,
    ready_for_hr: bool = False,
    context: Optional[dict[str, Any]] = None,
) -> Any:
    """Create or resume an HR live chat session, merging/reusing existing session for the same employee."""
    existing_name = get_existing_session_for_identity(
        whatsapp_identity, employee=employee, wa_id=wa_id
    )
    now = _now()
    resolved_name = resolve_display_name(
        context=context,
        employee=employee,
        erp_user=erp_user,
        explicit_name=display_name,
    )

    if existing_name:
        session = frappe.get_doc("HR Live Chat Session", existing_name)
        was_closed_or_expired = session.status in ("Closed", "Expired")
        if whatsapp_identity and not session.whatsapp_identity:
            session.whatsapp_identity = whatsapp_identity
        session.whatsapp_conversation = whatsapp_conversation
        if wa_id:
            session.wa_id = wa_id
        if employee:
            session.employee = employee
        if erp_user:
            session.erp_user = erp_user
        if resolved_name:
            session.display_name = resolved_name
        if guest_email:
            session.guest_email = guest_email
        if initial_query and not session.initial_query:
            session.initial_query = initial_query
        if person_type:
            session.person_type = normalize_session_person_type(person_type)
        if contact_hr_selected:
            session.contact_hr_selected = 1
        if ready_for_hr:
            session.ready_for_hr = 1
            if session.status in ("Pending Intake", "Closed", "Expired"):
                session.status = "Queued"
        session.off_hours_notice_sent = 0
        session.last_user_message_at = now
        session.session_window_expires_at = _compute_window_expires(now)
        if was_closed_or_expired:
            session.closed_at = None
            session.closed_by = None
            session.opened_at = now

        session.flags.ignore_links = True
        session.save(ignore_permissions=True)
        frappe.db.commit()
        if ready_for_hr:
            publish_session_update(session, {"event": "session_opened"})
        return session

    session = frappe.new_doc("HR Live Chat Session")
    session.whatsapp_identity = whatsapp_identity
    session.whatsapp_conversation = whatsapp_conversation
    session.wa_id = wa_id
    session.employee = employee or None
    session.erp_user = erp_user or None
    session.display_name = resolved_name or None
    session.guest_email = guest_email or None
    session.initial_query = initial_query or None
    session.person_type = normalize_session_person_type(person_type) if person_type else None
    session.contact_hr_selected = 1 if contact_hr_selected else 0
    session.ready_for_hr = 1 if ready_for_hr else 0
    session.status = "Queued" if ready_for_hr else "Pending Intake"
    session.opened_at = now
    session.last_user_message_at = now
    session.session_window_expires_at = _compute_window_expires(now)
    session.flags.ignore_links = True
    session.insert(ignore_permissions=True)
    frappe.db.commit()
    if ready_for_hr:
        publish_session_update(session, {"event": "session_opened"})
    return session


def link_message_to_session(
    session_name: str,
    *,
    meta_message_id: str = "",
    sender_type: str = "Employee",
) -> None:
    if not meta_message_id:
        return
    log_name = frappe.db.get_value(
        "WhatsApp Message Log",
        {"meta_message_id": meta_message_id},
        "name",
    )
    if not log_name:
        return
    frappe.db.set_value(
        "WhatsApp Message Log",
        log_name,
        {
            "hr_live_chat_session": session_name,
            "sender_type": sender_type,
        },
    )


def append_inbound_message(
    session: Any,
    message_text: str,
    *,
    meta_message_id: str = "",
    message_type: str = "text",
    media_file: str = "",
) -> None:
    from ai_workplace.security.credential_redaction import redact_message_for_log, is_pin_shaped_text

    safe_text = redact_message_for_log(message_text, force=is_pin_shaped_text(message_text))
    now = _now()
    refresh_session_window(session, now=now)
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)
    frappe.db.commit()
    link_message_to_session(session.name, meta_message_id=meta_message_id, sender_type="Employee")
    publish_session_update(
        session,
        {
            "event": "inbound_message",
            "message": safe_text,
            "meta_message_id": meta_message_id,
            "direction": "Inbound",
            "sender_type": "Employee",
            "timestamp": frappe.utils.now(),
            "message_type": message_type or "text",
            "media_file": media_file or "",
        },
    )


def handle_contact_hr_request(
    conv: Any,
    context: dict[str, Any],
    trace_id: str = "",
    identity: Any = None,
) -> OutboundMessage:
    """Show Contact HR options (phone, email, wait to connect)."""
    from ai_workplace.services.hr_contact_prompt import handle_contact_hr_intro

    if not is_hr_live_chat_enabled():
        return OutboundMessage(
            body_text=_("HR live chat is currently unavailable. Please try again later.")
        )

    return handle_contact_hr_intro(conv, context)


def handle_contact_hr_connect(
    conv: Any,
    context: dict[str, Any],
    trace_id: str = "",
    identity: Any = None,
) -> OutboundMessage:
    """Start HR live chat after user chooses to wait for HR."""
    if not is_hr_live_chat_enabled():
        return OutboundMessage(
            body_text=_("HR live chat is currently unavailable. Please try again later.")
        )

    from ai_workplace.services.hr_guest_intake import is_guest_context, start_guest_intake

    if is_guest_context(context):
        return start_guest_intake(conv, context)

    person_type = normalize_session_person_type(context.get("person_type") or "Employee")
    display_name = resolve_display_name(
        context=context,
        employee=conv.employee or context.get("employee") or "",
        erp_user=conv.erp_user or context.get("user") or "",
    )

    session = open_session(
        whatsapp_identity=conv.whatsapp_identity,
        whatsapp_conversation=conv.name,
        wa_id=conv.wa_id or "",
        employee=conv.employee or context.get("employee") or "",
        erp_user=conv.erp_user or context.get("user") or "",
        display_name=display_name,
        person_type=person_type,
        contact_hr_selected=True,
        ready_for_hr=True,
        context=context,
    )

    update_conversation(
        conv,
        state=ConversationState.LIVE_HR_CHAT,
        current_intent="contact_hr",
        active_service=None,
        active_hr_chat_session=session.name,
    )

    available = is_hr_available()
    if not available:
        if not session.off_hours_notice_sent:
            session.off_hours_notice_sent = 1
            session.flags.ignore_links = True
            session.save(ignore_permissions=True)
            frappe.db.commit()
        publish_session_update(session, {"event": "off_hours_queue"})
    else:
        publish_session_update(session, {"event": "queued"})

    return OutboundMessage(body_text=build_session_open_message(context, is_open=available))


def handle_live_hr_inbound(
    conv: Any,
    message_text: str,
    *,
    meta_message_id: str = "",
    trace_id: str = "",
) -> OutboundMessage:
    """Route an inbound WhatsApp message during LIVE_HR_CHAT."""
    session_name = conv.active_hr_chat_session or get_active_session_for_identity(
        conv.whatsapp_identity
    )
    if not session_name:
        return OutboundMessage(
            body_text=_("Please select *Contact HR* from the menu to start a chat with HR."),
        )

    session = get_session_doc(session_name)
    if not session.ready_for_hr:
        return OutboundMessage(body_text="", skip_send=True)

    append_inbound_message(session, message_text, meta_message_id=meta_message_id)
    return OutboundMessage(body_text="", skip_send=True)


def close_session(
    session_name: str,
    user: Optional[str] = None,
    *,
    reset_conversation: bool = True,
) -> Any:
    user = user or frappe.session.user
    session = get_session_doc(session_name)
    session.status = "Closed"
    session.closed_at = _now()
    session.closed_by = user
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)

    if reset_conversation and session.whatsapp_conversation:
        conv = frappe.get_doc("WhatsApp Conversation", session.whatsapp_conversation)
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service=None,
            clear_active_hr_chat_session=True,
            clear_active_fields=False,
        )

    frappe.db.commit()
    publish_session_update(session, {"event": "session_closed"})
    return session


def take_session(session_name: str, user: Optional[str] = None) -> Any:
    user = user or frappe.session.user
    if not user_is_hr_agent(user):
        frappe.throw(_("You do not have permission to take HR chats."), frappe.PermissionError)

    access_role = get_hr_agent_role_access(user)
    if access_role == "Assigned HR User (View & Reply Assigned Only)":
        frappe.throw(_("Access Restricted: Assigned HR users cannot take queued chats."), frappe.PermissionError)

    session = get_session_doc(session_name)
    if session.status != "Queued":
        frappe.throw(_("Only queued chats can be taken."))

    now = _now()
    if session.session_window_expires_at and now > session.session_window_expires_at:
        session.status = "Expired"
        session.flags.ignore_links = True
        session.save(ignore_permissions=True)
        frappe.db.commit()
        frappe.throw(_("This chat window has expired. Wait for the employee to message again on WhatsApp."))

    session.assigned_to = user
    session.status = "Active"
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)
    frappe.db.commit()
    publish_session_update(session, {"event": "session_taken"})
    return session


def assign_session(session_name: str, assign_to: str, user: Optional[str] = None) -> Any:
    user = user or frappe.session.user
    if not user_is_hr_agent(user):
        frappe.throw(_("You do not have permission to assign HR chats."), frappe.PermissionError)

    access_role = get_hr_agent_role_access(user)
    if access_role == "Assigned HR User (View & Reply Assigned Only)":
        frappe.throw(_("Access Restricted: Assigned HR users cannot assign or reassign chats."), frappe.PermissionError)

    session = get_session_doc(session_name)
    if session.assigned_to and session.assigned_to != user and not user_is_hr_manager(user):
        frappe.throw(_("Only HR Managers can reassign chats owned by another agent."), frappe.PermissionError)

    if not frappe.db.exists("User", assign_to):
        frappe.throw(_("User {0} does not exist.").format(assign_to))
    if not user_is_hr_agent(assign_to):
        frappe.throw(
            _("Assignee must be configured as an HR chat agent in AI Workplace Settings.")
        )

    session.assigned_to = assign_to
    if session.status in ("Queued", "Assigned", "Expired"):
        session.status = "Active"
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)
    frappe.db.commit()
    publish_session_update(session, {"event": "session_assigned", "assigned_by": user})
    return session


def consolidate_duplicate_sessions() -> int:
    """
    Consolidate multiple HR Live Chat Session records belonging to the same employee identity.
    Repoints all WhatsApp Message Logs from duplicate sessions to the single primary session,
    then deletes the duplicate session records from the database.
    Returns count of deleted duplicate sessions.
    """
    all_sessions = frappe.get_all(
        "HR Live Chat Session",
        fields=["name", "status", "employee", "whatsapp_identity", "wa_id", "modified", "creation"],
        order_by="creation desc",
    )
    if not all_sessions:
        return 0

    groups: dict[str, list[dict[str, Any]]] = {}
    for s in all_sessions:
        key = get_session_identity_key(s)
        groups.setdefault(key, []).append(s)

    deleted_count = 0
    for key, items in groups.items():
        if len(items) <= 1:
            continue

        def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
            is_open = 1 if item.get("status") in OPEN_STATUSES else 0
            return (is_open, str(item.get("modified") or item.get("creation")))

        sorted_items = sorted(items, key=_sort_key, reverse=True)
        primary = sorted_items[0]
        duplicates = sorted_items[1:]

        primary_name = primary["name"]
        duplicate_names = [d["name"] for d in duplicates]

        frappe.db.sql(
            """
            UPDATE `tabWhatsApp Message Log`
            SET hr_live_chat_session = %s
            WHERE hr_live_chat_session IN %s
            """,
            (primary_name, tuple(duplicate_names)),
        )

        frappe.db.sql(
            """
            UPDATE `tabWhatsApp Conversation`
            SET active_hr_chat_session = %s
            WHERE active_hr_chat_session IN %s
            """,
            (primary_name, tuple(duplicate_names)),
        )

        for dup in duplicate_names:
            frappe.delete_doc("HR Live Chat Session", dup, force=1, ignore_permissions=True)
            deleted_count += 1

    if deleted_count > 0:
        frappe.db.commit()

    return deleted_count


def expire_stale_sessions() -> None:
    """Mark open sessions as Expired when the 24-hour window has passed."""
    try:
        consolidate_duplicate_sessions()
    except Exception as e:
        frappe.log_error(f"Error in consolidate_duplicate_sessions: {e}")
    now = _now()
    stale = frappe.get_all(
        "HR Live Chat Session",
        filters={
            "status": ["in", list(OPEN_STATUSES)],
            "session_window_expires_at": ["<", now],
        },
        pluck="name",
    )
    for name in stale:
        frappe.db.set_value("HR Live Chat Session", name, "status", "Expired")
    if stale:
        frappe.db.commit()


def _create_outbound_log(
    *,
    session: Any,
    message: str,
    meta_message_id: str = "",
    user: str,
    status: str = "Sent",
    error: str = "",
    trace_id: str = "",
    message_type: str = "text",
    media_file: str = "",
) -> str:
    doc = frappe.new_doc("WhatsApp Message Log")
    doc.meta_message_id = meta_message_id or ""
    doc.direction = "Outbound"
    doc.sender = user
    doc.recipient = session.wa_id or ""
    doc.whatsapp_id = session.wa_id or ""
    doc.message_type = message_type or "text"
    doc.message = message
    doc.media_file = media_file or ""
    doc.erp_user = session.erp_user or ""
    doc.employee = session.employee or ""
    doc.status = status
    doc.delivery_status = "Failed" if status == "Failed" else "Sent"
    doc.trace_id = trace_id
    doc.hr_live_chat_session = session.name
    doc.sender_type = "HR Agent"
    doc.timestamp = _now()
    doc.error = error
    doc.flags.ignore_links = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _resolve_attachment_file(file_url: str) -> tuple[Any, bytes, str, str]:
    """Return (File doc, bytes, filename, mime type) for a Frappe file URL."""
    clean_url = (file_url or "").strip()
    if not clean_url:
        frappe.throw(_("No file was uploaded."))

    file_name = frappe.db.get_value("File", {"file_url": clean_url}, "name")
    if not file_name:
        frappe.throw(_("Uploaded file not found."))

    file_doc = frappe.get_doc("File", file_name)
    content, filename, mime_type = read_frappe_file_bytes(file_doc)

    if len(content) > MAX_ATTACHMENT_BYTES:
        frappe.throw(_("File is too large. Maximum size is 16 MB."))

    ext = os.path.splitext(filename or file_doc.file_name or "")[1].lower()
    if ext not in IMAGE_EXTENSIONS and ext not in DOCUMENT_EXTENSIONS:
        frappe.throw(_("Unsupported file type. Send images or common document formats."))

    return file_doc, content, filename, mime_type


def send_hr_attachment(
    session_name: str,
    file_url: str,
    caption: str = "",
    user: Optional[str] = None,
    trace_id: str = "",
) -> dict[str, Any]:
    user = user or frappe.session.user
    if not user_is_hr_agent(user):
        frappe.throw(_("You do not have permission to reply to HR chats."), frappe.PermissionError)

    session = get_session_doc(session_name)
    can_reply, reason = evaluate_reply_permission(session, user=user)
    if not can_reply:
        frappe.throw(reason)

    phone = frappe.db.get_value("WhatsApp Identity", session.whatsapp_identity, "normalized_phone")
    if not phone:
        frappe.throw(_("No WhatsApp phone number found for this session."))

    file_doc, content, filename, mime_type = _resolve_attachment_file(file_url)
    ext = os.path.splitext(filename or file_doc.file_name or "")[1].lower()
    is_image = ext in IMAGE_EXTENSIONS

    upload_result = upload_media_bytes(content, mime_type, filename or file_doc.file_name)
    if not upload_result.get("success"):
        frappe.throw(upload_result.get("error") or _("Failed to upload file to WhatsApp."))

    media_id = upload_result.get("media_id")
    caption_text = (caption or "").strip()
    if is_image:
        result = send_image_message(phone, media_id, caption=caption_text)
        message_type = "image"
        log_message = caption_text or file_doc.file_name
    else:
        result = send_document_message(
            phone,
            media_id,
            filename=filename or file_doc.file_name or "file",
            caption=caption_text,
        )
        message_type = "document"
        log_message = caption_text or file_doc.file_name

    now = _now()
    session.last_hr_reply_at = now
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)

    log_status = "Sent" if result.get("success") else "Failed"
    log_name = _create_outbound_log(
        session=session,
        message=log_message,
        meta_message_id=result.get("message_id") or "",
        user=user,
        status=log_status,
        error=result.get("error") or "",
        trace_id=trace_id,
        message_type=message_type,
        media_file=file_doc.file_url,
    )
    frappe.db.commit()

    publish_session_update(
        session,
        {
            "event": "outbound_message",
            "message": log_message,
            "success": result.get("success"),
            "direction": "Outbound",
            "sender_type": "HR Agent",
            "timestamp": frappe.utils.now(),
            "meta_message_id": result.get("message_id") or "",
            "log_name": log_name,
            "delivery_status": "Failed" if log_status == "Failed" else "Sent",
            "message_type": message_type,
            "media_file": file_doc.file_url,
        },
    )

    if not result.get("success"):
        frappe.throw(result.get("error") or _("Failed to send WhatsApp attachment."))

    return {
        "success": True,
        "message_id": result.get("message_id"),
        "session": _session_payload(session),
    }


def send_hr_reply(
    session_name: str,
    message: str,
    user: Optional[str] = None,
    trace_id: str = "",
) -> dict[str, Any]:
    user = user or frappe.session.user
    if not user_is_hr_agent(user):
        frappe.throw(_("You do not have permission to reply to HR chats."), frappe.PermissionError)

    text = (message or "").strip()
    if not text:
        frappe.throw(_("Message cannot be empty."))

    session = get_session_doc(session_name)
    can_reply, reason = evaluate_reply_permission(session, user=user)
    if not can_reply:
        frappe.throw(reason)

    phone = frappe.db.get_value("WhatsApp Identity", session.whatsapp_identity, "normalized_phone")
    if not phone:
        frappe.throw(_("No WhatsApp phone number found for this session."))

    result = send_text_message(phone, text)
    now = _now()
    session.last_hr_reply_at = now
    session.flags.ignore_links = True
    session.save(ignore_permissions=True)

    log_status = "Sent" if result.get("success") else "Failed"
    log_name = _create_outbound_log(
        session=session,
        message=text,
        meta_message_id=result.get("message_id") or "",
        user=user,
        status=log_status,
        error=result.get("error") or "",
        trace_id=trace_id,
    )
    frappe.db.commit()

    publish_session_update(
        session,
        {
            "event": "outbound_message",
            "message": text,
            "success": result.get("success"),
            "direction": "Outbound",
            "sender_type": "HR Agent",
            "timestamp": frappe.utils.now(),
            "meta_message_id": result.get("message_id") or "",
            "log_name": log_name,
            "delivery_status": "Failed" if log_status == "Failed" else "Sent",
            "message_type": "text",
        },
    )

    if not result.get("success"):
        frappe.throw(result.get("error") or _("Failed to send WhatsApp message."))

    return {
        "success": True,
        "message_id": result.get("message_id"),
        "session": _session_payload(session),
    }


def get_session_thread(session_name: str, limit: int = 15, start: int = 0) -> list[dict[str, Any]]:
    session = get_session_doc(session_name)

    related_session_names = {session_name}
    filters_or = []
    if session.whatsapp_identity:
        filters_or.append({"whatsapp_identity": session.whatsapp_identity})
    if session.employee:
        filters_or.append({"employee": session.employee})
    if session.wa_id:
        filters_or.append({"wa_id": session.wa_id})

    if filters_or:
        all_related = frappe.get_all(
            "HR Live Chat Session",
            or_filters=filters_or,
            pluck="name",
        )
        related_session_names.update(all_related)

    log_or_filters = [{"hr_live_chat_session": ["in", list(related_session_names)]}]
    if session.wa_id:
        log_or_filters.append({"recipient": session.wa_id})
        log_or_filters.append({"whatsapp_id": session.wa_id})
    if session.employee:
        log_or_filters.append({"employee": session.employee})

    raw_rows = frappe.get_all(
        "WhatsApp Message Log",
        or_filters=log_or_filters,
        fields=[
            "name",
            "direction",
            "message",
            "timestamp",
            "sender_type",
            "sender",
            "status",
            "delivery_status",
            "meta_message_id",
            "message_type",
            "media_file",
        ],
        order_by="timestamp desc",
        start=start,
        page_length=limit,
    )

    # Reverse to ascending chronological order for display
    raw_rows.reverse()

    seen_names = set()
    rows = []
    for row in raw_rows:
        if row["name"] not in seen_names:
            seen_names.add(row["name"])
            rows.append(row)

    for row in rows:
        if row.get("direction") == "Outbound":
            row["delivery_status"] = row.get("delivery_status") or (
                "Failed" if row.get("status") == "Failed" else "Sent"
            )

    if start == 0:
        if session.initial_query and not any(r.get("message") == session.initial_query for r in rows):
            rows.insert(
                0,
                {
                    "name": "initial-query",
                    "direction": "Inbound",
                    "message": session.initial_query,
                    "timestamp": session.opened_at,
                    "sender_type": "Employee",
                    "sender": session.display_name or "",
                    "status": "Received",
                    "meta_message_id": "",
                },
            )

        if session.guest_email:
            rows.insert(
                0,
                {
                    "name": "guest-meta",
                    "direction": "Inbound",
                    "message": _("Guest email: {0}").format(session.guest_email),
                    "timestamp": session.opened_at,
                    "sender_type": "System",
                    "sender": "",
                    "status": "Received",
                    "meta_message_id": "",
                },
            )

    return rows


def _inbox_base_filters() -> dict[str, Any]:
    """Only sessions created via Contact HR and ready for HR visibility."""
    return {
        "contact_hr_selected": 1,
        "ready_for_hr": 1,
    }


def get_session_list_title(session: Any) -> str:
    if session.display_name:
        return session.display_name
    if session.employee and frappe.db.exists("Employee", session.employee):
        name = frappe.db.get_value("Employee", session.employee, "employee_name")
        if name:
            return name
    return session.wa_id or session.name


def get_session_identity_key(session_row: dict[str, Any]) -> str:
    if session_row.get("employee"):
        return f"emp:{session_row['employee']}"
    if session_row.get("whatsapp_identity"):
        return f"wa_id:{session_row['whatsapp_identity']}"
    if session_row.get("wa_id"):
        return f"phone:{session_row['wa_id']}"
    return f"session:{session_row['name']}"


def get_inbox_sessions(status_filter: str = "queue", start: int = 0, limit: int = 15) -> list[dict[str, Any]]:
    user = frappe.session.user
    filters: dict[str, Any] = _inbox_base_filters()

    access_role = get_hr_agent_role_access(user)

    if access_role == "Assigned HR User (View & Reply Assigned Only)":
        filters["assigned_to"] = user
        if status_filter in ("queue", "mine"):
            filters["status"] = ["in", ["Assigned", "Active"]]
        elif status_filter == "closed":
            filters["status"] = "Closed"
        elif status_filter == "expired":
            filters["status"] = "Expired"
        else:
            filters["status"] = ["in", list(INBOX_STATUSES)]
    else:
        if status_filter == "queue":
            filters["status"] = "Queued"
        elif status_filter == "mine":
            filters["assigned_to"] = user
            filters["status"] = ["in", ["Assigned", "Active"]]
        elif status_filter == "closed":
            filters["status"] = "Closed"
        elif status_filter == "expired":
            filters["status"] = "Expired"
        else:
            filters["status"] = ["in", list(INBOX_STATUSES)]

    sessions = frappe.get_all(
        "HR Live Chat Session",
        filters=filters,
        fields=[
            "name",
            "status",
            "assigned_to",
            "employee",
            "erp_user",
            "wa_id",
            "whatsapp_identity",
            "display_name",
            "guest_email",
            "person_type",
            "initial_query",
            "last_user_message_at",
            "last_hr_reply_at",
            "session_window_expires_at",
            "modified",
        ],
        order_by="last_user_message_at desc, modified desc",
        start=start,
        page_length=limit,
    )

    # Merge / collapse multiple sessions belonging to the same employee / identity
    grouped_sessions: dict[str, dict[str, Any]] = {}
    for row in sessions:
        key = get_session_identity_key(row)
        if key not in grouped_sessions:
            grouped_sessions[key] = row
        else:
            existing = grouped_sessions[key]
            # Prefer active/queued session over closed session
            existing_open = existing.get("status") in OPEN_STATUSES
            row_open = row.get("status") in OPEN_STATUSES
            if row_open and not existing_open:
                grouped_sessions[key] = row

    merged_sessions = list(grouped_sessions.values())

    for row in merged_sessions:
        row["display_title"] = row.get("display_name") or row.get("employee") or row.get("wa_id") or row["name"]
        if not row.get("display_name") and row.get("employee"):
            row["display_title"] = (
                frappe.db.get_value("Employee", row["employee"], "employee_name") or row["display_title"]
            )
        if row.get("assigned_to"):
            row["assigned_to_name"] = frappe.db.get_value("User", row["assigned_to"], "full_name")
        can_reply = False
        reason = ""
        if row["name"]:
            session = get_session_doc(row["name"])
            can_reply, reason = evaluate_reply_permission(session, user=user)
        row["can_reply"] = can_reply
        row["can_reply_reason"] = reason

        # Calculate unread count for outside list indicator
        last_user = row.get("last_user_message_at")
        last_hr = row.get("last_hr_reply_at")
        if last_user and (not last_hr or last_user > last_hr):
            cnt_filters = {
                "hr_live_chat_session": row["name"],
                "direction": "Inbound",
            }
            if last_hr:
                cnt_filters["timestamp"] = [">", last_hr]
            row["unread_count"] = frappe.db.count("WhatsApp Message Log", cnt_filters)
        else:
            row["unread_count"] = 0

    return merged_sessions
