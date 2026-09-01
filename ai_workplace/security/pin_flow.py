"""
WhatsApp Support PIN user-facing flows and orchestrator helpers.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Union

import frappe

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.security.authorization import (
    authorize_whatsapp_service,
    get_pending_service,
    store_pending_service,
)
from ai_workplace.security.support_pin import verify_support_pin, get_pin_status
from ai_workplace.security.credential_redaction import is_pin_shaped_text
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message


PORTAL_URL = "https://portal.micromerger.com"
PIN_RECHECK_TRIGGERS = {
    "i have set my pin",
    "pin_set_done",
    "svc_pin_set_done",
}
PIN_SETUP_BUTTON_IDS = {
    "svc_open_hrmis",
    "svc_pin_set_done",
    "svc_pin_retry",
    "open_hrmis",
    "pin_set_done",
    "pin_retry",
}
FORGOT_PIN_TRIGGERS = {"forgot pin", "forgot pin?", "svc_forgot_pin"}


def _portal_url() -> str:
    return PORTAL_URL


def build_hrmis_portal_guide_message(context: dict[str, Any]) -> OutboundMessage:
    """Step-by-step guide to set Support PIN on HRMIS Portal."""
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🌐 *HRMIS Portal — Support PIN سیٹ کریں*\n\n"
            f"1. {PORTAL_URL} پر جائیں\n"
            "2. اپنا *username* اور *password* سے login کریں\n"
            "3. *Settings* کھولیں\n"
            "4. *Security* ٹیب پر جائیں\n"
            "5. اپنا *4-digit Support PIN* set یا reset کریں\n\n"
            "مکمل ہونے کے بعد یہاں واپس آئیں اور *I Have Set My PIN* دبائیں۔"
        )
    elif lang == "Roman Urdu":
        body = (
            "🌐 *HRMIS Portal — Support PIN Set Karein*\n\n"
            f"1. {PORTAL_URL} par jayein\n"
            "2. Apne *username* aur *password* se login karein\n"
            "3. *Settings* kholen\n"
            "4. *Security* tab par jayein\n"
            "5. Apna *4-digit Support PIN* set ya reset karein\n\n"
            "Complete hone ke baad yahan wapas aayein aur *I Have Set My PIN* dabayein."
        )
    else:
        body = (
            "🌐 *HRMIS Portal — Set Your Support PIN*\n\n"
            f"1. Go to {PORTAL_URL}\n"
            "2. Log in with your *username* and *password*\n"
            "3. Open *Settings*\n"
            "4. Go to the *Security* tab\n"
            "5. Set or reset your *4-digit Support PIN*\n\n"
            "When done, return here and tap *I Have Set My PIN* to continue."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_pin_set_done", "title": "I Have Set My PIN"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def build_pin_not_configured_message(context: dict[str, Any], pending_service: str) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🔐 *محفوظ رسائی درکار ہے*\n\n"
            "ذاتی HR معلومات تک رسائی کے لیے پہلے HRMIS پورٹل میں اپنا "
            "*4 ہندسوں کا Support PIN* سیٹ کریں۔\n\n"
            f"{PORTAL_URL} → login → *Settings* → *Security* tab\n\n"
            "مکمل ہونے کے بعد *I Have Set My PIN* دبائیں۔"
        )
    elif lang == "Roman Urdu":
        body = (
            "🔐 *Secure Access Required*\n\n"
            "Apni personal HR information ke liye pehle HRMIS Portal mein apna "
            "*4-digit Support PIN* set karein.\n\n"
            f"{PORTAL_URL} → login → *Settings* → *Security* tab\n\n"
            "Complete hone ke baad *I Have Set My PIN* dabayein."
        )
    else:
        body = (
            "🔐 *Secure Access Required*\n\n"
            "Please set your *Support PIN* first on the HRMIS Portal.\n\n"
            f"Go to {PORTAL_URL} → login → *Settings* → *Security* tab.\n\n"
            "Once completed, return here and tap *I Have Set My PIN*."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_open_hrmis", "title": "Open HRMIS Portal"},
            {"id": "svc_pin_set_done", "title": "I Have Set My PIN"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def build_pin_prompt_message(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🔐 *تصدیق درکار ہے*\n\n"
            "براہ کرم اپنا *4-digit Support PIN* درج کریں۔\n\n"
            "PIN بھول گئے؟ Portal → Settings → Security سے reset کریں۔"
        )
    elif lang == "Roman Urdu":
        body = (
            "🔐 *Verification Required*\n\n"
            "Apna *4-digit Support PIN* enter karein.\n\n"
            "PIN bhool gaye? Portal → Settings → Security se reset karein."
        )
    else:
        body = (
            "🔐 *Verification Required*\n\n"
            "Please enter your *4-digit Support PIN* to continue.\n\n"
            "Forgot PIN? Reset it on the Portal under *Settings* → *Security*."
        )
    return OutboundMessage(body_text=body)


def build_pin_verified_message(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return "✅ *کامیابی سے تصدیق ہو گئی۔*"
    if lang == "Roman Urdu":
        return "✅ *Successfully verified.*"
    return "✅ *Verified successfully.*"


def build_pin_failed_message(context: dict[str, Any], attempts_remaining: int = 0, locked_until=None) -> str:
    lang = context.get("preferred_language", "English")
    if locked_until:
        if lang == "Urdu":
            return f"🔒 بہت زیادہ غلط کوششیں۔ {locked_until} تک لاک ہے۔"
        return f"🔒 Too many failed attempts. Locked until {locked_until}."
    if lang == "Urdu":
        return f"❌ غلط PIN۔ باقی کوششیں: {attempts_remaining}"
    return f"❌ Incorrect PIN. Attempts remaining: {attempts_remaining}"


def build_forgot_pin_message(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🔐 *Support PIN بھول گئے؟*\n\n"
            "سیکیورٹی کے لیے PIN WhatsApp سے reset نہیں ہو سکتا۔\n"
            "HRMIS Portal → My Profile میں نیا PIN سیٹ کریں۔"
        )
    else:
        body = (
            "🔐 *Forgot your Support PIN?*\n\n"
            "For your security, Support PINs cannot be reset through WhatsApp.\n\n"
            f"Go to {PORTAL_URL} → login → *Settings* → *Security* tab "
            "to set a new Support PIN."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_open_hrmis", "title": "Open HRMIS Portal"},
            {"id": "svc_pin_retry", "title": "Try Again"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def maybe_gate_service(
    conv: Any,
    context: dict[str, Any],
    service_key: str,
) -> Optional[OutboundMessage]:
    """Return outbound message if service is blocked pending PIN; else None."""
    auth = authorize_whatsapp_service(
        context,
        service_key,
        conversation_name=conv.name,
    )
    if auth.get("allowed"):
        return None

    reason = auth.get("reason")
    if reason == "PIN_NOT_CONFIGURED":
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            draft_payload=store_pending_service(conv, service_key),
        )
        return build_pin_not_configured_message(context, service_key)

    if reason == "LOCKED":
        return OutboundMessage(
            body_text=build_pin_failed_message(
                context,
                locked_until=auth.get("locked_until"),
            )
        )

    if reason == "PIN_REQUIRED":
        update_conversation(
            conv,
            state=ConversationState.WAITING_FOR_SUPPORT_PIN,
            draft_payload=store_pending_service(conv, service_key),
            current_intent="support_pin_verify",
        )
        return build_pin_prompt_message(context)

    return None


def _normalize_pin_button_id(message_text: str) -> str:
    """Normalize interactive button id or button label to a known action key."""
    clean = (message_text or "").strip()
    lower = clean.lower()
    if lower.startswith("svc_"):
        return lower[4:]
    if lower in PIN_RECHECK_TRIGGERS:
        return "pin_set_done"
    if lower in ("open hrmis portal", "open hrmis"):
        return "open_hrmis"
    if lower in ("try again",):
        return "pin_retry"
    return lower


def handle_pin_setup_action(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> Optional[OutboundMessage]:
    """
    Handle PIN-setup buttons (Open HRMIS Portal, I Have Set My PIN) when PIN
    is not yet configured. Works regardless of conversation state.
    """
    action = _normalize_pin_button_id(message_text)
    if action not in ("open_hrmis", "pin_set_done", "pin_retry"):
        return None

    pending = get_pending_service(conv.draft_payload or "")

    if action == "open_hrmis":
        return build_hrmis_portal_guide_message(context)

    if action in ("pin_set_done", "pin_retry"):
        employee = context.get("employee") or ""
        status = get_pin_status(employee)
        if not status.get("configured"):
            return build_pin_not_configured_message(context, pending or "")
        update_conversation(
            conv,
            state=ConversationState.WAITING_FOR_SUPPORT_PIN,
            current_intent="support_pin_verify",
            draft_payload=store_pending_service(conv, pending) if pending else conv.draft_payload,
        )
        return build_pin_prompt_message(context)

    return None


def handle_waiting_for_pin(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
    *,
    wa_id: str = "",
) -> Union[OutboundMessage, str, None]:
    """
    Handle inbound while WAITING_FOR_SUPPORT_PIN.
    Returns None if message should fall through to normal routing.
    """
    clean = (message_text or "").strip()
    lower = clean.lower()

    if lower in FORGOT_PIN_TRIGGERS or clean == "svc_forgot_pin":
        return build_forgot_pin_message(context)

    setup_action = handle_pin_setup_action(conv, clean, context)
    if setup_action is not None:
        return setup_action

    if lower in PIN_RECHECK_TRIGGERS or clean in ("svc_pin_set_done",):
        employee = context.get("employee") or ""
        status = get_pin_status(employee)
        pending = get_pending_service(conv.draft_payload or "")
        if not status.get("configured"):
            return build_pin_not_configured_message(context, pending or "")
        update_conversation(
            conv,
            state=ConversationState.WAITING_FOR_SUPPORT_PIN,
            current_intent="support_pin_verify",
        )
        return build_pin_prompt_message(context)

    if not is_pin_shaped_text(clean):
        return OutboundMessage(
            body_text=build_pin_failed_message(context, attempts_remaining=0)
            + "\n\nType *forgot pin* for help or *menu* to go back."
        )

    employee = context.get("employee") or ""
    result = verify_support_pin(
        employee,
        clean,
        conversation=conv.name,
        wa_id=wa_id,
        user=context.get("user") or "",
    )

    if not result.get("success"):
        reason = result.get("reason")
        if reason == "LOCKED":
            return OutboundMessage(
                body_text=build_pin_failed_message(
                    context,
                    locked_until=result.get("locked_until"),
                )
            )
        return OutboundMessage(
            body_text=build_pin_failed_message(
                context,
                attempts_remaining=result.get("attempts_remaining", 0),
            )
        )

    pending = get_pending_service(conv.draft_payload or "")
    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        draft_payload=json.dumps({"resume_service_key": pending}) if pending else None,
    )
    verified = build_pin_verified_message(context)
    return OutboundMessage(body_text=verified)


def get_resume_service_key(conv: Any) -> Optional[str]:
    if not conv.draft_payload:
        return None
    try:
        data = json.loads(conv.draft_payload)
        return data.get("resume_service_key")
    except Exception:
        return None


def clear_resume_service_key(conv: Any) -> None:
    update_conversation(conv, draft_payload=None)
