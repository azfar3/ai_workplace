"""
ai_workplace/services/hr_guest_intake.py
─────────────────────────────────────────
Multi-step intake for public/guest users before HR live chat is queued.
Full name → Email → Query
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import frappe
from frappe import _

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.hr_chat import (
    append_inbound_message,
    open_session,
    resolve_display_name,
)
from ai_workplace.services.office_hours import build_session_open_message
from ai_workplace.whatsapp.outbound import OutboundMessage

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_guest_context(context: dict[str, Any]) -> bool:
    return context.get("person_type") == "Guest" or context.get("identity_status") == "guest"


def start_guest_intake(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin guest HR intake — ask for full name first."""
    update_conversation(
        conv,
        state=ConversationState.HR_GUEST_INTAKE,
        current_intent="contact_hr",
        active_service=None,
        draft_payload=json.dumps({"step": "awaiting_fullname"}),
        clear_active_hr_chat_session=True,
    )
    return OutboundMessage(
        body_text=_(
            "You selected *Contact HR*.\n\n"
            "Please enter your *full name* to continue:"
        )
    )


def handle_guest_intake_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
    *,
    meta_message_id: str = "",
) -> OutboundMessage:
    """Process one step of guest HR intake."""
    draft: dict[str, Any] = {}
    if conv.draft_payload:
        try:
            draft = json.loads(conv.draft_payload)
        except Exception:
            draft = {}

    step = draft.get("step", "awaiting_fullname")
    text = (message_text or "").strip()

    if step == "awaiting_fullname":
        if len(text) < 2:
            return OutboundMessage(body_text=_("Please enter a valid full name (at least 2 characters)."))
        draft["full_name"] = text
        draft["step"] = "awaiting_email"
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(
            body_text=_("Thank you, *{0}*.\n\nPlease enter your *email address*:").format(text)
        )

    if step == "awaiting_email":
        if not _EMAIL_RE.match(text):
            return OutboundMessage(body_text=_("Please enter a valid email address (e.g. name@example.com)."))
        draft["email"] = text
        draft["step"] = "awaiting_query"
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(
            body_text=_("Got it.\n\nPlease type your *question or message* for HR:")
        )

    if step == "awaiting_query":
        if len(text) < 3:
            return OutboundMessage(body_text=_("Please enter your question (at least 3 characters)."))
        draft["query"] = text
        return _complete_guest_intake(conv, context, draft, meta_message_id=meta_message_id)

    return OutboundMessage(body_text=_("Something went wrong. Type 'menu' to go back."))


def _complete_guest_intake(
    conv: Any,
    context: dict[str, Any],
    draft: dict[str, Any],
    *,
    meta_message_id: str = "",
) -> OutboundMessage:
    full_name = draft.get("full_name", "")
    email = draft.get("email", "")
    query = draft.get("query", "")

    session = open_session(
        whatsapp_identity=conv.whatsapp_identity,
        whatsapp_conversation=conv.name,
        wa_id=conv.wa_id or "",
        employee="",
        erp_user="",
        display_name=full_name,
        guest_email=email,
        initial_query=query,
        person_type="Guest",
        contact_hr_selected=True,
        ready_for_hr=True,
    )

    update_conversation(
        conv,
        state=ConversationState.LIVE_HR_CHAT,
        current_intent="contact_hr",
        active_hr_chat_session=session.name,
        draft_payload=None,
    )

    append_inbound_message(session, query, meta_message_id=meta_message_id)

    body = _(
        "Thank you, *{0}*! Your message has been sent to HR.\n\n{1}"
    ).format(full_name, build_session_open_message(context))

    return OutboundMessage(body_text=body)
