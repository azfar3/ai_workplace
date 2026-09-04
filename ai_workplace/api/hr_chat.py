"""
ai_workplace/api/hr_chat.py
────────────────────────────
Whitelisted API endpoints for the WhatsApp HR Inbox Desk page.
"""

from __future__ import annotations

import frappe
from frappe import _

from ai_workplace.services.hr_chat import (
    assign_session,
    close_session,
    get_configured_hr_chat_agents,
    get_inbox_sessions,
    get_session_doc,
    get_session_thread,
    send_hr_attachment,
    send_hr_reply,
    take_session,
    user_is_hr_agent,
)
from ai_workplace.services.office_hours import get_office_hours_info


def _ensure_hr_agent() -> None:
    if not user_is_hr_agent():
        frappe.throw(_("You do not have permission to access HR live chat."), frappe.PermissionError)


@frappe.whitelist()
def get_inbox(status_filter: str = "queue", start: int = 0, limit: int = 15) -> list[dict]:
    _ensure_hr_agent()
    start_val = frappe.utils.cint(start)
    limit_val = frappe.utils.cint(limit) or 15
    return get_inbox_sessions(status_filter=status_filter or "queue", start=start_val, limit=limit_val)


@frappe.whitelist()
def get_inbox_counts() -> dict[str, int]:
    _ensure_hr_agent()
    from ai_workplace.services.hr_chat import get_inbox_tab_counts

    return get_inbox_tab_counts()


@frappe.whitelist()
def get_session_detail(session_name: str, start: int = 0, limit: int = 15) -> dict:
    _ensure_hr_agent()
    session = get_session_doc(session_name)
    from ai_workplace.services.hr_chat import _session_payload, evaluate_reply_permission

    start_val = frappe.utils.cint(start)
    limit_val = frappe.utils.cint(limit) or 15

    payload = _session_payload(session)
    thread = get_session_thread(session_name, limit=limit_val, start=start_val)

    # Compute unread count and tag individual messages accurately using datetime objects
    last_user = session.last_user_message_at
    last_hr = session.last_hr_reply_at
    last_hr_dt = frappe.utils.get_datetime(last_hr) if last_hr else None
    last_user_dt = frappe.utils.get_datetime(last_user) if last_user else None

    unread_count = 0
    if last_user_dt and (not last_hr_dt or last_user_dt > last_hr_dt):
        cnt_filters = {"hr_live_chat_session": session_name, "direction": "Inbound"}
        if last_hr:
            cnt_filters["timestamp"] = [">", last_hr]
        unread_count = frappe.db.count("WhatsApp Message Log", cnt_filters)

    payload["unread_count"] = unread_count
    payload["last_hr_reply_at"] = session.last_hr_reply_at

    for m in thread:
        if m.get("direction") == "Inbound":
            m_dt = frappe.utils.get_datetime(m.get("timestamp")) if m.get("timestamp") else None
            if unread_count > 0 and m_dt:
                is_unread = bool(not last_hr_dt or m_dt > last_hr_dt)
            else:
                is_unread = False
            m["is_unread"] = is_unread

    payload["thread"] = thread
    payload["has_more_messages"] = len(thread) >= limit_val
    payload["thread_start"] = start_val
    office = get_office_hours_info()
    payload.update(office)
    payload["is_office_hours"] = office["is_office_hours"]
    payload["hr_support_status"] = office.get("hr_support_status")
    payload["can_reply"], payload["can_reply_reason"] = evaluate_reply_permission(session)
    payload["display_name"] = session.display_name or ""
    payload["display_title"] = session.display_name or ""
    if not payload["display_title"] and session.employee:
        payload["display_title"] = frappe.db.get_value("Employee", session.employee, "employee_name") or ""
    if session.employee:
        payload["employee_name"] = frappe.db.get_value("Employee", session.employee, "employee_name") or session.employee
    if session.guest_email:
        payload["guest_email"] = session.guest_email
    if session.initial_query:
        payload["initial_query"] = session.initial_query
    if session.person_type:
        payload["person_type"] = session.person_type
    if session.assigned_to:
        payload["assigned_to_name"] = frappe.db.get_value("User", session.assigned_to, "full_name")
    phone = frappe.db.get_value("WhatsApp Identity", session.whatsapp_identity, "normalized_phone")
    payload["phone"] = phone or ""
    return payload


@frappe.whitelist()
def take_chat(session_name: str) -> dict:
    _ensure_hr_agent()
    session = take_session(session_name)
    from ai_workplace.services.hr_chat import _session_payload

    return _session_payload(session)


@frappe.whitelist()
def assign_chat(session_name: str, assign_to: str) -> dict:
    _ensure_hr_agent()
    session = assign_session(session_name, assign_to)
    from ai_workplace.services.hr_chat import _session_payload

    return _session_payload(session)


@frappe.whitelist()
def send_reply(session_name: str, message: str) -> dict:
    _ensure_hr_agent()
    return send_hr_reply(session_name, message)


@frappe.whitelist()
def send_attachment(session_name: str, file_url: str, caption: str = "") -> dict:
    _ensure_hr_agent()
    return send_hr_attachment(session_name, file_url, caption=caption or "")


@frappe.whitelist()
def close_chat(session_name: str) -> dict:
    _ensure_hr_agent()
    session = close_session(session_name)
    from ai_workplace.services.hr_chat import _session_payload

    return _session_payload(session)


@frappe.whitelist()
def get_hr_agents() -> list[dict]:
    _ensure_hr_agent()
    configured = get_configured_hr_chat_agents()
    if configured:
        agents = []
        for user in configured:
            agents.append(
                {
                    "value": user,
                    "label": frappe.db.get_value("User", user, "full_name") or user,
                }
            )
        return sorted(agents, key=lambda x: x["label"].lower())

    users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Workplace Agent", "parenttype": "User"},
        fields=["parent"],
        distinct=True,
    )
    agents = []
    for row in users:
        user = row.parent
        if user == "Guest":
            continue
        enabled = frappe.db.get_value("User", user, "enabled")
        if not enabled:
            continue
        agents.append(
            {
                "value": user,
                "label": frappe.db.get_value("User", user, "full_name") or user,
            }
        )
    return sorted(agents, key=lambda x: x["label"].lower())


@frappe.whitelist()
def get_user_access_info() -> dict:
    _ensure_hr_agent()
    user = frappe.session.user
    from ai_workplace.services.hr_chat import get_hr_agent_role_access
    return {
        "user": user,
        "role_access": get_hr_agent_role_access(user)
    }
