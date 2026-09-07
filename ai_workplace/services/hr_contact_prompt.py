"""
ai_workplace/services/hr_contact_prompt.py
───────────────────────────────────────────
Contact HR intro — phone, email, and wait-to-connect option before live chat.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe import _

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.whatsapp.outbound import OutboundMessage

WAIT_BUTTON_ID = "hr_wait_connect"
_DEFAULT_PHONE = "051 8444 777"
_DEFAULT_WHATSAPP = "03111123702"
_DEFAULT_EMAIL = "hr@MicroMerger.com"

_WAIT_ALIASES = {
    WAIT_BUTTON_ID,
    "wait for hr",
    "wait",
    "connect",
    "connect hr",
    "start chat",
    "chat with hr",
    "hr connect",
    "leave message",
    "پیغام چھوڑیں",
    "پیغام چھوڑیں",
    "message chhorin",
    "hr سے بات کریں",
}


def get_hr_contact_details() -> tuple[str, str, str]:
    try:
        settings = frappe.get_single("AI Workplace Settings")
        phone = (settings.get("hr_contact_phone") or _DEFAULT_PHONE).strip()
        whatsapp = (settings.get("hr_contact_whatsapp") or _DEFAULT_WHATSAPP).strip()
        email = (settings.get("hr_contact_email") or _DEFAULT_EMAIL).strip()
        return phone or _DEFAULT_PHONE, whatsapp or _DEFAULT_WHATSAPP, email or _DEFAULT_EMAIL
    except Exception:
        return _DEFAULT_PHONE, _DEFAULT_WHATSAPP, _DEFAULT_EMAIL


def is_wait_for_hr_selection(user_input: str) -> bool:
    clean = (user_input or "").strip().lower()
    if not clean:
        return False
    if clean in _WAIT_ALIASES:
        return True
    return clean.startswith(WAIT_BUTTON_ID)


def is_contact_hr_menu_resubmit(user_input: str) -> bool:
    """True when user taps Chat with HR again while already on the HR contact step."""
    clean = (user_input or "").strip().lower()
    return clean in ("svc_contact_hr", "contact_hr", "💬 chat with hr")


def _contact_hr_body(context: dict[str, Any]) -> str:
    from ai_workplace.services.office_hours import (
        build_closed_hours_message,
        build_open_hours_message,
        get_hr_support_status,
    )

    phone, whatsapp, email = get_hr_contact_details()
    lang = context.get("preferred_language", "English")
    employee = context.get("employee")
    status = get_hr_support_status(employee=employee)

    if status["is_open"]:
        availability = build_open_hours_message(context)
    else:
        availability = build_closed_hours_message(context, employee=employee)

    wa_line_ur = f"• واٹس ایپ: {whatsapp}\n" if whatsapp else ""
    wa_line_en = f"• WhatsApp: {whatsapp}\n" if whatsapp else ""

    if lang == "Urdu":
        contact_block = (
            f"☎️ *HR سے رابطہ*\n\n"
            f"{availability}\n\n"
            f"• فون: {phone}\n"
            f"{wa_line_ur}"
            f"• ای میل: {email}"
        )
    elif lang == "Roman Urdu":
        contact_block = (
            f"☎️ *Contact HR*\n\n"
            f"{availability}\n\n"
            f"• Call: {phone}\n"
            f"{wa_line_en}"
            f"• Email: {email}"
        )
    else:
        contact_block = (
            f"💬 *Chat with HR*\n\n"
            f"{availability}\n\n"
            f"• Call: {phone}\n"
            f"{wa_line_en}"
            f"• Email: {email}"
        )
    return contact_block


def _wait_button_title(lang: str, *, is_open: bool) -> str:
    if is_open:
        if lang == "Urdu":
            return "HR سے بات کریں"
        if lang == "Roman Urdu":
            return "HR Se Baat Karein"
        return "Chat with HR"
    if lang == "Urdu":
        return "پیغام چھوڑیں"
    if lang == "Roman Urdu":
        return "Message Chhorin"
    return "Leave Message"


def _menu_button_title(lang: str) -> str:
    if lang == "Urdu":
        return "اصلی مینو"
    if lang == "Roman Urdu":
        return "Main Menu"
    return "Main Menu"


def build_contact_hr_options_message(context: dict[str, Any]) -> OutboundMessage:
    """Show HR contact options when CLOSED with Leave Message and Main Menu action buttons."""
    from ai_workplace.services.office_hours import get_hr_support_status
    from ai_workplace.whatsapp.interactive import _truncate

    lang = context.get("preferred_language", "English")
    employee = context.get("employee")
    status = get_hr_support_status(employee=employee)
    body = _truncate(_contact_hr_body(context), 1024)
    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {
                        "id": WAIT_BUTTON_ID,
                        "title": _wait_button_title(lang, is_open=False)[:20],
                    },
                },
                {
                    "type": "reply",
                    "reply": {
                        "id": "main_menu",
                        "title": _menu_button_title(lang)[:20],
                    },
                },
            ]
        },
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def handle_contact_hr_intro(
    conv: Any,
    context: dict[str, Any],
    trace_id: str = "",
    identity: Any = None,
) -> OutboundMessage:
    """
    First step after Contact HR.
    Within office hours (OPEN): automatically connect & show direct response message.
    Outside office hours (CLOSED): show off-hours info with Leave Message & Main Menu buttons.
    """
    from ai_workplace.services.office_hours import get_hr_support_status

    status = get_hr_support_status(employee=context.get("employee"))

    if status["is_open"]:
        from ai_workplace.services.hr_chat import handle_contact_hr_connect

        return handle_contact_hr_connect(
            conv,
            context,
            trace_id=trace_id,
            identity=identity,
        )

    update_conversation(
        conv,
        state=ConversationState.HR_CONTACT_PROMPT,
        current_intent="contact_hr",
        active_service=None,
        draft_payload={},
        clear_active_hr_chat_session=True,
    )
    return build_contact_hr_options_message(context)


def _is_direct_hr_message(message_text: str) -> bool:
    """True when the user typed a substantive message instead of tapping Leave Message."""
    clean = (message_text or "").strip()
    if len(clean) < 3:
        return False
    lower = clean.lower()
    return lower not in {
        "menu",
        "home",
        "back",
        "main menu",
        "main_menu",
        "cancel",
    }


def handle_contact_hr_prompt_reply(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
    *,
    identity: Any = None,
    trace_id: str = "",
    meta_message_id: str = "",
) -> OutboundMessage:
    """User confirmed they want to wait — start live chat or guest intake."""
    if is_contact_hr_menu_resubmit(message_text):
        return build_contact_hr_options_message(context)

    import json
    draft_raw = conv.draft_payload or "{}"
    try:
        draft = json.loads(draft_raw) if isinstance(draft_raw, str) else (draft_raw or {})
    except Exception:
        draft = {}

    awaiting = draft.get("awaiting_leave_message")

    if is_wait_for_hr_selection(message_text) and not awaiting:
        update_conversation(
            conv,
            draft_payload=json.dumps({"awaiting_leave_message": True}),
        )
        lang = context.get("preferred_language", "English")
        if lang == "Urdu":
            msg = (
                "💬 *ایچ آر کے لیے پیغام تحریر کریں*\n\n"
                "براہ کرم اپنا پیغام یا سوال نیچے ٹائپ کریں۔ ایچ آر نمائندہ ورکنگ آورز میں آپ کو جواب دے گا۔"
            )
        elif lang == "Roman Urdu":
            msg = (
                "💬 *Message for HR*\n\n"
                "Barah-e-karam apna message ya sawal neeche type karein. HR representative working hours mein aap ko jawab dega."
            )
        else:
            msg = (
                "💬 *Message for HR*\n\n"
                "Please type your message or question for HR below. An HR representative will respond during working hours."
            )
        return OutboundMessage(body_text=msg)

    # Process message as the off-hours inquiry message
    from ai_workplace.services.hr_chat import (
        handle_contact_hr_connect,
        handle_live_hr_inbound,
    )

    handle_contact_hr_connect(
        conv,
        context,
        trace_id=trace_id,
        identity=identity,
    )
    if message_text:
        handle_live_hr_inbound(
            conv,
            message_text,
            meta_message_id=meta_message_id,
            trace_id=trace_id,
        )

    update_conversation(conv, draft_payload=None)

    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🟢 *پیغام ایچ آر کو موصول ہو گیا ہے*\n\n"
            "آپ کا پیغام ایچ آر ٹیم کو موصول ہو گیا ہے اور کیو (Queue) میں شامل کر دیا گیا ہے۔ نمائندہ ورکنگ آورز میں آپ کو جواب دے گا۔\n\n"
            "💡 *اگر آپ مزید پیغامات بھیجنا چاہتے ہیں تو بھیج سکتے ہیں۔ سیشن ختم کرنے کے لیے نیچے '🔴 چیٹ ختم کریں' پر کلک کریں یا 'menu' لکھیں۔*"
        )
        btn_title = "🔴 چیٹ ختم کریں"
    elif lang == "Roman Urdu":
        body = (
            "🟢 *Message HR Ko Recieve Ho Gaya Hai*\n\n"
            "Aap ka message HR team ko mil gaya hai aur queue mein shamil kar diya gaya hai. HR representative working hours mein aap ko jawab dega.\n\n"
            "💡 *Agar aap mazeed messages bhejna chahte hain toh bhej sakte hain. Session close karne ke liye neeche '🔴 Chat Khatam Karein' button dabayein ya 'menu' likhein.*"
        )
        btn_title = "🔴 Chat Khatam Karein"
    else:
        body = (
            "🟢 *Message Queued for HR*\n\n"
            "Your message has been queued for HR support. An HR representative will respond during working hours.\n\n"
            "💡 *You can send more messages if needed. When finished, tap '🔴 End HR Chat' below or type 'menu' at any time to end the session.*"
        )
        btn_title = "🔴 End HR Chat"

    from ai_workplace.whatsapp.interactive import build_button_message
    return build_button_message(
        body=body,
        buttons=[
            {"id": "svc_end_hr_chat", "title": btn_title[:20]},
        ]
    )
