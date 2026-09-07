"""
ai_workplace/services/leave_apply.py
──────────────────────────────────────
Step-by-step WhatsApp leave application workflow.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.attendance_leave import get_leave_balance_data
from ai_workplace.services.response_helpers import wrap_with_menu_again
from ai_workplace.whatsapp.interactive import (
    build_leave_type_list_message,
    build_yes_no_buttons,
)
from ai_workplace.whatsapp.outbound import OutboundMessage

_DATE_HINT = "e.g. 01-Sep-2026 or 2026-09-01"
_CANCEL_WORDS = frozenset({"cancel", "menu", "stop", "exit", "back"})


def start_leave_application(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin leave application — show assigned leave types."""
    lang = context.get("preferred_language", "English")
    employee_id = context.get("employee") or conv.employee or ""
    if not employee_id:
        err = "معذرت، چھٹی کی درخواست صرف رجسٹرڈ ملازمین کے لیے دستیاب ہے۔" if lang == "Urdu" else "Leave application is only available for linked employees."
        return wrap_with_menu_again(err, context)

    leave_types = get_leave_balance_data(employee_id)
    if not leave_types:
        if lang == "Urdu":
            err = "آپ کے اکاؤنٹ میں کوئی فعال (Active) چھٹی کا کوٹہ نہیں ملا۔\n\nاگر یہ غلط ہے تو براہ کرم HR سے رابطہ کریں۔"
        elif lang == "Roman Urdu":
            err = "Aap ke account mein koi active leave allocation nahi mila.\n\nAgar yeh ghalat hai toh HR se rabta karein."
        else:
            err = "No active leave allocation was found for your account.\n\nPlease contact HR if you believe this is incorrect."
        return wrap_with_menu_again(err, context)

    draft = {
        "step": "awaiting_leave_type",
        "employee": employee_id,
        "leave_types": leave_types,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent="leave_apply",
        active_service="attendance_leave",
        draft_payload=json.dumps(draft),
    )

    if lang == "Urdu":
        header = (
            "📝 *چھٹی کی درخواست (Apply for Leave)*\n\n"
            "آئیے آپ کی چھٹی کی درخواست مرحلہ وار جمع کروائیں۔\n\n"
            "مرحلہ 1 تا 4 — اپنی *چھٹی کی قسم* منتخب کریں:"
        )
    elif lang == "Roman Urdu":
        header = (
            "📝 *Apply for Leave*\n\n"
            "Aap ki leave application step by step submit karte hain.\n\n"
            "Step 1 of 4 — Apni *Leave Type* select karein:"
        )
    else:
        header = (
            "📝 *Apply for Leave*\n\n"
            "Let's submit your leave step by step.\n\n"
            "Step 1 of 4 — Select your *Leave Type*:"
        )

    if len(leave_types) <= 3:
        return _build_leave_type_buttons(header, leave_types)
    return build_leave_type_list_message(context, leave_types, header)


def handle_leave_apply_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> OutboundMessage:
    """Process one step of the leave application flow."""
    draft = _load_draft(conv)
    step = draft.get("step", "")
    text = (message_text or "").strip()
    clean = text.lower()

    if clean in _CANCEL_WORDS:
        return _cancel_flow(conv, context)

    if step == "awaiting_leave_type":
        return _handle_leave_type(conv, context, draft, text)
    if step == "awaiting_from_date":
        return _handle_from_date(conv, context, draft, text)
    if step == "awaiting_to_date":
        return _handle_to_date(conv, context, draft, text)
    if step == "awaiting_half_day":
        return _handle_half_day(conv, context, draft, text)
    if step == "awaiting_reason":
        return _handle_reason(conv, context, draft, text)
    if step == "awaiting_confirm":
        return _handle_confirm(conv, context, draft, text)

    lang = context.get("preferred_language", "English")
    err = "کچھ غلط ہو گیا۔ دوبارہ شروع کرنے کے لیے 'menu' ٹائپ کریں۔" if lang == "Urdu" else "Something went wrong. Type 'menu' to start again."
    return wrap_with_menu_again(err, context)


def _load_draft(conv: Any) -> dict[str, Any]:
    if not conv.draft_payload:
        return {}
    try:
        return json.loads(conv.draft_payload)
    except Exception:
        return {}


def _save_draft(conv: Any, draft: dict[str, Any]) -> None:
    update_conversation(conv, draft_payload=json.dumps(draft))


def _cancel_flow(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="attendance_leave",
        draft_payload=None,
    )
    lang = context.get("preferred_language", "English")
    msg = "چھٹی کی درخواست منسوخ کر دی گئی ہے۔" if lang == "Urdu" else "Leave application cancelled."
    return wrap_with_menu_again(msg, context)


def _build_leave_type_buttons(header: str, leave_types: list[dict[str, Any]]) -> OutboundMessage:
    buttons = []
    for idx, item in enumerate(leave_types[:3]):
        lt = item.get("leave_type") or "Leave"
        buttons.append({
            "type": "reply",
            "reply": {"id": f"lt_{idx}", "title": lt[:20]},
        })
    interactive = {
        "type": "button",
        "body": {"text": header},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def _resolve_leave_type(draft: dict[str, Any], text: str) -> Optional[str]:
    leave_types = draft.get("leave_types") or []
    clean = text.strip().lower()

    if clean.startswith("lt_") and clean[3:].isdigit():
        idx = int(clean[3:])
        if 0 <= idx < len(leave_types):
            return leave_types[idx].get("leave_type")

    for item in leave_types:
        lt = (item.get("leave_type") or "").lower()
        if clean == lt or clean in lt or lt in clean:
            return item.get("leave_type")
    return None


def _handle_leave_type(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    leave_type = _resolve_leave_type(draft, text)
    lang = context.get("preferred_language", "English")

    if not leave_type:
        if lang == "Urdu":
            err = "براہ کرم فہرست سے چھٹی کی قسم منتخب کریں، یا منسوخ کرنے کے لیے 'menu' لکھیں۔"
        elif lang == "Roman Urdu":
            err = "Baraaye meharbani list se leave type select karein, ya cancel karne ke liye 'menu' likhein."
        else:
            err = "Please select a leave type from the list, or type 'menu' to cancel."
        return OutboundMessage(body_text=err)

    draft["leave_type"] = leave_type
    draft["step"] = "awaiting_from_date"
    _save_draft(conv, draft)

    if lang == "Urdu":
        body = (
            f"✅ چھٹی کی قسم: *{leave_type}*\n\n"
            f"مرحلہ 2 تا 4 — *شروعاتی تاریخ (From Date)* درج کریں\n"
            f"فارمیٹ: 01-Sep-2026 یا 2026-09-01"
        )
    elif lang == "Roman Urdu":
        body = (
            f"✅ Leave Type: *{leave_type}*\n\n"
            f"Step 2 of 4 — Enter *From Date*\n"
            f"Format: 01-Sep-2026 ya 2026-09-01"
        )
    else:
        body = (
            f"✅ Leave Type: *{leave_type}*\n\n"
            f"Step 2 of 4 — Enter *From Date*\n"
            f"Format: {_DATE_HINT}"
        )
    return OutboundMessage(body_text=body)


def _parse_user_date(text: str) -> Optional[Any]:
    raw = (text or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return getdate(datetime.strptime(raw, fmt).date())
        except Exception:
            continue
    try:
        return getdate(raw)
    except Exception:
        return None


def _handle_from_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    from_date = _parse_user_date(text)
    lang = context.get("preferred_language", "English")

    if not from_date:
        if lang == "Urdu":
            err = f"غیر درست تاریخ۔ براہ کرم شروعاتی تاریخ اس فارمیٹ میں درج کریں: {_DATE_HINT}"
        else:
            err = f"Invalid date. Please enter From Date as {_DATE_HINT}."
        return OutboundMessage(body_text=err)

    draft["from_date"] = str(from_date)
    draft["step"] = "awaiting_to_date"
    _save_draft(conv, draft)

    formatted_from = formatdate(from_date, "dd MMM YYYY")
    if lang == "Urdu":
        body = (
            f"✅ شروعاتی تاریخ: *{formatted_from}*\n\n"
            f"مرحلہ 3 تا 4 — *آخری تاریخ (To Date)* درج کریں\n"
            f"فارمیٹ: {_DATE_HINT}"
        )
    elif lang == "Roman Urdu":
        body = (
            f"✅ From Date: *{formatted_from}*\n\n"
            f"Step 3 of 4 — Enter *To Date*\n"
            f"Format: {_DATE_HINT}"
        )
    else:
        body = (
            f"✅ From Date: *{formatted_from}*\n\n"
            f"Step 3 of 4 — Enter *To Date*\n"
            f"Format: {_DATE_HINT}"
        )
    return OutboundMessage(body_text=body)


def _handle_to_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    to_date = _parse_user_date(text)
    lang = context.get("preferred_language", "English")

    if not to_date:
        err = f"غیر درست تاریخ۔ براہ کرم آخری تاریخ درج کریں۔ ({_DATE_HINT})" if lang == "Urdu" else f"Invalid date. Please enter To Date as {_DATE_HINT}."
        return OutboundMessage(body_text=err)

    from_date = getdate(draft.get("from_date"))
    if to_date < from_date:
        err = "آخری تاریخ شروعاتی تاریخ سے پہلے نہیں ہو سکتی۔" if lang == "Urdu" else "To Date cannot be before From Date. Please try again."
        return OutboundMessage(body_text=err)

    draft["to_date"] = str(to_date)
    draft["step"] = "awaiting_half_day"
    _save_draft(conv, draft)

    formatted_to = formatdate(to_date, "dd MMM YYYY")
    if lang == "Urdu":
        prompt = (
            f"✅ آخری تاریخ: *{formatted_to}*\n\n"
            f"کیا یہ *نصف دن (Half Day)* کی چھٹی ہے؟"
        )
        yes_label = "ہاں"
        no_label = "نہیں"
    elif lang == "Roman Urdu":
        prompt = (
            f"✅ To Date: *{formatted_to}*\n\n"
            f"Kya yeh *Half Day* leave hai?"
        )
        yes_label = "Haan"
        no_label = "Nahi"
    else:
        prompt = (
            f"✅ To Date: *{formatted_to}*\n\n"
            f"Is this a *Half Day* leave?"
        )
        yes_label = "Yes"
        no_label = "No"

    return build_yes_no_buttons(prompt, yes_id="leave_half_yes", no_id="leave_half_no", yes_label=yes_label, no_label=no_label)


def _handle_half_day(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    lang = context.get("preferred_language", "English")
    is_half = clean in ("leave_half_yes", "yes", "y", "ha", "haan", "ہاں")
    is_full = clean in ("leave_half_no", "no", "n", "nahi", "na", "نہیں")

    if not is_half and not is_full:
        prompt = "براہ کرم نصف دن کی چھٹی کے لیے *ہاں* یا *نہیں* کا انتخاب کریں۔" if lang == "Urdu" else "Please tap *Yes* or *No* for half-day leave."
        yes_l = "ہاں" if lang == "Urdu" else "Yes"
        no_l = "نہیں" if lang == "Urdu" else "No"
        return build_yes_no_buttons(prompt, yes_id="leave_half_yes", no_id="leave_half_no", yes_label=yes_l, no_label=no_l)

    draft["half_day"] = 1 if is_half else 0
    if is_half:
        from_date = getdate(draft.get("from_date"))
        to_date = getdate(draft.get("to_date"))
        draft["half_day_date"] = str(from_date if from_date == to_date else from_date)

    draft["step"] = "awaiting_reason"
    _save_draft(conv, draft)

    if lang == "Urdu":
        body = (
            "مرحلہ 4 تا 4 — براہ کرم اپنی چھٹی کی *وجہ (Reason)* درج کریں\n"
            "(مختصر تفصیل):"
        )
    elif lang == "Roman Urdu":
        body = (
            "Step 4 of 4 — Baraaye meharbani apni leave ki *Reason* enter karein\n"
            "(mukhtasar waja):"
        )
    else:
        body = (
            "Step 4 of 4 — Please enter the *Reason* for your leave\n"
            "(brief description):"
        )
    return OutboundMessage(body_text=body)


def _handle_reason(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    reason = (text or "").strip()
    lang = context.get("preferred_language", "English")
    if len(reason) < 3:
        err = "براہ کرم چھٹی کی وجہ تفصیل سے لکھیں (کم از کم 3 حروف)۔" if lang == "Urdu" else "Please enter a reason (at least 3 characters)."
        return OutboundMessage(body_text=err)

    draft["description"] = reason
    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)

    summary = _build_summary(draft, context)
    prompt_tail = "\n\nکیا آپ یہ چھٹی کی درخواست جمع کروانا چاہتے ہیں؟" if lang == "Urdu" else "\n\nSubmit this leave application?"
    yes_l = "جمع کروائیں" if lang == "Urdu" else "Submit"
    no_l = "منسوخ کریں" if lang == "Urdu" else "Cancel"

    return build_yes_no_buttons(
        summary + prompt_tail,
        yes_id="leave_submit",
        no_id="leave_cancel",
        yes_label=yes_l,
        no_label=no_l,
    )


def _build_summary(draft: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    lang = (context or {}).get("preferred_language", "English")
    from_date = formatdate(draft.get("from_date"), "dd MMM YYYY")
    to_date = formatdate(draft.get("to_date"), "dd MMM YYYY")

    if lang == "Urdu":
        half = "ہاں" if draft.get("half_day") else "نہیں"
        return (
            f"📋 *چھٹی کی درخواست کا خلاصہ*\n\n"
            f"• *چھٹی کی قسم:* {draft.get('leave_type')}\n"
            f"• *شروعاتی تاریخ:* {from_date}\n"
            f"• *آخری تاریخ:* {to_date}\n"
            f"• *نصف دن (Half Day):* {half}\n"
            f"• *وجہ:* {draft.get('description')}"
        )
    elif lang == "Roman Urdu":
        half = "Haan" if draft.get("half_day") else "Nahi"
        return (
            f"📋 *Leave Application Summary*\n\n"
            f"• *Leave Type:* {draft.get('leave_type')}\n"
            f"• *From:* {from_date}\n"
            f"• *To:* {to_date}\n"
            f"• *Half Day:* {half}\n"
            f"• *Reason:* {draft.get('description')}"
        )
    else:
        half = "Yes" if draft.get("half_day") else "No"
        return (
            f"📋 *Leave Application Summary*\n\n"
            f"• *Leave Type:* {draft.get('leave_type')}\n"
            f"• *From:* {from_date}\n"
            f"• *To:* {to_date}\n"
            f"• *Half Day:* {half}\n"
            f"• *Reason:* {draft.get('description')}"
        )


def _handle_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    lang = context.get("preferred_language", "English")

    if clean in ("leave_cancel", "no", "cancel", "منسوخ کریں", "نہیں"):
        return _cancel_flow(conv, context)

    if clean not in ("leave_submit", "yes", "submit", "confirm", "جمع کروائیں", "ہاں"):
        summary = _build_summary(draft, context)
        prompt_tail = "\n\nکیا آپ یہ چھٹی کی درخواست جمع کروانا چاہتے ہیں؟" if lang == "Urdu" else "\n\nSubmit this leave application?"
        yes_l = "جمع کروائیں" if lang == "Urdu" else "Submit"
        no_l = "منسوخ کریں" if lang == "Urdu" else "Cancel"
        return build_yes_no_buttons(
            summary + prompt_tail,
            yes_id="leave_submit",
            no_id="leave_cancel",
            yes_label=yes_l,
            no_label=no_l,
        )

    try:
        doc_name = _create_leave_application(draft, context)
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Leave apply failed: {exc}")
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="attendance_leave",
            draft_payload=None,
        )
        err = f"معذرت، چھٹی کی درخواست جمع نہیں ہو سکی:\n\n{str(exc)}" if lang == "Urdu" else f"Could not submit leave application:\n\n{str(exc)}"
        return wrap_with_menu_again(err, context)

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="attendance_leave",
        draft_payload=None,
    )

    if lang == "Urdu":
        msg = (
            f"✅ *چھٹی کی درخواست جمع ہو گئی ہے*\n\n"
            f"ریفرنس: *{doc_name}*\n"
            f"حالت: *اوپن (زیرِ التوا)*\n\n"
            f"آپ کے مینیجر کو مطلع کر دیا جائے گا۔"
        )
    elif lang == "Roman Urdu":
        msg = (
            f"✅ *Leave Application Submitted*\n\n"
            f"Reference: *{doc_name}*\n"
            f"Status: *Open* (pending approval)\n\n"
            f"Aap ke supervisor ko notify kar diya jaye ga."
        )
    else:
        msg = (
            f"✅ *Leave Application Submitted*\n\n"
            f"Reference: *{doc_name}*\n"
            f"Status: *Open* (pending approver review)\n\n"
            f"Your supervisor will be notified."
        )

    return wrap_with_menu_again(msg, context)


def _create_leave_application(draft: dict[str, Any], context: dict[str, Any]) -> str:
    employee_id = draft.get("employee") or context.get("employee")
    if not employee_id:
        frappe.throw(_("Employee not found."))

    erp_user = context.get("user") or ""
    previous_user = frappe.session.user
    try:
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)

        employee = frappe.get_cached_doc("Employee", employee_id)
        doc = frappe.new_doc("Leave Application")
        doc.employee = employee_id
        doc.leave_type = draft.get("leave_type")
        doc.from_date = draft.get("from_date")
        doc.to_date = draft.get("to_date")
        doc.half_day = draft.get("half_day") or 0
        if doc.half_day and draft.get("half_day_date"):
            doc.half_day_date = draft.get("half_day_date")
        doc.description = draft.get("description") or ""
        doc.company = employee.company
        doc.leave_approver = employee.get("leave_approver") or None
        doc.posting_date = today()
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    finally:
        frappe.set_user(previous_user)
