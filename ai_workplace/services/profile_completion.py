"""
Profile completion hub and WhatsApp flows (all changes via HR approval / EPCR).
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.profile_gaps import gap_flow_key, get_employee_profile_gaps
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message

_CANCEL = frozenset({"cancel", "menu", "main menu", "exit", "stop"})
_SCAN_STEPS = frozenset({"front_scan", "back_scan", "scan"})

PORTAL_URL = "https://portal.micromerger.com"

DOC_FIELD_BY_GAP: dict[str, str] = {
    "police_cert": "police_character_certificate",
    "psea_cert": "psea_certificate",
}

PORTAL_GAP_GUIDES: dict[str, dict[str, str]] = {
    "declaration_conflict": {
        "English": (
            "📝 *Declaration of Conflict of Interest*\n\n"
            f"Please submit this on the HRMIS Portal:\n{PORTAL_URL}\n\n"
            "Go to *Compliance* → *Declaration of Conflict of Interest*."
        ),
        "Urdu": (
            "📝 *تضاد مفادات کا اعلان*\n\n"
            f"HRMIS Portal پر جمع کروائیں:\n{PORTAL_URL}\n\n"
            "*Compliance* → *Declaration of Conflict of Interest*."
        ),
    },
    "contract": {
        "English": (
            "📄 *Employment Contract*\n\n"
            "Your contract is not generated yet. HR will publish it on the HRMIS Portal when ready.\n\n"
            f"Check: {PORTAL_URL} → *Documents*."
        ),
        "Urdu": (
            "📄 *ملازمت کا معاہدہ*\n\n"
            "معاہدہ ابھی تیار نہیں ہوا۔ HR تیار ہونے پر Portal پر شائع کرے گی۔\n\n"
            f"{PORTAL_URL} → *Documents*."
        ),
    },
    "contract_signature": {
        "English": (
            "✍️ *Sign Employment Contract*\n\n"
            f"Please sign your contract on the HRMIS Portal:\n{PORTAL_URL}\n\n"
            "Go to *Documents* → *Employment Contract*."
        ),
        "Urdu": (
            "✍️ *معاہدے پر دستخط*\n\n"
            f"HRMIS Portal پر دستخط کریں:\n{PORTAL_URL}\n\n"
            "*Documents* → *Employment Contract*."
        ),
    },
    "support_pin_not_configured": {
        "English": (
            "🔐 *Support PIN Required*\n\n"
            f"Set your 4-digit Support PIN on the Portal first:\n{PORTAL_URL}\n\n"
            "*Settings* → *Security* → *Support PIN*."
        ),
        "Urdu": (
            "🔐 *Support PIN درکار*\n\n"
            f"پہلے Portal پر PIN سیٹ کریں:\n{PORTAL_URL}\n\n"
            "*Settings* → *Security*."
        ),
    },
}

_FLOW_PROMPTS: dict[str, dict[str, str]] = {
    "prof_cnic_add": {
        "start": "Please enter your CNIC number (13 digits, no dashes):",
        "front_scan": "Please send a photo of your CNIC *front*.",
        "back_scan": "Please send a photo of your CNIC *back*.",
        "issue_date": "Enter CNIC issue date (YYYY-MM-DD):",
        "expiry_date": "Enter CNIC expiry date (YYYY-MM-DD):",
    },
    "prof_bank_update": {
        "start": "Please enter your bank name:",
        "account_title": "Enter account title (name on account):",
        "account": "Enter your bank account number:",
        "iban": "Enter your IBAN (or type *skip*):",
    },
    "prof_contact_update": {
        "start": "Enter your mobile number:",
        "email": "Enter your email address:",
        "emergency": "Enter emergency contact number (or type *skip*):",
    },
    "prof_photo_upload": {
        "start": "Please send your profile photo as an image.",
    },
    "prof_doc_upload": {
        "start": "Send the document file (PDF or image).",
    },
    "prof_education_ticket": {
        "start": "Enter your qualification (e.g. Bachelors):",
        "institution": "Enter institution / university name:",
        "year": "Enter passing year:",
        "scan": "Upload degree scan (photo or PDF):",
        "confirm": "Type *yes* to submit this education request to HR.",
    },
    "prof_work_history_ticket": {
        "start": "Enter your previous company name:",
        "designation": "Enter your designation:",
        "dates": "Enter start and end dates (e.g. Jan 2020 - Dec 2022):",
        "scan": "Upload experience letter or proof (optional — type *skip*):",
        "confirm": "Type *yes* to submit this work history request to HR.",
    },
}


def build_profile_completion_hub(context: dict[str, Any]) -> OutboundMessage:
    employee = context.get("employee") or ""
    report = get_employee_profile_gaps(employee)
    gaps = [
        g for g in report.get("all_gaps", [])
        if g.get("update_mode") in ("ticket", "direct", "portal_only")
        and g.get("key") not in ("attendance_checkin", "attendance_missing")
    ][:5]

    lang = context.get("preferred_language", "English")
    name = report.get("employee_name") or context.get("employee_name") or "there"

    if lang == "Urdu":
        header = f"👤 *میری تفصیلات اور دستاویزات* — {name}"
        intro = "آپ یہاں اپنی ذاتی معلومات دیکھ یا اپ ڈیٹ کر سکتے ہیں۔"
        pending = "کچھ معاملات آپ کی توجہ کے متقبل ہو سکتے ہیں۔ ذیل میں سے منتخب کریں:"
    else:
        header = f"👤 *My Details & Documents* — {name}"
        intro = "You can review or update your personal information and submit required documents here."
        pending = "A few items may need your attention. Choose an item to review or update:"

    lines = [header, "", intro]
    if gaps:
        lines.extend(["", pending])
        for idx, gap in enumerate(gaps, 1):
            lines.append(f"{idx}. {gap['label']}")

    if not gaps:
        lines.append("\n✅ No outstanding items need your action right now.")

    body = "\n".join(lines)
    buttons = []
    for gap in gaps[:2]:
        flow = gap.get("flow_key") or gap_flow_key(gap["key"])
        if gap.get("update_mode") == "portal_only":
            buttons.append({"id": f"svc_gap_{gap['key']}", "title": gap["label"][:20]})
        elif flow:
            buttons.append({"id": f"svc_{flow}", "title": gap["label"][:20]})
        else:
            buttons.append({"id": f"svc_gap_{gap['key']}", "title": gap["label"][:20]})
    buttons.append({"id": "svc_prof_my_requests", "title": "My Requests"})
    if len(buttons) < 3:
        buttons.append({"id": "svc_main_menu", "title": "Main Menu"})

    return build_button_message(body, buttons[:3])


def build_portal_gap_guide(context: dict[str, Any], gap_key: str) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    guides = PORTAL_GAP_GUIDES.get(gap_key, {})
    body = guides.get(lang) or guides.get("English") or (
        f"Please complete this item on the HRMIS Portal: {PORTAL_URL}"
    )
    return build_button_message(
        body,
        [
            {"id": "svc_open_hrmis", "title": "Open HRMIS Portal"},
            {"id": "svc_update_profile", "title": "My Details"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def handle_profile_gap_action(conv: Any, context: dict[str, Any], gap_key: str) -> OutboundMessage:
    """Route a profile hub gap button to approval flow, ticket flow, or portal guidance."""
    report = get_employee_profile_gaps(context.get("employee") or "")
    gap = next((g for g in report.get("all_gaps", []) if g.get("key") == gap_key), None)
    if not gap:
        return OutboundMessage(body_text="This profile item is no longer pending. Type *menu* for main menu.")

    mode = gap.get("update_mode")
    if mode == "portal_only":
        return build_portal_gap_guide(context, gap_key)
    if mode == "guidance_only":
        return OutboundMessage(
            body_text=f"📌 {gap.get('label')}\n\nPlease follow your supervisor or HR guidance for this item."
        )

    flow_key = gap.get("flow_key") or gap_flow_key(gap_key)
    if not flow_key:
        return build_portal_gap_guide(context, gap_key)

    extra: dict[str, Any] = {}
    if flow_key == "prof_doc_upload":
        extra["doc_field"] = DOC_FIELD_BY_GAP.get(gap_key, gap_key)
    return start_profile_flow(conv, context, flow_key, extra=extra)


def start_profile_flow(
    conv: Any,
    context: dict[str, Any],
    flow_key: str,
    extra: dict[str, Any] | None = None,
) -> OutboundMessage:
    data = dict(extra or {})
    draft = {"flow": flow_key, "step": "start", "data": data}
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=flow_key,
        draft_payload=json.dumps(draft),
    )
    prompt = _FLOW_PROMPTS.get(flow_key, {}).get("start", "Please provide the requested information:")
    if flow_key in _APPROVAL_FLOW_KEYS:
        prompt = (
            f"{prompt}\n\n"
            "_Your update will be submitted to HR for approval before it is applied._"
        )
    return OutboundMessage(body_text=prompt)


_APPROVAL_FLOW_KEYS = frozenset({
    "prof_cnic_add",
    "prof_bank_update",
    "prof_contact_update",
    "prof_photo_upload",
    "prof_doc_upload",
    "prof_education_ticket",
    "prof_work_history_ticket",
})


def _submit_profile_ticket(
    conv: Any,
    context: dict[str, Any],
    request_type: str,
    proposed: dict,
    attachment: str = "",
) -> OutboundMessage:
    from ai_workplace.api.profile import submit_whatsapp_profile_change_request

    try:
        result = submit_whatsapp_profile_change_request(
            context.get("employee"),
            request_type,
            [{
                "field": request_type.lower().replace(" ", "_"),
                "value": "",
                "proposed_json": json.dumps(proposed),
                "attachment": attachment,
            }],
            context=context,
        )
    except Exception as exc:
        return OutboundMessage(body_text=f"Could not submit request: {exc}")
    update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
    return OutboundMessage(
        body_text=(
            f"✅ Request submitted: *{result.get('name')}*\n"
            f"Type: {request_type}\n"
            "Status: Pending HR Review\n\n"
            "We will notify you on WhatsApp when HR responds.\n"
            "Type *menu* for main menu."
        )
    )


def handle_profile_flow_message(conv: Any, text: str, context: dict[str, Any]) -> OutboundMessage:
    draft = json.loads(conv.draft_payload or "{}")
    flow = draft.get("flow", "")
    step = draft.get("step", "start")
    data = draft.get("data", {})
    clean = (text or "").strip()

    if clean.lower() in _CANCEL:
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        return OutboundMessage(body_text="Profile update cancelled. Type *menu* for main menu.")

    handlers = {
        "prof_cnic_add": _handle_cnic_flow,
        "prof_bank_update": _handle_bank_flow,
        "prof_contact_update": _handle_contact_flow,
        "prof_education_ticket": _handle_education_ticket,
        "prof_work_history_ticket": _handle_work_ticket,
        "prof_doc_upload": _handle_doc_upload,
    }
    handler = handlers.get(flow)
    if handler:
        return handler(conv, context, draft, step, data, clean)

    update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
    return OutboundMessage(body_text="Please type *menu* to return to the main menu.")


def handle_profile_flow_media(
    conv: Any,
    context: dict[str, Any],
    file_url: str,
    filename: str = "",
) -> OutboundMessage:
    draft = json.loads(conv.draft_payload or "{}")
    flow = draft.get("flow", "")
    step = draft.get("step", "start")
    data = draft.get("data", {})

    if flow == "prof_photo_upload" and step == "start":
        return _submit_profile_ticket(
            conv,
            context,
            "Profile Photo",
            {"image": file_url},
            attachment=file_url,
        )

    if flow == "prof_cnic_add" and step in ("front_scan", "back_scan"):
        field = "cnic_scan_front" if step == "front_scan" else "cnic_scan_back"
        data[field] = file_url
        next_step = "back_scan" if step == "front_scan" else "issue_date"
        draft.update({"step": next_step, "data": data})
        update_conversation(
            conv,
            state=ConversationState.PROCESSING,
            current_intent=flow,
            draft_payload=json.dumps(draft),
        )
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_cnic_add"][next_step])

    if flow == "prof_education_ticket" and step == "scan":
        data["attachment"] = file_url
        draft.update({"step": "confirm", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_education_ticket"]["confirm"])

    if flow == "prof_work_history_ticket" and step == "scan":
        data["attachment"] = file_url
        draft.update({"step": "confirm", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_work_history_ticket"]["confirm"])

    if flow == "prof_doc_upload" and step == "start":
        doc_field = data.get("doc_field", "police_character_certificate")
        return _submit_profile_ticket(
            conv,
            context,
            "Document Upload",
            {doc_field: file_url},
            attachment=file_url,
        )

    return OutboundMessage(
        body_text="Unexpected file for this step. Please send the requested attachment or type *menu*."
    )


def _handle_cnic_flow(conv, context, draft, step, data, clean) -> OutboundMessage:
    flow = "prof_cnic_add"

    if step in ("front_scan", "back_scan"):
        label = "CNIC front" if step == "front_scan" else "CNIC back"
        return OutboundMessage(
            body_text=f"Please send your *{label}* as a photo attachment (not text)."
        )

    if step == "start":
        data["cnic"] = clean
        draft.update({"step": "front_scan", "data": data})
        update_conversation(
            conv,
            state=ConversationState.PROCESSING,
            current_intent=flow,
            draft_payload=json.dumps(draft),
        )
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["front_scan"])

    if step == "issue_date":
        data["date_of_issue"] = clean
        draft.update({"step": "expiry_date", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["expiry_date"])

    if step == "expiry_date":
        data["valid_upto"] = clean
        return _submit_profile_ticket(conv, context, "CNIC Change", data)

    return OutboundMessage(body_text="Please continue with your CNIC update or type *cancel*.")


def _handle_bank_flow(conv, context, draft, step, data, clean) -> OutboundMessage:
    flow = "prof_bank_update"

    if step == "start":
        data["bank_name"] = clean
        draft.update({"step": "account_title", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["account_title"])

    if step == "account_title":
        data["bank_account_title"] = clean
        draft.update({"step": "account", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["account"])

    if step == "account":
        data["bank_ac_no"] = clean
        draft.update({"step": "iban", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["iban"])

    if step == "iban":
        if clean.lower() != "skip":
            data["iban"] = clean
        return _submit_profile_ticket(conv, context, "Bank Change", data)

    return OutboundMessage(body_text="Please continue with bank details.")


def _handle_contact_flow(conv, context, draft, step, data, clean) -> OutboundMessage:
    flow = "prof_contact_update"

    if step == "start":
        data["cell_number"] = clean
        draft.update({"step": "email", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["email"])

    if step == "email":
        data["prefered_email"] = clean
        draft.update({"step": "emergency", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS[flow]["emergency"])

    if step == "emergency":
        if clean.lower() not in ("skip", "uploaded", "done", "na", "n/a", "-"):
            data["emergency_phone_number"] = clean
        return _submit_profile_ticket(conv, context, "Contact Change", data)

    return OutboundMessage(body_text="Please continue with contact details.")


def _handle_education_ticket(conv, context, draft, step, data, clean) -> OutboundMessage:
    if step == "start":
        data["qualification"] = clean
        draft.update({"step": "institution", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_education_ticket"]["institution"])

    if step == "institution":
        data["institution"] = clean
        draft.update({"step": "year", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_education_ticket"]["year"])

    if step == "year":
        data["year"] = clean
        draft.update({"step": "scan", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_education_ticket"]["scan"])

    if step == "confirm" and clean.lower() in ("yes", "y", "confirm"):
        return _submit_ticket(conv, context, "Education", data, {
            "qualification": data.get("qualification"),
            "school_univ": data.get("institution"),
            "year_of_passing": data.get("year"),
        })

    if step == "scan":
        return OutboundMessage(body_text="Please send the degree scan as a photo or PDF attachment.")

    return OutboundMessage(body_text="Type *yes* to confirm or *cancel* to abort.")


def _handle_work_ticket(conv, context, draft, step, data, clean) -> OutboundMessage:
    if step == "start":
        data["company"] = clean
        draft.update({"step": "designation", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_work_history_ticket"]["designation"])

    if step == "designation":
        data["designation"] = clean
        draft.update({"step": "dates", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_work_history_ticket"]["dates"])

    if step == "dates":
        data["dates"] = clean
        draft.update({"step": "scan", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_work_history_ticket"]["scan"])

    if step == "scan" and clean.lower() == "skip":
        draft.update({"step": "confirm", "data": data})
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_FLOW_PROMPTS["prof_work_history_ticket"]["confirm"])

    if step == "confirm" and clean.lower() in ("yes", "y", "confirm"):
        return _submit_ticket(conv, context, "Work History", data, {
            "company_name": data.get("company"),
            "designation": data.get("designation"),
            "employment_period": data.get("dates"),
        })

    if step == "scan" and clean.lower() != "skip":
        return OutboundMessage(body_text="Please send the document as an attachment, or type *skip*.")

    return OutboundMessage(body_text="Type *yes* to confirm or *cancel* to abort.")


def _handle_doc_upload(conv, context, draft, step, data, clean) -> OutboundMessage:
    return OutboundMessage(body_text="Please send the document as a file attachment.")


def _submit_ticket(conv, context, request_type: str, data: dict, proposed: dict) -> OutboundMessage:
    return _submit_profile_ticket(
        conv,
        context,
        request_type,
        proposed,
        attachment=data.get("attachment", ""),
    )


def build_my_requests_response(context: dict[str, Any]) -> OutboundMessage:
    from ai_workplace.api.profile import get_pending_profile_requests

    pending = get_pending_profile_requests(context.get("employee") or "")
    if not pending:
        return OutboundMessage(body_text="No pending profile change requests.")
    lines = ["📋 *Your Profile Requests*\n"]
    for req in pending:
        lines.append(f"• {req['name']} — {req.get('request_type')} — {req.get('status')}")
    return OutboundMessage(body_text="\n".join(lines))
