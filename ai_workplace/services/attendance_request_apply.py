"""
ai_workplace/services/attendance_request_apply.py
────────────────────────────────────────────────────
Multi-step workflow for submitting an Attendance Request.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import (
    cint,
    formatdate,
    getdate,
    today,
)

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.response_helpers import wrap_with_parent_menu
from ai_workplace.whatsapp.interactive import (
    build_option_list_message,
    build_yes_no_buttons,
)
from ai_workplace.whatsapp.outbound import OutboundMessage

ATTENDANCE_REQUEST_REASONS = [
    "Check In Miss",
    "Check Out Miss",
    "Work From Home",
    "On Duty",
    "Adjustment",
    "Actual Hours Adjustment",
]


def check_attendance_request_permission(user: str | None = None) -> bool:
    """Check if the session user has permission to create an Attendance Request."""
    user_to_check = user or frappe.session.user
    if not user_to_check or user_to_check == "Guest":
        return False
    try:
        return bool(frappe.has_permission("Attendance Request", ptype="create", user=user_to_check))
    except Exception:
        return False


def start_attendance_request_application(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Entry point for starting the Attendance Request workflow."""
    user_to_check = context.get("user") or frappe.session.user
    if not check_attendance_request_permission(user_to_check):
        lang = context.get("preferred_language", "English")
        if lang == "Urdu":
            msg = "معذرت، آپ کے پاس حاضری کی درخواست (Attendance Request) کی اجازت نہیں ہے۔"
        elif lang == "Roman Urdu":
            msg = "Maazrat, aap ke pas Attendance Request create karne ki permission nahi hai."
        else:
            msg = "Sorry, you do not have permission to create an Attendance Request."
        return wrap_with_parent_menu(msg, context, "attendance_leave")

    draft = {
        "step": "awaiting_reason",
        "employee": conv.employee or context.get("employee"),
        "reasons": ATTENDANCE_REQUEST_REASONS,
    }
    _save_draft(conv, draft)

    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent="att_request_apply",
        active_service="attendance_leave",
        draft_payload=json.dumps(draft),
    )

    return _build_reason_selection_message(context, ATTENDANCE_REQUEST_REASONS)


def handle_attendance_request_message(conv: Any, text: str, context: dict[str, Any]) -> OutboundMessage:
    """Handle multi-step inputs for the Attendance Request application."""
    draft = _get_draft(conv)
    step = draft.get("step", "awaiting_reason")

    if step == "awaiting_reason":
        return _handle_reason(conv, context, draft, text)
    elif step == "awaiting_from_date":
        return _handle_from_date(conv, context, draft, text)
    elif step == "awaiting_to_date":
        return _handle_to_date(conv, context, draft, text)
    elif step == "awaiting_explanation":
        return _handle_explanation(conv, context, draft, text)
    elif step == "awaiting_confirm":
        return _handle_confirm(conv, context, draft, text)
    else:
        return start_attendance_request_application(conv, context)


def _handle_reason(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip()
    reasons = draft.get("reasons") or ATTENDANCE_REQUEST_REASONS
    selected_reason = None

    if clean.startswith("att_reason_"):
        try:
            idx = int(clean.split("_")[-1])
            if 0 <= idx < len(reasons):
                selected_reason = reasons[idx]
        except ValueError:
            pass

    if not selected_reason:
        # Match exact or case-insensitive string
        for r in reasons:
            if clean.lower() == r.lower():
                selected_reason = r
                break

    if not selected_reason:
        lang = context.get("preferred_language", "English")
        prompt = (
            "براہ کرم فہرست سے صحیح وجہ منتخب کریں۔"
            if lang == "Urdu"
            else "Please select a valid reason from the menu."
        )
        return _build_reason_selection_message(context, reasons, error_prompt=prompt)

    draft["reason"] = selected_reason
    draft["step"] = "awaiting_from_date"
    _save_draft(conv, draft)

    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            f"✅ وجہ: *{selected_reason}*\n\n"
            "مرحلہ 2 تا 4 — *شروعاتی تاریخ (From Date)* درج کریں:\n"
            "فارمیٹ: e.g. 01-Sep-2026 یا 2026-09-01"
        )
    elif lang == "Roman Urdu":
        body = (
            f"✅ Reason: *{selected_reason}*\n\n"
            "Step 2 of 4 — *From Date* enter karein:\n"
            "Format: e.g. 01-Sep-2026 ya 2026-09-01"
        )
    else:
        body = (
            f"✅ Reason: *{selected_reason}*\n\n"
            "Step 2 of 4 — Enter *From Date*:\n"
            "Format: e.g. 01-Sep-2026 or 2026-09-01"
        )

    return OutboundMessage(body_text=body)


def _handle_from_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    dt = _parse_user_date(text)
    lang = context.get("preferred_language", "English")

    if not dt:
        err = (
            "تاریخ درست نہیں ہے۔ براہ کرم DD-MMM-YYYY (e.g. 15-Sep-2026) فارمیٹ میں لکھیں۔"
            if lang == "Urdu"
            else "Invalid date format. Please enter as DD-MMM-YYYY (e.g. 15-Sep-2026)."
        )
        return OutboundMessage(body_text=err)

    draft["from_date"] = str(dt)
    draft["step"] = "awaiting_to_date"
    _save_draft(conv, draft)

    from_formatted = formatdate(str(dt), "dd MMM YYYY")
    if lang == "Urdu":
        body = (
            f"✅ شروعاتی تاریخ: *{from_formatted}*\n\n"
            "مرحلہ 3 تا 4 — *آخری تاریخ (To Date)* درج کریں:\n"
            "اگر صرف ایک دن ہے تو وہی تاریخ یا 'same' لکھیں۔"
        )
    elif lang == "Roman Urdu":
        body = (
            f"✅ From Date: *{from_formatted}*\n\n"
            "Step 3 of 4 — *To Date* enter karein:\n"
            "Agar 1 hi din hai to wahi date ya 'same' likhein."
        )
    else:
        body = (
            f"✅ From Date: *{from_formatted}*\n\n"
            "Step 3 of 4 — Enter *To Date*:\n"
            "If single day, enter same date or type 'same'."
        )

    return OutboundMessage(body_text=body)


def _handle_to_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    from_str = draft.get("from_date")
    lang = context.get("preferred_language", "English")

    if clean in ("same", "ایک ہی دن", "1 day", "wahi"):
        dt = getdate(from_str)
    else:
        dt = _parse_user_date(text)

    if not dt:
        err = (
            "تاریخ درست نہیں ہے۔ براہ کرم DD-MMM-YYYY فارمیٹ میں لکھیں یا 'same' درج کریں۔"
            if lang == "Urdu"
            else "Invalid date format. Please enter as DD-MMM-YYYY or type 'same'."
        )
        return OutboundMessage(body_text=err)

    from_dt = getdate(from_str)
    if dt < from_dt:
        err = (
            "آخری تاریخ شروعاتی تاریخ سے پہلے نہیں ہو سکتی۔"
            if lang == "Urdu"
            else "To Date cannot be before From Date."
        )
        return OutboundMessage(body_text=err)

    draft["to_date"] = str(dt)
    draft["step"] = "awaiting_explanation"
    _save_draft(conv, draft)

    if lang == "Urdu":
        body = (
            "مرحلہ 4 تا 4 — براہ کرم حاضری کی درخواست کی *تفصیل (Explanation)* درج کریں:\n"
            "(مختصر وجہ درج کریں)"
        )
    elif lang == "Roman Urdu":
        body = (
            "Step 4 of 4 — Baraye meharbani attendance request ki *Explanation* enter karein:\n"
            "(mukhtasar waja)"
        )
    else:
        body = (
            "Step 4 of 4 — Please enter the *Explanation* for your attendance request:\n"
            "(brief details)"
        )

    return OutboundMessage(body_text=body)


def _handle_explanation(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    explanation = (text or "").strip()
    lang = context.get("preferred_language", "English")

    if len(explanation) < 3:
        err = (
            "براہ کرم وجہ تفصیل سے لکھیں (کم از کم 3 حروف)۔"
            if lang == "Urdu"
            else "Please enter an explanation (at least 3 characters)."
        )
        return OutboundMessage(body_text=err)

    draft["explanation"] = explanation
    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)

    summary = _build_summary(draft, context)
    prompt_tail = (
        "\n\nکیا آپ یہ حاضری کی درخواست جمع کروانا چاہتے ہیں؟"
        if lang == "Urdu"
        else "\n\nSubmit this attendance request?"
    )
    yes_l = "جمع کروائیں" if lang == "Urdu" else "Submit"
    no_l = "منسوخ کریں" if lang == "Urdu" else "Cancel"

    return build_yes_no_buttons(
        summary + prompt_tail,
        yes_id="att_req_submit",
        no_id="att_req_cancel",
        yes_label=yes_l,
        no_label=no_l,
    )


def _handle_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    lang = context.get("preferred_language", "English")

    if clean in ("att_req_cancel", "no", "cancel", "منسوخ کریں", "نہیں"):
        return _cancel_flow(conv, context)

    if clean not in ("att_req_submit", "yes", "submit", "confirm", "جمع کروائیں", "ہاں"):
        summary = _build_summary(draft, context)
        prompt_tail = (
            "\n\nکیا آپ یہ حاضری کی درخواست جمع کروانا چاہتے ہیں؟"
            if lang == "Urdu"
            else "\n\nSubmit this attendance request?"
        )
        yes_l = "جمع کروائیں" if lang == "Urdu" else "Submit"
        no_l = "منسوخ کریں" if lang == "Urdu" else "Cancel"
        return build_yes_no_buttons(
            summary + prompt_tail,
            yes_id="att_req_submit",
            no_id="att_req_cancel",
            yes_label=yes_l,
            no_label=no_l,
        )

    try:
        doc_name = _create_attendance_request(draft, context)
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Attendance Request submission failed: {exc}")
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="attendance_leave",
            draft_payload=None,
        )
        err = (
            f"معذرت، حاضری کی درخواست جمع نہیں ہو سکی:\n\n{str(exc)}"
            if lang == "Urdu"
            else f"Could not submit attendance request:\n\n{str(exc)}"
        )
        return wrap_with_parent_menu(err, context, "attendance_leave")

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="attendance_leave",
        draft_payload=None,
    )

    if lang == "Urdu":
        msg = (
            f"✅ *حاضری کی درخواست جمع ہو گئی ہے*\n\n"
            f"ریفرنس: *{doc_name}*\n\n"
            f"آپ کے مینیجر کو مطلع کر دیا جائے گا۔"
        )
    elif lang == "Roman Urdu":
        msg = (
            f"✅ *Attendance Request Submitted*\n\n"
            f"Reference: *{doc_name}*\n\n"
            f"Aap ke supervisor ko notify kar diya jaye ga."
        )
    else:
        msg = (
            f"✅ *Attendance Request Submitted*\n\n"
            f"Reference: *{doc_name}*\n\n"
            f"Your supervisor will be notified."
        )

    return wrap_with_parent_menu(msg, context, "attendance_leave")


def _build_summary(draft: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    lang = (context or {}).get("preferred_language", "English")
    from_date = formatdate(draft.get("from_date"), "dd MMM YYYY")
    to_date = formatdate(draft.get("to_date"), "dd MMM YYYY")
    reason = draft.get("reason", "N/A")
    explanation = draft.get("explanation", "N/A")

    if lang == "Urdu":
        return (
            f"📋 *حاضری کی درخواست کا خلاصہ*\n\n"
            f"• *وجہ (Reason):* {reason}\n"
            f"• *شروعاتی تاریخ:* {from_date}\n"
            f"• *آخری تاریخ:* {to_date}\n"
            f"• *تفصیل:* {explanation}"
        )
    elif lang == "Roman Urdu":
        return (
            f"📋 *Attendance Request Summary*\n\n"
            f"• *Reason:* {reason}\n"
            f"• *From Date:* {from_date}\n"
            f"• *To Date:* {to_date}\n"
            f"• *Explanation:* {explanation}"
        )
    else:
        return (
            f"📋 *Attendance Request Summary*\n\n"
            f"• *Reason:* {reason}\n"
            f"• *From Date:* {from_date}\n"
            f"• *To Date:* {to_date}\n"
            f"• *Explanation:* {explanation}"
        )


def _create_attendance_request(draft: dict[str, Any], context: dict[str, Any]) -> str:
    employee_id = draft.get("employee") or context.get("employee")
    if not employee_id:
        frappe.throw(_("Employee not found."))

    erp_user = context.get("user") or ""
    previous_user = frappe.session.user
    try:
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)

        employee = frappe.get_cached_doc("Employee", employee_id)
        doc = frappe.new_doc("Attendance Request")
        doc.employee = employee_id
        doc.from_date = draft.get("from_date")
        doc.to_date = draft.get("to_date")
        doc.reason = draft.get("reason")
        doc.explanation = draft.get("explanation") or ""
        doc.company = employee.company

        # Populate mandatory leave_approver field
        leave_approver = employee.leave_approver
        if not leave_approver and employee.reports_to:
            leave_approver = frappe.db.get_value("Employee", employee.reports_to, "user_id")
        if not leave_approver:
            hr_user = frappe.db.get_value("Has Role", {"role": ["in", ["HR Manager", "HR User"]]}, "parent")
            leave_approver = hr_user or "Administrator"
        doc.leave_approver = leave_approver

        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except Exception as exc:
        frappe.log_error(
            title="Attendance Request Submission Failed",
            message=f"Failed to submit Attendance Request for employee '{employee_id}': {exc}\n\nDraft: {json.dumps(draft, default=str)}\n\nTraceback:\n{frappe.get_traceback()}"
        )
        raise exc
    finally:
        frappe.set_user(previous_user)


def _build_reason_selection_message(
    context: dict[str, Any],
    reasons: list[str],
    error_prompt: str | None = None,
) -> OutboundMessage:
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        title = "⏱️ *حاضری کی درخواست*"
        body = error_prompt or (
            f"{title}\n\n"
            "مرحلہ 1 تا 4 — *حاضری کی درخواست کی وجہ* منتخب کریں:"
        )
        button_text = "وجہ منتخب کریں"
    elif lang == "Roman Urdu":
        title = "⏱️ *Attendance Request*"
        body = error_prompt or (
            f"{title}\n\n"
            "Step 1 of 4 — Select your *Attendance Request Reason*:"
        )
        button_text = "Select Reason"
    else:
        title = "⏱️ *Attendance Request*"
        body = error_prompt or (
            f"{title}\n\n"
            "Step 1 of 4 — Select your *Attendance Request Reason*:"
        )
        button_text = "Select Reason"

    return build_option_list_message(
        options=reasons,
        header=body,
        button_label=button_text,
        section_title="Reasons",
        id_prefix="att_reason",
    )



def _cancel_flow(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="attendance_leave",
        draft_payload=None,
    )
    lang = context.get("preferred_language", "English")
    msg = (
        "حاضری کی درخواست منسوخ کر دی گئی ہے۔"
        if lang == "Urdu"
        else "Attendance Request cancelled."
    )
    return wrap_with_parent_menu(msg, context, "attendance_leave")


def _parse_user_date(text: str) -> Optional[Any]:
    clean = text.strip()
    if clean.lower() in ("today", "آج"):
        return getdate(today())
    try:
        return getdate(clean)
    except Exception:
        pass
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return getdate(frappe.utils.datetime.datetime.strptime(clean, fmt).strftime("%Y-%m-%d"))
        except Exception:
            pass
    return None


def _get_draft(conv: Any) -> dict[str, Any]:
    if not conv.draft_payload:
        return {}
    try:
        return json.loads(conv.draft_payload)
    except Exception:
        return {}


def _save_draft(conv: Any, draft: dict[str, Any]) -> None:
    update_conversation(conv, draft_payload=json.dumps(draft))
