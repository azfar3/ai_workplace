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
    employee_id = context.get("employee") or conv.employee or ""
    if not employee_id:
        return wrap_with_menu_again(
            _("Leave application is only available for linked employees."),
            context,
        )

    leave_types = get_leave_balance_data(employee_id)
    if not leave_types:
        return wrap_with_menu_again(
            _(
                "No active leave allocation was found for your account.\n\n"
                "Please contact HR if you believe this is incorrect."
            ),
            context,
        )

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

    header = _(
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

    return wrap_with_menu_again(_("Something went wrong. Type 'menu' to start again."), context)


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
    return wrap_with_menu_again(_("Leave application cancelled."), context)


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
    if not leave_type:
        return OutboundMessage(
            body_text=_("Please select a leave type from the list, or type 'menu' to cancel.")
        )

    draft["leave_type"] = leave_type
    draft["step"] = "awaiting_from_date"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ Leave Type: *{0}*\n\n"
            "Step 2 of 4 — Enter *From Date*\n"
            "Format: {1}"
        ).format(leave_type, _DATE_HINT)
    )


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
    if not from_date:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter From Date as {0}.").format(_DATE_HINT)
        )

    draft["from_date"] = str(from_date)
    draft["step"] = "awaiting_to_date"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ From Date: *{0}*\n\n"
            "Step 3 of 4 — Enter *To Date*\n"
            "Format: {1}"
        ).format(formatdate(from_date, "dd MMM YYYY"), _DATE_HINT)
    )


def _handle_to_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    to_date = _parse_user_date(text)
    if not to_date:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter To Date as {0}.").format(_DATE_HINT)
        )

    from_date = getdate(draft.get("from_date"))
    if to_date < from_date:
        return OutboundMessage(body_text=_("To Date cannot be before From Date. Please try again."))

    draft["to_date"] = str(to_date)
    draft["step"] = "awaiting_half_day"
    _save_draft(conv, draft)

    prompt = _(
        "✅ To Date: *{0}*\n\n"
        "Is this a *Half Day* leave?"
    ).format(formatdate(to_date, "dd MMM YYYY"))
    return build_yes_no_buttons(prompt, yes_id="leave_half_yes", no_id="leave_half_no")


def _handle_half_day(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    is_half = clean in ("leave_half_yes", "yes", "y", "ha", "haan")
    is_full = clean in ("leave_half_no", "no", "n", "nahi", "na")

    if not is_half and not is_full:
        prompt = _("Please tap *Yes* or *No* for half-day leave.")
        return build_yes_no_buttons(prompt, yes_id="leave_half_yes", no_id="leave_half_no")

    draft["half_day"] = 1 if is_half else 0
    if is_half:
        from_date = getdate(draft.get("from_date"))
        to_date = getdate(draft.get("to_date"))
        draft["half_day_date"] = str(from_date if from_date == to_date else from_date)

    draft["step"] = "awaiting_reason"
    _save_draft(conv, draft)

    return OutboundMessage(
        body_text=_(
            "Step 4 of 4 — Please enter the *Reason* for your leave\n"
            "(brief description):"
        )
    )


def _handle_reason(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    reason = (text or "").strip()
    if len(reason) < 3:
        return OutboundMessage(body_text=_("Please enter a reason (at least 3 characters)."))

    draft["description"] = reason
    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)

    summary = _build_summary(draft)
    return build_yes_no_buttons(
        summary + "\n\n" + _("Submit this leave application?"),
        yes_id="leave_submit",
        no_id="leave_cancel",
        yes_label=_("Submit"),
        no_label=_("Cancel"),
    )


def _build_summary(draft: dict[str, Any]) -> str:
    from_date = formatdate(draft.get("from_date"), "dd MMM YYYY")
    to_date = formatdate(draft.get("to_date"), "dd MMM YYYY")
    half = _("Yes") if draft.get("half_day") else _("No")
    return _(
        "📋 *Leave Application Summary*\n\n"
        "• *Leave Type:* {leave_type}\n"
        "• *From:* {from_date}\n"
        "• *To:* {to_date}\n"
        "• *Half Day:* {half}\n"
        "• *Reason:* {reason}"
    ).format(
        leave_type=draft.get("leave_type"),
        from_date=from_date,
        to_date=to_date,
        half=half,
        reason=draft.get("description"),
    )


def _handle_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("leave_cancel", "no", "cancel"):
        return _cancel_flow(conv, context)

    if clean not in ("leave_submit", "yes", "submit", "confirm"):
        summary = _build_summary(draft)
        return build_yes_no_buttons(
            summary + "\n\n" + _("Submit this leave application?"),
            yes_id="leave_submit",
            no_id="leave_cancel",
            yes_label=_("Submit"),
            no_label=_("Cancel"),
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
        return wrap_with_menu_again(
            _("Could not submit leave application:\n\n{0}").format(str(exc)),
            context,
        )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="attendance_leave",
        draft_payload=None,
    )
    return wrap_with_menu_again(
        _(
            "✅ *Leave Application Submitted*\n\n"
            "Reference: *{0}*\n"
            "Status: *Open* (pending approver review)\n\n"
            "Your supervisor will be notified."
        ).format(doc_name),
        context,
    )


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
