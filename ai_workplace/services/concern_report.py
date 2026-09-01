"""
ai_workplace/services/concern_report.py
────────────────────────────────────────
Step-by-step WhatsApp wrongdoing / grievance report workflow.

Mirrors the public web form at /report-wrongdoing/new (Employee Grievance).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.response_helpers import wrap_with_menu_again
from ai_workplace.whatsapp.interactive import (
    build_grievance_type_list_message,
    build_option_list_message,
    build_yes_no_buttons,
)
from ai_workplace.whatsapp.outbound import OutboundMessage

CONCERN_MENU_KEYS = frozenset({"concerns", "guest_concern", "former_concern"})
INTENT_KEY = "concern_report"
_DATE_HINT = "e.g. 01-Sep-2026 or 2026-09-01"
_CANCEL_WORDS = frozenset({"cancel", "menu", "stop", "exit", "back"})
_SKIP_WORDS = frozenset({"skip", "na", "n/a", "-", "none"})
_FAKE_CNICS = frozenset(
    f"{d * 13}" for d in range(10)
)


def start_concern_report(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin confidential concern report — incident type first."""
    grievance_types = _get_grievance_types()
    if not grievance_types:
        return wrap_with_menu_again(
            _("Concern reporting is temporarily unavailable. Please contact HR."),
            context,
        )

    employee_id = context.get("employee") or conv.employee or ""
    is_guest = not bool(employee_id)

    draft = {
        "step": "awaiting_incident_type",
        "employee": employee_id or None,
        "is_guest": is_guest,
        "grievance_types": grievance_types,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=INTENT_KEY,
        active_service="concerns",
        draft_payload=json.dumps(draft),
    )

    header = _(
        "🛡️ *Report a Concern*\n\n"
        "Submit confidential reports on grievances, harassment, fraud, or safety issues.\n\n"
        "All reports are handled confidentially under MicroMerger's Zero Tolerance policy.\n\n"
        "Step 1 — Select *Incident Type*:"
    )
    if len(grievance_types) <= 3:
        return _build_incident_type_buttons(header, grievance_types)
    return build_grievance_type_list_message(grievance_types, header)


def handle_concern_report_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> OutboundMessage:
    """Process one step of the concern report flow."""
    draft = _load_draft(conv)
    step = draft.get("step", "")
    text = (message_text or "").strip()
    clean = text.lower()

    if clean in _CANCEL_WORDS:
        return _cancel_flow(conv, context)

    handlers = {
        "awaiting_incident_type": _handle_incident_type,
        "awaiting_full_name": _handle_full_name,
        "awaiting_email": _handle_email,
        "awaiting_cnic": _handle_cnic,
        "awaiting_mobile": _handle_mobile,
        "awaiting_address": _handle_address,
        "awaiting_province": _handle_province,
        "awaiting_district": _handle_district,
        "awaiting_incident_date": _handle_incident_date,
        "awaiting_person_involved": _handle_person_involved,
        "awaiting_designation": _handle_designation,
        "awaiting_location": _handle_location,
        "awaiting_other_type": _handle_other_type,
        "awaiting_description": _handle_description,
        "awaiting_witnesses": _handle_witnesses,
        "awaiting_witness_detail": _handle_witness_detail,
        "awaiting_reported_before": _handle_reported_before,
        "awaiting_reported_detail": _handle_reported_detail,
        "awaiting_anonymous": _handle_anonymous,
        "awaiting_confirm": _handle_confirm,
    }
    handler = handlers.get(step)
    if handler:
        return handler(conv, context, draft, text)

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
        active_service="concerns",
        draft_payload=None,
    )
    return wrap_with_menu_again(_("Concern report cancelled."), context)


def _get_grievance_types() -> list[str]:
    rows = frappe.get_all("Grievance Type", pluck="name", order_by="name asc")
    return list(rows or [])


def _get_provinces() -> list[dict[str, str]]:
    rows = frappe.get_all(
        "Province",
        fields=["name", "province_name"],
        order_by="province_name asc",
    )
    return [
        {"id": row["name"], "label": row.get("province_name") or row["name"]}
        for row in rows
    ]


def _get_districts(province_id: str) -> list[str]:
    from hrms.hr.doctype.employee_grievance.employee_grievance import get_districts

    rows = get_districts(province_id) or []
    return [row[0] for row in rows if row and row[0]]


def _build_incident_type_buttons(header: str, grievance_types: list[str]) -> OutboundMessage:
    buttons = []
    for idx, gt in enumerate(grievance_types[:3]):
        buttons.append({
            "type": "reply",
            "reply": {"id": f"gt_{idx}", "title": gt[:20]},
        })
    interactive = {
        "type": "button",
        "body": {"text": header},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def _resolve_indexed_choice(
    options: list[Any],
    text: str,
    prefix: str,
    *,
    label_key: str | None = None,
) -> Optional[Any]:
    clean = text.strip().lower()
    if clean.startswith(f"{prefix}_") and clean[len(prefix) + 1 :].isdigit():
        idx = int(clean[len(prefix) + 1 :])
        if 0 <= idx < len(options):
            item = options[idx]
            return item.get(label_key) if label_key and isinstance(item, dict) else item

    for item in options:
        label = (item.get(label_key) if label_key and isinstance(item, dict) else item) or ""
        label_lower = str(label).lower()
        if clean == label_lower or clean in label_lower or label_lower in clean:
            return label if label_key else item
    return None


def _resolve_incident_type(draft: dict[str, Any], text: str) -> Optional[str]:
    return _resolve_indexed_choice(draft.get("grievance_types") or [], text, "gt")


def _next_step_after_incident_type(draft: dict[str, Any]) -> str:
    return "awaiting_full_name" if draft.get("is_guest") else "awaiting_incident_date"


def _handle_incident_type(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    incident_type = _resolve_incident_type(draft, text)
    if not incident_type:
        return OutboundMessage(
            body_text=_("Please select an incident type from the list, or type 'menu' to cancel.")
        )

    draft["grievance_type"] = incident_type
    draft["step"] = _next_step_after_incident_type(draft)
    _save_draft(conv, draft)

    if draft.get("is_guest"):
        return OutboundMessage(
            body_text=_(
                "✅ Incident Type: *{0}*\n\n"
                "Step 2 — Enter your *Full Name*\n"
                "(letters and spaces only, min 3 characters):"
            ).format(incident_type)
        )

    return OutboundMessage(
        body_text=_(
            "✅ Incident Type: *{0}*\n\n"
            "Step 2 — Enter *Incident Date*\n"
            "Format: {1}\n"
            "(cannot be in the future)"
        ).format(incident_type, _DATE_HINT)
    )


def _handle_full_name(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    name = (text or "").strip()
    if len(name) < 3 or not re.match(r"^[A-Za-z\s]+$", name):
        return OutboundMessage(
            body_text=_("Please enter a valid full name (letters and spaces only, min 3 characters).")
        )

    draft["employee_name"] = name
    draft["step"] = "awaiting_email"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_("✅ Full Name: *{0}*\n\nStep 3 — Enter your *Email*:").format(name)
    )


def _handle_email(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    email = (text or "").strip()
    if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
        return OutboundMessage(body_text=_("Please enter a valid email address."))

    draft["custom_email"] = email
    draft["step"] = "awaiting_cnic"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ Email saved.\n\n"
            "Step 4 — Enter your *CNIC* (13 digits, no dashes)\n"
            "e.g. 1234567890123"
        )
    )


def _handle_cnic(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    cnic = (text or "").strip()
    if re.match(r"^\d{13}$", cnic):
        if cnic in _FAKE_CNICS:
            return OutboundMessage(body_text=_("Please enter a valid CNIC."))
    elif not re.match(r"^[A-Za-z]{2}\d{11}$", cnic):
        return OutboundMessage(
            body_text=_(
                "Please enter a valid CNIC (13 digits) or Afghan Citizen Number (e.g. AB12345678901)."
            )
        )

    draft["custom_cnic"] = cnic
    draft["step"] = "awaiting_mobile"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ CNIC saved.\n\n"
            "Step 5 — Enter your *Mobile No.* (11 digits, starts with 03)\n"
            "e.g. 03001234567"
        )
    )


def _handle_mobile(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    mobile = (text or "").strip()
    if not re.match(r"^03\d{9}$", mobile):
        return OutboundMessage(
            body_text=_("Mobile number must be 11 digits and start with '03' (e.g. 03001234567).")
        )

    draft["custom_mobile_no"] = mobile
    draft["step"] = "awaiting_address"
    _save_draft(conv, draft)
    return OutboundMessage(body_text=_("✅ Mobile saved.\n\nStep 6 — Enter your *Address*:"))


def _handle_address(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    address = (text or "").strip()
    if len(address) < 5:
        return OutboundMessage(body_text=_("Please enter a valid address (at least 5 characters)."))

    draft["custom_address"] = address
    provinces = _get_provinces()
    draft["provinces"] = provinces
    draft["step"] = "awaiting_province"
    _save_draft(conv, draft)

    header = _("✅ Address saved.\n\nStep 7 — Select your *Province*:")
    return build_option_list_message(
        provinces,
        header,
        button_label=_("Select Province"),
        section_title=_("Provinces"),
        id_prefix="prov",
        label_key="label",
    )


def _handle_province(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    provinces = draft.get("provinces") or _get_provinces()
    province = _resolve_indexed_choice(provinces, text, "prov", label_key="label")
    if not province:
        header = _("Please select your province from the list:")
        return build_option_list_message(
            provinces,
            header,
            button_label=_("Select Province"),
            section_title=_("Provinces"),
            id_prefix="prov",
            label_key="label",
        )

    province_id = None
    for row in provinces:
        if row.get("label") == province:
            province_id = row.get("id")
            break

    districts = _get_districts(province_id or province)
    if not districts:
        return OutboundMessage(
            body_text=_("Could not load districts for the selected province. Please try again or type 'menu'.")
        )

    draft["custom_province"] = province_id or province
    draft["districts"] = districts
    draft["step"] = "awaiting_district"
    _save_draft(conv, draft)

    header = _("✅ Province: *{0}*\n\nStep 8 — Select your *District*:").format(province)
    district_rows = [{"label": d} for d in districts]
    return build_option_list_message(
        district_rows,
        header,
        button_label=_("Select District"),
        section_title=_("Districts"),
        id_prefix="dist",
        label_key="label",
    )


def _handle_district(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    districts = draft.get("districts") or []
    district_rows = [{"label": d} for d in districts]
    district = _resolve_indexed_choice(district_rows, text, "dist", label_key="label")
    if not district:
        header = _("Please select your district from the list:")
        return build_option_list_message(
            district_rows,
            header,
            button_label=_("Select District"),
            section_title=_("Districts"),
            id_prefix="dist",
            label_key="label",
        )

    draft["custom_district"] = district
    draft["step"] = "awaiting_incident_date"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ District: *{0}*\n\n"
            "Step 9 — Enter *Incident Date*\n"
            "Format: {1}\n"
            "(cannot be in the future)"
        ).format(district, _DATE_HINT)
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


def _handle_incident_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    incident_date = _parse_user_date(text)
    if not incident_date:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter Incident Date as {0}.").format(_DATE_HINT)
        )
    if incident_date > getdate(today()):
        return OutboundMessage(body_text=_("Incident Date cannot be in the future. Please try again."))

    draft["custom_incident_date"] = str(incident_date)
    draft["step"] = "awaiting_person_involved"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ Incident Date: *{0}*\n\n"
            "Enter *Incident Person Involved*\n"
            "(name of person(s) involved — required):"
        ).format(formatdate(incident_date, "dd MMM YYYY"))
    )


def _handle_person_involved(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    name = (text or "").strip()
    if len(name) < 2:
        return OutboundMessage(body_text=_("Please enter the name of the person involved (required)."))

    draft["custom_grievance_against_name"] = name
    draft["step"] = "awaiting_designation"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ Person Involved: *{0}*\n\n"
            "Enter their *Designation* (if known), or type *skip*:"
        ).format(name)
    )


def _handle_designation(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean not in _SKIP_WORDS:
        draft["custom_grievance_designation"] = text.strip()

    draft["step"] = "awaiting_location"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_("Enter *Location of Incident* (where it happened — required):")
    )


def _handle_location(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    location = (text or "").strip()
    if len(location) < 2:
        return OutboundMessage(body_text=_("Please enter the location of the incident (required)."))

    draft["custom_location_of_incident"] = location
    if draft.get("grievance_type") == "Other":
        draft["step"] = "awaiting_other_type"
        _save_draft(conv, draft)
        return OutboundMessage(
            body_text=_(
                "✅ Location saved.\n\n"
                "You selected *Other* — please describe the type of grievance:"
            )
        )

    draft["step"] = "awaiting_description"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "✅ Location saved.\n\n"
            "Enter *Incident Description*\n"
            "(provide as much detail as possible — what happened, where, and how):"
        )
    )


def _handle_other_type(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    other = (text or "").strip()
    if len(other) < 3:
        return OutboundMessage(body_text=_("Please describe the grievance type (at least 3 characters)."))

    draft["custom_grievance_other_type"] = other
    draft["step"] = "awaiting_description"
    _save_draft(conv, draft)
    return OutboundMessage(
        body_text=_(
            "Enter *Incident Description*\n"
            "(provide as much detail as possible — what happened, where, and how):"
        )
    )


def _handle_description(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    description = (text or "").strip()
    if len(description) < 10:
        return OutboundMessage(
            body_text=_("Please provide a detailed description (at least 10 characters).")
        )

    draft["description"] = description
    draft["step"] = "awaiting_witnesses"
    _save_draft(conv, draft)

    prompt = _(
        "✅ Description saved.\n\n"
        "*Were there any witnesses?*"
    )
    return build_yes_no_buttons(prompt, yes_id="witness_yes", no_id="witness_no")


def _handle_witnesses(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("witness_yes", "yes", "y"):
        draft["custom_question1"] = "Yes"
        draft["step"] = "awaiting_witness_detail"
        _save_draft(conv, draft)
        return OutboundMessage(
            body_text=_(
                "Please provide witness *names and contact information*:"
            )
        )
    if clean in ("witness_no", "no", "n"):
        draft["custom_question1"] = "No"
        draft["step"] = "awaiting_reported_before"
        _save_draft(conv, draft)
        prompt = _("*Have you reported this incident to anyone before?*")
        return build_yes_no_buttons(prompt, yes_id="reported_yes", no_id="reported_no")

    prompt = _("Please tap *Yes* or *No* — were there any witnesses?")
    return build_yes_no_buttons(prompt, yes_id="witness_yes", no_id="witness_no")


def _handle_witness_detail(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    detail = (text or "").strip()
    if len(detail) < 3:
        return OutboundMessage(body_text=_("Please provide witness details (at least 3 characters)."))

    draft["custom_question_1_detail"] = detail
    draft["step"] = "awaiting_reported_before"
    _save_draft(conv, draft)
    prompt = _("*Have you reported this incident to anyone before?*")
    return build_yes_no_buttons(prompt, yes_id="reported_yes", no_id="reported_no")


def _handle_reported_before(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("reported_yes", "yes", "y"):
        draft["custom_question2"] = "Yes"
        draft["step"] = "awaiting_reported_detail"
        _save_draft(conv, draft)
        return OutboundMessage(
            body_text=_("Please provide details of who you reported to and when:")
        )
    if clean in ("reported_no", "no", "n"):
        draft["custom_question2"] = "No"
        draft["step"] = "awaiting_anonymous"
        _save_draft(conv, draft)
        prompt = _("*Would you like to remain anonymous?*")
        return build_yes_no_buttons(prompt, yes_id="anon_yes", no_id="anon_no")

    prompt = _("Please tap *Yes* or *No* — have you reported this before?")
    return build_yes_no_buttons(prompt, yes_id="reported_yes", no_id="reported_no")


def _handle_reported_detail(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    detail = (text or "").strip()
    if len(detail) < 3:
        return OutboundMessage(body_text=_("Please provide reporting details (at least 3 characters)."))

    draft["custom_question_2_detail"] = detail
    draft["step"] = "awaiting_anonymous"
    _save_draft(conv, draft)
    prompt = _("*Would you like to remain anonymous?*")
    return build_yes_no_buttons(prompt, yes_id="anon_yes", no_id="anon_no")


def _handle_anonymous(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("anon_yes", "yes", "y"):
        draft["custom_would_you_like_to_remain_anonymous"] = "Yes"
    elif clean in ("anon_no", "no", "n"):
        draft["custom_would_you_like_to_remain_anonymous"] = "No"
    else:
        prompt = _("Please tap *Yes* or *No* — would you like to remain anonymous?")
        return build_yes_no_buttons(prompt, yes_id="anon_yes", no_id="anon_no")

    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)
    summary = _build_summary(draft)
    return build_yes_no_buttons(
        summary + "\n\n" + _("Submit this concern report?"),
        yes_id="concern_submit",
        no_id="concern_cancel",
        yes_label=_("Submit"),
        no_label=_("Cancel"),
    )


def _build_summary(draft: dict[str, Any]) -> str:
    lines = [
        _("📋 *Concern Report Summary*"),
        "",
        _("• *Incident Type:* {0}").format(draft.get("grievance_type")),
    ]
    if draft.get("is_guest"):
        lines.append(_("• *Reporter:* {0}").format(draft.get("employee_name")))
    elif draft.get("employee"):
        lines.append(_("• *Employee:* {0}").format(draft.get("employee")))
    lines.extend([
        _("• *Incident Date:* {0}").format(formatdate(draft.get("custom_incident_date"), "dd MMM YYYY")),
        _("• *Person Involved:* {0}").format(draft.get("custom_grievance_against_name")),
        _("• *Location:* {0}").format(draft.get("custom_location_of_incident")),
        _("• *Witnesses:* {0}").format(draft.get("custom_question1")),
        _("• *Reported Before:* {0}").format(draft.get("custom_question2")),
        _("• *Anonymous:* {0}").format(draft.get("custom_would_you_like_to_remain_anonymous")),
    ])
    return "\n".join(lines)


def _handle_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("concern_cancel", "no", "cancel"):
        return _cancel_flow(conv, context)

    if clean not in ("concern_submit", "yes", "submit", "confirm"):
        summary = _build_summary(draft)
        return build_yes_no_buttons(
            summary + "\n\n" + _("Submit this concern report?"),
            yes_id="concern_submit",
            no_id="concern_cancel",
            yes_label=_("Submit"),
            no_label=_("Cancel"),
        )

    try:
        doc_name = _create_employee_grievance(draft, context)
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Concern report failed: {exc}")
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="concerns",
            draft_payload=None,
        )
        err_text = str(exc).replace("<br>", "\n").replace("<br/>", "\n")
        return wrap_with_menu_again(
            _("Could not submit concern report:\n\n{0}").format(err_text),
            context,
        )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="concerns",
        draft_payload=None,
    )
    web_form_url = _report_wrongdoing_url()
    return wrap_with_menu_again(
        _(
            "✅ *Concern Report Submitted*\n\n"
            "Reference: *{0}*\n"
            "Status: *Open*\n\n"
            "Your report will be reviewed confidentially. "
            "You are protected from retaliation under MicroMerger's Zero Tolerance policy.\n\n"
            "You can also submit via the web form:\n"
            "{1}"
        ).format(doc_name, web_form_url),
        context,
    )


def _report_wrongdoing_url() -> str:
    try:
        from frappe.utils import get_url

        return get_url("/report-wrongdoing/new")
    except Exception:
        return "/report-wrongdoing/new"


def _normalize_cnic(raw: str | None) -> str:
    """Strip formatting so CNIC matches Employee Grievance validation (13 digits)."""
    value = re.sub(r"[\s\-_]", "", (raw or "").strip())
    return value if re.match(r"^\d{13}$", value) else ""


def _prefill_employee_identity(doc: Any, employee_id: str) -> None:
    """Set fetched identity fields with normalized values before insert."""
    emp = frappe.get_cached_doc("Employee", employee_id)
    cnic = _normalize_cnic(emp.get("cnic"))
    if cnic:
        doc.custom_cnic = cnic
    mobile = (emp.get("cell_number") or "").strip()
    if mobile:
        doc.custom_mobile_no = mobile
    email = (emp.get("personal_email") or emp.get("company_email") or "").strip()
    if email:
        doc.custom_email = email


def _create_employee_grievance(draft: dict[str, Any], context: dict[str, Any]) -> str:
    employee_id = draft.get("employee") or context.get("employee")
    erp_user = context.get("user") or ""
    previous_user = frappe.session.user

    try:
        if employee_id and erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)
        elif not employee_id:
            frappe.set_user("Guest")

        doc = frappe.new_doc("Employee Grievance")
        doc.date = today()
        doc.grievance_type = draft.get("grievance_type")
        doc.custom_incident_date = draft.get("custom_incident_date")
        doc.custom_grievance_against_name = draft.get("custom_grievance_against_name")
        doc.custom_grievance_designation = draft.get("custom_grievance_designation") or ""
        doc.custom_location_of_incident = draft.get("custom_location_of_incident")
        doc.description = draft.get("description") or ""
        doc.custom_question1 = draft.get("custom_question1")
        doc.custom_question_1_detail = draft.get("custom_question_1_detail") or ""
        doc.custom_question2 = draft.get("custom_question2")
        doc.custom_question_2_detail = draft.get("custom_question_2_detail") or ""
        doc.custom_would_you_like_to_remain_anonymous = draft.get("custom_would_you_like_to_remain_anonymous")

        if draft.get("grievance_type") == "Other":
            doc.custom_grievance_other_type = draft.get("custom_grievance_other_type")

        if employee_id:
            doc.raised_by = employee_id
            _prefill_employee_identity(doc, employee_id)
        else:
            doc.employee_name = draft.get("employee_name")
            doc.custom_email = draft.get("custom_email")
            doc.custom_cnic = draft.get("custom_cnic")
            doc.custom_mobile_no = draft.get("custom_mobile_no")
            doc.custom_address = draft.get("custom_address")
            doc.custom_province = draft.get("custom_province")
            doc.custom_district = draft.get("custom_district")

        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    finally:
        frappe.set_user(previous_user)
