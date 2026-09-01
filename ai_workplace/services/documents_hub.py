"""
Documents & Contract hub and contract status for employees.
"""

from __future__ import annotations

from typing import Any

import frappe

from ai_workplace.services.profile_completion import build_portal_gap_guide
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage

PORTAL_URL = "https://portal.micromerger.com"


def build_documents_hub(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "📄 *دستاویزات اور معاہدہ*\n\n"
            "اپنی ملازمت سے متعلق دستاویزات یہاں سے حاصل کریں۔"
        )
    else:
        body = (
            "📄 *Documents & Contract*\n\n"
            "Access your employment documents and HR letters here."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_doc_contract", "title": "Contract"},
            {"id": "svc_doc_salary_slip", "title": "Salary Slip"},
            {"id": "svc_doc_tax_cert", "title": "Tax Cert"},
        ],
    )


def build_contract_status(context: dict[str, Any]) -> OutboundMessage:
    employee = context.get("employee") or ""
    lang = context.get("preferred_language", "English")

    if not frappe.db.exists("DocType", "Employee Contract"):
        return OutboundMessage(body_text=f"Contract information is available on the HRMIS Portal: {PORTAL_URL}")

    rows = frappe.get_all(
        "Employee Contract",
        filters={"employee": employee},
        fields=["name", "signature", "start_date", "end_date"],
        order_by="creation desc",
        limit=1,
    )
    contract = rows[0] if rows else None

    if not contract:
        if lang == "Urdu":
            body = (
                "📃 *ملازمت کا معاہدہ*\n\n"
                "آپ کا معاہدہ HR کے ذریعے تیار کیا جا رہا ہے۔ "
                "تیار ہونے پر آپ کو HRMIS Portal کے ذریعے مطلع کیا جائے گا۔"
            )
        else:
            body = (
                "📃 *Employment Contract*\n\n"
                "Your contract is being prepared by HR. "
                "You will be notified via the HRMIS Portal when it is ready for you."
            )
        return build_button_message(body, [{"id": "svc_open_hrmis", "title": "Open Portal"}, {"id": "svc_main_menu", "title": "Main Menu"}])

    if not contract.signature:
        return build_portal_gap_guide(context, "contract_signature")

    start = contract.get("start_date") or "—"
    end = contract.get("end_date") or "—"
    body = (
        f"📃 *Employment Contract*\n\n"
        f"Status: *Signed*\n"
        f"Period: {start} to {end}\n\n"
        f"View full details on the HRMIS Portal."
    )
    return build_button_message(
        body,
        [{"id": "svc_open_hrmis", "title": "Open Portal"}, {"id": "svc_main_menu", "title": "Main Menu"}],
    )


def build_pin_help(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "🔐 *Support PIN*\n\n"
            f"Support PIN صرف HRMIS Portal پر بنایا/تبدیل کیا جا سکتا ہے:\n{PORTAL_URL}\n\n"
            "*Settings* → *Security* → *Support PIN* (4 digits)"
        )
    else:
        body = (
            "🔐 *Support PIN Help*\n\n"
            f"Your Support PIN can only be created or changed on the HRMIS Portal:\n{PORTAL_URL}\n\n"
            "Go to *Settings* → *Security* → *Support PIN* (4 digits).\n\n"
            "WhatsApp only verifies your PIN — it cannot reset it."
        )
    return build_button_message(
        body,
        [{"id": "svc_open_hrmis", "title": "Open Portal"}, {"id": "svc_main_menu", "title": "Main Menu"}],
    )
