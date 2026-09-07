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
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        msg = "آپ نے *HR سے رابطہ* منتخب کیا ہے۔\n\nبراہ کرم جاری رکھنے کے لیے اپنا *مکمل نام* درج کریں:"
    elif lang == "Roman Urdu":
        msg = "Aap ne *Contact HR* select kiya hai.\n\nBaraaye meharbani aage barhne ke liye apna *full name* enter karein:"
    else:
        msg = "You selected *Contact HR*.\n\nPlease enter your *full name* to continue:"
    return OutboundMessage(body_text=msg)


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
    lang = context.get("preferred_language", "English")

    if step == "awaiting_fullname":
        if len(text) < 2:
            if lang == "Urdu":
                err = "براہ کرم درست نام درج کریں (کم از کم 2 حروف)۔"
            elif lang == "Roman Urdu":
                err = "Baraaye meharbani apna sahi full name enter karein (kam se kam 2 characters)."
            else:
                err = "Please enter a valid full name (at least 2 characters)."
            return OutboundMessage(body_text=err)

        draft["full_name"] = text
        draft["step"] = "awaiting_email"
        update_conversation(conv, draft_payload=json.dumps(draft))

        if lang == "Urdu":
            resp = f"شکریہ، *{text}*۔\n\nبراہ کرم اپنا *ای میل ایڈریس* درج کریں:"
        elif lang == "Roman Urdu":
            resp = f"Shukriya, *{text}*.\n\nBaraaye meharbani apna *email address* enter karein:"
        else:
            resp = f"Thank you, *{text}*.\n\nPlease enter your *email address*:"
        return OutboundMessage(body_text=resp)

    if step == "awaiting_email":
        if not _EMAIL_RE.match(text):
            if lang == "Urdu":
                err = "براہ کرم درست ای میل ایڈریس درج کریں (مثال: name@example.com)۔"
            elif lang == "Roman Urdu":
                err = "Baraaye meharbani sahi email address enter karein (e.g. name@example.com)."
            else:
                err = "Please enter a valid email address (e.g. name@example.com)."
            return OutboundMessage(body_text=err)

        draft["email"] = text
        draft["step"] = "awaiting_query"
        update_conversation(conv, draft_payload=json.dumps(draft))

        if lang == "Urdu":
            resp = "بہت خوب۔\n\nبراہ کرم HR کے لیے اپنا *سوال یا پیغام* ٹائپ کریں:"
        elif lang == "Roman Urdu":
            resp = "Aacha ji.\n\nBaraaye meharbani HR ke liye apna *sawal ya paigham* type karein:"
        else:
            resp = "Got it.\n\nPlease type your *question or message* for HR:"
        return OutboundMessage(body_text=resp)

    if step == "awaiting_query":
        if len(text) < 3:
            if lang == "Urdu":
                err = "براہ کرم اپنا سوال تفصیل سے لکھیں (کم از کم 3 حروف)۔"
            elif lang == "Roman Urdu":
                err = "Baraaye meharbani apna sawal tafseel se likhein (kam se kam 3 characters)."
            else:
                err = "Please enter your question (at least 3 characters)."
            return OutboundMessage(body_text=err)

        draft["query"] = text
        return _complete_guest_intake(conv, context, draft, meta_message_id=meta_message_id)

    fallback = "معذرت، کچھ غلط ہو گیا۔ مینو میں جانے کے لیے 'menu' ٹائپ کریں۔" if lang == "Urdu" else "Something went wrong. Type 'menu' to go back."
    return OutboundMessage(body_text=fallback)


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
    lang = context.get("preferred_language", "English")

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

    from ai_workplace.services.office_hours import build_session_open_outbound
    outbound = build_session_open_outbound(context)

    if lang == "Urdu":
        header = f"شکریہ، *{full_name}*! آپ کا پیغام HR ٹیم کو ارسال کر دیا گیا ہے۔\n\n"
    elif lang == "Roman Urdu":
        header = f"Shukriya, *{full_name}*! Aap ka message HR team ko bhej diya gaya hai.\n\n"
    else:
        header = f"Thank you, *{full_name}*! Your message has been sent to HR.\n\n"

    outbound.body_text = f"{header}{outbound.body_text}"
    if outbound.interactive and outbound.interactive.get("body"):
        outbound.interactive["body"]["text"] = outbound.body_text
    return outbound
