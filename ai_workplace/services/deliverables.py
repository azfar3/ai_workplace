"""
ai_workplace/services/deliverables.py
──────────────────────────────────────
WhatsApp deliverable workflow for Contract (Deliverable) project staff.

Creates and submits Consultant Deliverable records in mm_bpo.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import add_months, flt, formatdate, getdate, today

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.response_helpers import wrap_with_menu_again
from ai_workplace.whatsapp.interactive import (
    build_deliverable_post_save_buttons,
    build_option_list_message,
    build_yes_no_buttons,
)
from ai_workplace.whatsapp.media import is_allowed_attachment_filename
from ai_workplace.whatsapp.outbound import OutboundMessage

INTENT_ADD = "deliverable_add"
INTENT_SUBMIT = "deliverable_submit"

SUBMIT_TRIGGER_IDS = frozenset({
    "dlv_submit",
    "dlv_submit_now",
    "svc_dlv_submit",
})

SUBMIT_WORKFLOW_ACTION = "Send for Approval"


def is_submit_for_approval_trigger(message_text: str) -> bool:
    """Detect submit-for-approval button clicks and common title/body fallbacks."""
    raw = (message_text or "").strip()
    if not raw:
        return False

    clean = raw.lower()
    if clean in SUBMIT_TRIGGER_IDS or clean in ("submit for approval", "submit"):
        return True
    if clean.startswith(("svc_dlv_submit", "dlv_submit")):
        return True
    if "submit for approv" in clean:
        return True
    if "draft deliverables ready to submit" in clean:
        return True
    if "approval ke liye bhejein" in clean:
        return True
    if "منظوری بھیجیں" in raw or "منظوری کے لیے" in raw:
        return True
    return False


def handle_submit_for_approval_request(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Route submit triggers to post-save submit or the standard draft picker flow."""
    draft = _load_draft(conv)
    if (draft.get("saved_doc") or "").strip():
        return start_submit_saved_deliverable(conv, context)
    return start_submit_deliverable(conv, context)
_DATE_HINT = "e.g. 01-Sep-2026 or 2026-09-01"
_ATTACHMENT_HINT = "PDF, Word, Excel, ZIP, or other document file"
_CANCEL_WORDS = frozenset({"cancel", "menu", "stop", "exit", "back"})
_SKIP_WORDS = frozenset({"skip", "na", "n/a", "-", "none"})


def _is_deliverable_staff(context: dict[str, Any]) -> bool:
    return context.get("staff_category") == "project_deliverable"


def _require_deliverable_staff(context: dict[str, Any]) -> Optional[OutboundMessage]:
    if _is_deliverable_staff(context):
        return None
    return wrap_with_menu_again(
        _("Deliverables are only available for Contract (Deliverable) staff."),
        context,
    )


def start_add_deliverable(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin multi-step deliverable draft creation."""
    denied = _require_deliverable_staff(context)
    if denied:
        return denied

    employee_id = context.get("employee") or conv.employee or ""
    if not employee_id:
        return wrap_with_menu_again(
            _("Deliverables are only available for linked employees."),
            context,
        )

    draft = {
        "step": "awaiting_from_date",
        "employee": employee_id,
        "lines": [],
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=INTENT_ADD,
        active_service="deliverables",
        draft_payload=json.dumps(draft),
    )

    return OutboundMessage(
        body_text=_(
            "📦 *Add Deliverable*\n\n"
            "Step 1 of 5 — Enter the *From Date* for this deliverable period\n"
            "({0}):"
        ).format(_DATE_HINT)
    )


def start_submit_saved_deliverable(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Submit a deliverable that was just saved as draft (post-save action)."""
    denied = _require_deliverable_staff(context)
    if denied:
        return denied

    draft = _load_draft(conv)
    doc_name = (draft.get("saved_doc") or "").strip()
    if not doc_name:
        return wrap_with_menu_again(
            _("No saved deliverable was found. Use *Submit for Approval* from the Deliverables menu."),
            context,
        )

    return _begin_submit_confirm(conv, context, doc_name)


def start_submit_deliverable(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin flow to submit an existing draft for supervisor approval."""
    denied = _require_deliverable_staff(context)
    if denied:
        return denied

    employee_id = context.get("employee") or conv.employee or ""
    if not employee_id:
        return wrap_with_menu_again(
            _("Deliverables are only available for linked employees."),
            context,
        )

    drafts = _list_draft_deliverables(employee_id)
    if not drafts:
        return wrap_with_menu_again(
            _(
                "You have no draft deliverables to submit.\n\n"
                "Use *Add Deliverable* to create one first."
            ),
            context,
        )

    if len(drafts) == 1:
        return _begin_submit_confirm(conv, context, drafts[0]["name"])

    draft = {
        "step": "awaiting_pick_draft",
        "employee": employee_id,
        "draft_options": drafts,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=INTENT_SUBMIT,
        active_service="deliverables",
        draft_payload=json.dumps(draft),
    )

    return _build_draft_pick_outbound(drafts)


def build_deliverable_status_outbound(context: dict[str, Any]) -> OutboundMessage:
    """List deliverables and offer submit action when draft records exist."""
    text = build_deliverable_status_response(context)
    msg = OutboundMessage(body_text=text)

    employee_id = context.get("employee") or ""
    if employee_id and _list_draft_deliverables(employee_id):
        msg.follow_up = [_build_submit_from_status_button(context)]
    return msg


def _build_submit_from_status_button(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = "ڈرافٹ ڈیلیوریبلز منظوری کے لیے بھیجیں:"
        title = "📤 منظوری بھیجیں"
    elif lang == "Roman Urdu":
        body = "Draft deliverables ko approval ke liye bhejein:"
        title = "📤 Submit for Approval"
    else:
        body = "You have draft deliverables ready to submit:"
        title = "📤 Submit for Approval"

    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [{
                "type": "reply",
                "reply": {"id": "dlv_submit", "title": _truncate_button_title(title)},
            }],
        },
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def _truncate_button_title(title: str, limit: int = 20) -> str:
    title = (title or "").strip()
    if len(title) <= limit:
        return title
    return title[: limit - 1] + "…"


def build_deliverable_status_response(context: dict[str, Any]) -> str:
    """List recent Consultant Deliverable records for the employee."""
    denied = _require_deliverable_staff(context)
    if denied:
        return denied.body_text or str(denied)

    employee_id = context.get("employee") or ""
    if not employee_id:
        return _("Deliverables are only available for linked employees.")

    records = frappe.get_all(
        "Consultant Deliverable",
        filters={"employee": employee_id, "docstatus": ["!=", 2]},
        fields=["name", "from_date", "to_date", "total_amount", "workflow_state", "status", "modified"],
        order_by="modified desc",
        limit=10,
    )
    if not records:
        return _(
            "📋 *My Deliverables*\n\n"
            "No deliverable records found.\n\n"
            "Use *Add Deliverable* to create your first entry."
        )

    lines = [_("📋 *My Deliverables*\n")]
    for idx, row in enumerate(records, start=1):
        from_date = row.get("from_date")
        to_date = row.get("to_date")
        period = "{0} — {1}".format(
            formatdate(from_date, "dd MMM YYYY") if from_date else "—",
            formatdate(to_date, "dd MMM YYYY") if to_date else "—",
        )
        state = row.get("workflow_state") or row.get("status") or _("Draft")
        amount = flt(row.get("total_amount"))
        lines.append(
            _(
                "{idx}. *{name}*\n"
                "   Period: {period}\n"
                "   Amount: {amount:,.2f}\n"
                "   Status: {state}"
            ).format(
                idx=idx,
                name=row.get("name"),
                period=period,
                amount=amount,
                state=state,
            )
        )
    return "\n\n".join(lines)


def handle_deliverable_add_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> OutboundMessage:
    """Process one step of the add-deliverable flow."""
    draft = _load_draft(conv)
    step = draft.get("step", "")
    text = (message_text or "").strip()
    clean = text.lower()

    if clean in _CANCEL_WORDS:
        return _cancel_flow(conv, context)

    if step == "awaiting_from_date":
        return _handle_from_date(conv, context, draft, text)
    if step == "awaiting_to_date":
        return _handle_to_date(conv, context, draft, text)
    if step == "awaiting_line_description":
        return _handle_line_description(conv, context, draft, text)
    if step == "awaiting_line_amount":
        return _handle_line_amount(conv, context, draft, text)
    if step == "awaiting_line_attachment":
        return _prompt_line_attachment(context, draft)
    if step == "awaiting_more_lines":
        return _handle_more_lines(conv, context, draft, text)
    if step == "awaiting_remarks":
        return _handle_remarks(conv, context, draft, text)
    if step == "awaiting_confirm":
        return _handle_add_confirm(conv, context, draft, text)

    return wrap_with_menu_again(_("Something went wrong. Type 'menu' to start again."), context)


def handle_deliverable_add_attachment(
    conv: Any,
    context: dict[str, Any],
    file_url: str,
    filename: str = "",
) -> OutboundMessage:
    """Process an uploaded file for the current deliverable line item."""
    draft = _load_draft(conv)
    step = draft.get("step", "")

    if step != "awaiting_line_attachment":
        return OutboundMessage(
            body_text=_(
                "File received, but no deliverable line is waiting for an attachment.\n\n"
                "Type *menu* to return to the main menu."
            )
        )

    clean_url = (file_url or "").strip()
    if not clean_url:
        return _prompt_line_attachment(context, draft)

    display_name = (filename or clean_url.split("/")[-1] or "attachment").strip()
    if not is_allowed_attachment_filename(display_name):
        return OutboundMessage(
            body_text=_(
                "Unsupported file type for *{0}*.\n\n"
                "Please send a supported attachment ({1})."
            ).format(display_name, _ATTACHMENT_HINT)
        )

    pending = draft.get("pending_line") or {}
    pending["attachment"] = clean_url
    pending["attachment_filename"] = display_name
    lines = draft.get("lines") or []
    lines.append(pending)
    draft["lines"] = lines
    draft.pop("pending_line", None)
    draft["step"] = "awaiting_more_lines"
    _save_draft(conv, draft)

    total = sum(flt(line.get("amount")) for line in lines)
    return build_yes_no_buttons(
        _(
            "Attachment saved for *{0}*.\n"
            "Line total so far: *{1:,.2f}*\n\n"
            "Add another deliverable line?"
        ).format(display_name, total),
        yes_id="dlv_more_yes",
        no_id="dlv_more_no",
        yes_label=_("Add Another"),
        no_label=_("Continue"),
    )


def is_awaiting_deliverable_attachment(conv: Any) -> bool:
    """True when conversation is waiting for a line-item file upload."""
    if getattr(conv, "current_intent", None) != INTENT_ADD:
        return False
    draft = _load_draft(conv)
    return draft.get("step") == "awaiting_line_attachment"


def handle_deliverable_submit_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> OutboundMessage:
    """Process one step of the submit-for-approval flow."""
    draft = _load_draft(conv)
    step = draft.get("step", "")
    text = (message_text or "").strip()
    clean = text.lower()

    if clean in _CANCEL_WORDS:
        return _cancel_flow(conv, context)

    if step == "awaiting_pick_draft":
        return _handle_pick_draft(conv, context, draft, text)
    if step == "awaiting_submit_confirm":
        return _handle_submit_confirm(conv, context, draft, text)

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
        active_service="deliverables",
        draft_payload=None,
    )
    return wrap_with_menu_again(_("Deliverable flow cancelled."), context)


def _parse_date(text: str):
    raw = (text or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return getdate(datetime.strptime(raw, fmt).date())
        except ValueError:
            continue
    try:
        return getdate(raw)
    except Exception:
        return None


def _handle_from_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    parsed = _parse_date(text)
    if not parsed:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter From Date ({0}):").format(_DATE_HINT)
        )
    draft["from_date"] = str(parsed)
    draft["step"] = "awaiting_to_date"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "Step 2 of 5 — Enter the *To Date* for this period\n"
            "({0}):"
        ).format(_DATE_HINT)
    )


def _handle_to_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    parsed = _parse_date(text)
    if not parsed:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter To Date ({0}):").format(_DATE_HINT)
        )
    if getdate(parsed) < getdate(draft.get("from_date")):
        return OutboundMessage(body_text=_("To Date cannot be before From Date. Please re-enter To Date:"))

    draft["to_date"] = str(parsed)
    draft["step"] = "awaiting_line_description"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "Step 3 of 5 — Enter the *Deliverable description*\n"
            "(what was completed in this period):"
        )
    )


def _handle_line_description(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    desc = (text or "").strip()
    if len(desc) < 3:
        return OutboundMessage(body_text=_("Please enter a description (at least 3 characters)."))
    draft["pending_line"] = {"deliverable": desc}
    draft["step"] = "awaiting_line_amount"
    _save_draft(conv, draft)
    return OutboundMessage(body_text=_("Enter the *Amount* for this deliverable (numbers only):"))


def _handle_line_amount(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    raw = (text or "").strip().replace(",", "")
    if not re.match(r"^\d+(\.\d{1,2})?$", raw):
        return OutboundMessage(body_text=_("Please enter a valid amount (e.g. 50000 or 50000.00):"))

    pending = draft.get("pending_line") or {}
    pending["amount"] = flt(raw)
    draft["pending_line"] = pending
    draft["step"] = "awaiting_line_attachment"
    _save_draft(conv, draft)
    return _prompt_line_attachment(context, draft, line_label=pending.get("deliverable"))


def _prompt_line_attachment(
    context: dict[str, Any],
    draft: dict[str, Any],
    line_label: str = "",
) -> OutboundMessage:
    label = (line_label or (draft.get("pending_line") or {}).get("deliverable") or "").strip()
    label_line = _(" for *{0}*").format(label) if label else ""
    return OutboundMessage(
        body_text=_(
            "Step 4 of 5 — Send the supporting *attachment*{label_line}.\n\n"
            "Accepted formats: {formats}\n\n"
            "Use WhatsApp's attachment button to send the file."
        ).format(label_line=label_line, formats=_ATTACHMENT_HINT)
    )


def _handle_more_lines(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("dlv_more_yes", "yes", "add another", "add"):
        draft["step"] = "awaiting_line_description"
        _save_draft(conv, draft)
        return OutboundMessage(body_text=_("Enter the *Deliverable description* for the next line:"))

    draft["step"] = "awaiting_remarks"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "Step 5 of 5 — Add optional *Remarks*\n"
            "(or type 'skip'):"
        )
    )


def _handle_remarks(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean not in _SKIP_WORDS:
        draft["remarks"] = text.strip()
    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)

    summary = _build_add_summary(draft)
    return build_yes_no_buttons(
        summary + "\n\n" + _("Save this deliverable as Draft?"),
        yes_id="dlv_save",
        no_id="dlv_cancel",
        yes_label=_("Save Draft"),
        no_label=_("Cancel"),
    )


def _build_add_summary(draft: dict[str, Any]) -> str:
    lines = draft.get("lines") or []
    total = sum(flt(line.get("amount")) for line in lines)
    line_text = "\n".join(
        _("  • {desc}: {amount:,.2f}{attachment}").format(
            desc=line.get("deliverable"),
            amount=flt(line.get("amount")),
            attachment=(
                _(" (📎 {0})").format(line.get("attachment_filename") or "attached")
                if line.get("attachment")
                else ""
            ),
        )
        for line in lines
    )
    return _(
        "📋 *Deliverable Summary*\n\n"
        "• *From:* {from_date}\n"
        "• *To:* {to_date}\n"
        "• *Lines:*\n{line_text}\n"
        "• *Total:* {total:,.2f}"
    ).format(
        from_date=formatdate(draft.get("from_date"), "dd MMM YYYY"),
        to_date=formatdate(draft.get("to_date"), "dd MMM YYYY"),
        line_text=line_text or _("  (none)"),
        total=total,
    )


def _handle_add_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("dlv_cancel", "no", "cancel"):
        return _cancel_flow(conv, context)

    if clean not in ("dlv_save", "yes", "save", "confirm"):
        summary = _build_add_summary(draft)
        return build_yes_no_buttons(
            summary + "\n\n" + _("Save this deliverable as Draft?"),
            yes_id="dlv_save",
            no_id="dlv_cancel",
            yes_label=_("Save Draft"),
            no_label=_("Cancel"),
        )

    try:
        doc_name = _create_consultant_deliverable(draft, context)
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Deliverable create failed: {exc}")
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="deliverables",
            draft_payload=None,
        )
        return wrap_with_menu_again(
            _("Could not save deliverable:\n\n{0}").format(str(exc)),
            context,
        )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="deliverables",
        draft_payload=json.dumps({"saved_doc": doc_name}),
    )
    body = _(
        "✅ *Deliverable Saved*\n\n"
        "Reference: *{0}*\n"
        "Status: *Draft*\n\n"
        "Tap *Submit for Approval* below when you are ready to send it to your supervisor."
    ).format(doc_name)
    return build_deliverable_post_save_buttons(body)


def _get_deliverable_summary_row(doc_name: str, employee_id: str) -> Optional[dict[str, Any]]:
    if not doc_name or not employee_id:
        return None
    row = frappe.db.get_value(
        "Consultant Deliverable",
        doc_name,
        ["name", "employee", "from_date", "to_date", "total_amount", "workflow_state", "docstatus"],
        as_dict=True,
    )
    if not row or row.get("employee") != employee_id:
        return None
    return row


def _begin_submit_confirm(conv: Any, context: dict[str, Any], doc_name: str) -> OutboundMessage:
    employee_id = context.get("employee") or conv.employee or ""
    picked = _get_deliverable_summary_row(doc_name, employee_id)
    if not picked:
        return wrap_with_menu_again(
            _("Deliverable *{0}* was not found or cannot be submitted.").format(doc_name),
            context,
        )
    if picked.get("docstatus") == 1:
        return wrap_with_menu_again(
            _("Deliverable *{0}* has already been submitted.").format(doc_name),
            context,
        )

    draft = {
        "step": "awaiting_submit_confirm",
        "employee": employee_id,
        "selected_doc": doc_name,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=INTENT_SUBMIT,
        active_service="deliverables",
        draft_payload=json.dumps(draft),
    )
    return _build_submit_confirm_prompt(picked)


def _build_submit_confirm_prompt(picked: dict[str, Any]) -> OutboundMessage:
    summary = _(
        "📤 *Submit for Approval*\n\n"
        "• *Reference:* {name}\n"
        "• *Period:* {from_date} — {to_date}\n"
        "• *Amount:* {amount:,.2f}\n\n"
        "Send this deliverable to your supervisor?"
    ).format(
        name=picked.get("name"),
        from_date=formatdate(picked.get("from_date"), "dd MMM YYYY"),
        to_date=formatdate(picked.get("to_date"), "dd MMM YYYY"),
        amount=flt(picked.get("total_amount")),
    )
    return build_yes_no_buttons(
        summary,
        yes_id="dlv_submit_yes",
        no_id="dlv_submit_no",
        yes_label=_("Submit"),
        no_label=_("Cancel"),
    )


def _handle_pick_draft(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    options = draft.get("draft_options") or []
    picked = _resolve_pick(text, options)
    if not picked:
        return OutboundMessage(
            body_text=_("Invalid selection. Reply with the number from the list, or type 'menu' to cancel.\n\n")
            + _build_draft_pick_list(options)
        )

    draft["selected_doc"] = picked["name"]
    draft["step"] = "awaiting_submit_confirm"
    _save_draft(conv, draft)
    return _build_submit_confirm_prompt(picked)


def _handle_submit_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("dlv_submit_no", "no", "cancel"):
        doc_name = (draft.get("selected_doc") or "").strip()
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="deliverables",
            draft_payload=json.dumps({"saved_doc": doc_name}) if doc_name else None,
        )
        if doc_name:
            body = _(
                "Submission cancelled.\n\n"
                "Reference: *{0}* is still saved as *Draft*.\n\n"
                "Tap *Submit for Approval* when you are ready."
            ).format(doc_name)
            return build_deliverable_post_save_buttons(body)
        return wrap_with_menu_again(_("Deliverable submission cancelled."), context)

    if clean not in ("dlv_submit_yes", "yes", "submit", "confirm"):
        return OutboundMessage(body_text=_("Please confirm using the buttons or reply Submit / Cancel."))

    doc_name = draft.get("selected_doc")
    if not doc_name:
        return _cancel_flow(conv, context)

    try:
        _submit_deliverable_for_approval(doc_name, context)
    except Exception as exc:
        error_detail = _format_submit_error(exc)
        frappe.logger("ai_workplace").error(
            f"Deliverable submit failed ({doc_name}): {error_detail}\n{frappe.get_traceback()}"
        )
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="deliverables",
            draft_payload=None,
        )
        return wrap_with_menu_again(
            _("Could not submit deliverable:\n\n{0}").format(error_detail),
            context,
        )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="deliverables",
        draft_payload=None,
    )
    return wrap_with_menu_again(
        _(
            "✅ *Submitted for Approval*\n\n"
            "Reference: *{0}*\n"
            "Status: *Sent For Approval*\n\n"
            "Your supervisor will review this deliverable."
        ).format(doc_name),
        context,
    )


def _is_draft_deliverable(row: dict[str, Any]) -> bool:
    if row.get("docstatus") not in (0, None):
        return False
    state = (row.get("workflow_state") or row.get("status") or "Draft").strip()
    return state in ("Draft", "")


def _list_draft_deliverables(employee_id: str) -> list[dict[str, Any]]:
    since = add_months(today(), -3)
    records = frappe.get_all(
        "Consultant Deliverable",
        filters={
            "employee": employee_id,
            "docstatus": 0,
            "modified": [">=", since],
        },
        fields=["name", "from_date", "to_date", "total_amount", "workflow_state", "status", "docstatus"],
        order_by="modified desc",
        limit=20,
    )
    return [row for row in records if _is_draft_deliverable(row)][:10]


def _build_draft_pick_outbound(drafts: list[dict[str, Any]]) -> OutboundMessage:
    header = _build_draft_pick_list(drafts)
    options = []
    for idx, row in enumerate(drafts):
        period = "{0} — {1}".format(
            formatdate(row.get("from_date"), "dd MMM YYYY") if row.get("from_date") else "—",
            formatdate(row.get("to_date"), "dd MMM YYYY") if row.get("to_date") else "—",
        )
        options.append({
            "label": f"{row.get('name')} ({period})",
            "idx": idx,
        })

    if len(options) <= 10:
        rows = []
        for item in options:
            row = drafts[item["idx"]]
            rows.append({
                "id": f"dlv_pick_{item['idx']}",
                "title": _truncate_button_title(row.get("name") or "Deliverable", 24),
                "description": _truncate_button_title(
                    "{0} | {1:,.2f}".format(
                        formatdate(row.get("from_date"), "dd MMM YYYY") if row.get("from_date") else "—",
                        flt(row.get("total_amount")),
                    ),
                    72,
                ),
            })
        interactive = {
            "type": "list",
            "body": {"text": header},
            "action": {
                "button": _truncate_button_title("Select Draft", 20),
                "sections": [{"title": "Draft Deliverables", "rows": rows}],
            },
        }
        return OutboundMessage(body_text=header, interactive=interactive)

    return OutboundMessage(body_text=header)


def _build_draft_pick_list(options: list[dict[str, Any]]) -> str:
    lines = [_("📤 *Submit for Approval*\n\nSelect a draft deliverable by number:\n")]
    for idx, row in enumerate(options, start=1):
        period = "{0} — {1}".format(
            formatdate(row.get("from_date"), "dd MMM YYYY") if row.get("from_date") else "—",
            formatdate(row.get("to_date"), "dd MMM YYYY") if row.get("to_date") else "—",
        )
        lines.append(
            _(
                "{idx}. *{name}*\n"
                "   {period} | {amount:,.2f}"
            ).format(
                idx=idx,
                name=row["name"],
                period=period,
                amount=flt(row.get("total_amount")),
            )
        )
    return "\n\n".join(lines)


def _resolve_pick(text: str, options: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    clean = (text or "").strip()
    clean_lower = clean.lower()

    if clean_lower.startswith("dlv_pick_"):
        try:
            pick_idx = int(clean_lower.split("_")[-1])
            if 0 <= pick_idx < len(options):
                return options[pick_idx]
        except ValueError:
            pass

    if clean.isdigit():
        idx = int(clean)
        if 1 <= idx <= len(options):
            return options[idx - 1]

    for row in options:
        if clean == row.get("name") or clean_lower == (row.get("name") or "").lower():
            return row
    return None


def _create_consultant_deliverable(draft: dict[str, Any], context: dict[str, Any]) -> str:
    employee_id = draft.get("employee") or context.get("employee")
    if not employee_id:
        frappe.throw(_("Employee not found."))

    lines = draft.get("lines") or []
    if not lines:
        frappe.throw(_("Please add at least one deliverable line."))
    missing = [line for line in lines if not line.get("attachment")]
    if missing:
        frappe.throw(_("Each deliverable line must include an attachment."))

    erp_user = context.get("user") or ""
    previous_user = frappe.session.user
    try:
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)

        employee = frappe.get_cached_doc("Employee", employee_id)
        doc = frappe.new_doc("Consultant Deliverable")
        doc.employee = employee_id
        doc.from_date = draft.get("from_date")
        doc.to_date = draft.get("to_date")
        if draft.get("remarks"):
            doc.remarks = draft.get("remarks")
        if getattr(employee, "company", None):
            doc.company = employee.company
        for line in lines:
            doc.append(
                "deliverables",
                {
                    "deliverable": line.get("deliverable"),
                    "amount": flt(line.get("amount")),
                },
            )
            if line.get("attachment"):
                doc.append(
                    "attachments",
                    {
                        "title": line.get("deliverable"),
                        "attachment": line.get("attachment"),
                        "remarks": line.get("attachment_filename") or line.get("deliverable"),
                    },
                )
        doc.workflow_state = "Draft"
        doc.status = "Draft"
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    finally:
        frappe.set_user(previous_user)


def _format_submit_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__ or _("Unknown error")


def _resolve_submit_workflow_action(doc: Any) -> str:
    from frappe.model.workflow import get_transitions

    transitions = get_transitions(doc)
    preferred = ""
    fallback = ""
    for transition in transitions:
        action = (transition.get("action") or "").strip()
        if not action:
            continue
        if action == SUBMIT_WORKFLOW_ACTION:
            return action
        if "approval" in action.lower() and not fallback:
            fallback = action
    return fallback or preferred


def _submit_deliverable_for_approval(doc_name: str, context: dict[str, Any]) -> None:
    employee_id = context.get("employee") or ""
    previous_user = frappe.session.user
    try:
        doc = frappe.get_doc("Consultant Deliverable", doc_name)
        if doc.employee != employee_id:
            frappe.throw(_("You can only submit your own deliverables."))
        if doc.docstatus == 1:
            frappe.throw(_("This deliverable has already been submitted."))
        current_state = (doc.workflow_state or doc.status or "Draft").strip()
        if current_state not in ("Draft", ""):
            frappe.throw(_("This deliverable is not in Draft status."))
        if not doc.deliverables:
            frappe.throw(_("Please add deliverable lines before submitting."))

        # Workflow checks doc read permission; apply as Administrator after ownership checks.
        frappe.set_user("Administrator")
        doc.reload()

        from frappe.model.workflow import apply_workflow

        action = _resolve_submit_workflow_action(doc)
        if not action:
            frappe.throw(_("No submit action is available for this deliverable."))

        apply_workflow(doc, action)
        frappe.db.commit()
    finally:
        frappe.set_user(previous_user)
