"""
ai_workplace/services/payroll.py
──────────────────────────────────
Salary slip download for WhatsApp self-service.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_months, formatdate, get_first_day, get_last_day, getdate, today

from ai_workplace.whatsapp.interactive import build_salary_slip_period_options_message
from ai_workplace.whatsapp.outbound import OutboundMessage


def get_salary_slips_for_months(employee_id: str | None, months: int) -> list[dict[str, Any]]:
    """Return submitted salary slips for the last N calendar months (excludes current month)."""
    if not employee_id or months < 1:
        return []

    today_date = getdate(today())
    period_end = get_last_day(add_months(today_date, -1))
    period_start = get_first_day(add_months(period_end, -(months - 1)))

    return frappe.db.get_all(
        "Salary Slip",
        filters={
            "employee": employee_id,
            "docstatus": 1,
            "start_date": ["between", [period_start, period_end]],
        },
        fields=["name", "start_date", "end_date", "posting_date", "gross_pay", "net_pay"],
        order_by="start_date asc",
    )


def get_default_salary_slip_print_format() -> str:
    """Use ERP default print format for Salary Slip."""
    return frappe.get_meta("Salary Slip").default_print_format or "Standard"


def generate_salary_slip_pdf(slip_name: str) -> tuple[bytes, str]:
    """Generate PDF bytes using the site's default Salary Slip print format."""
    print_format = get_default_salary_slip_print_format()
    doc = frappe.get_doc("Salary Slip", slip_name)
    safe_period = formatdate(doc.start_date, "MMM_YYYY")
    safe_employee = (doc.employee or "Employee").replace("/", "-").replace(" ", "_")
    filename = f"Salary_Slip_{safe_employee}_{safe_period}.pdf"

    prev_user = frappe.session.user
    try:
        if prev_user == "Guest":
            frappe.set_user("Administrator")
        pdf_bytes = frappe.get_print(
            "Salary Slip",
            slip_name,
            print_format=print_format,
            doc=doc,
            as_pdf=True,
        )
    finally:
        frappe.set_user(prev_user)

    return pdf_bytes, filename


def build_salary_slip_download_intro(context: dict[str, Any]) -> str:
    """Intro when user opens Previous Salary Slips (period picker)."""
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return (
            "📑 *پچھلی سیلری سلپس*\n\n"
            "براہ کرم بتائیں کتنے مہینوں کی سیلری سلپ PDF میں چاہیے (زیادہ سے زیادہ 6 ماہ)۔\n"
            "ERP کی ڈیفالٹ پرنٹ فارمیٹ استعمال ہوگی۔"
        )
    if lang == "Roman Urdu":
        return (
            "📑 *Previous Salary Slips*\n\n"
            "Batayein kitne mahine ki salary slip PDF chahiye (max 6 months).\n"
            "ERP ki default print format use hogi."
        )
    return (
        "📑 *Previous Salary Slips*\n\n"
        "Choose how many months of payslips you want as PDF (up to 6 months).\n"
        "We use your ERP default print format."
    )


def build_former_payslip_intro(context: dict[str, Any]) -> str:
    """Intro for ex-staff payslip download (same period options as previous slips)."""
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return (
            "🧾 *پے سلپ اور ٹیکس دستاویزات*\n\n"
            "آپ اپنی جمع شدہ سیلری سلپ PDF میں ڈاؤن لوڈ کر سکتے ہیں (1، 3 یا 6 ماہ)۔\n"
            "ERP کی ڈیفالٹ پرنٹ فارمیٹ استعمال ہوگی۔"
        )
    if lang == "Roman Urdu":
        return (
            "🧾 *Payslip & Tax Documents*\n\n"
            "Aap apni submitted salary slips PDF mein download kar sakte hain (1, 3 ya 6 months).\n"
            "ERP ki default print format use hogi."
        )
    return (
        "🧾 *Payslip & Tax Documents*\n\n"
        "Download your submitted salary slips as PDF (last 1, 3, or 6 months).\n"
        "We use your ERP default print format."
    )


def build_salary_slip_not_found(context: dict[str, Any], months: int) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return (
            f"📭 *{months} ماہ* کی کوئی جمع (Submitted) سیلری سلپ نہیں ملی۔\n"
            "براہ کرم دوسرا دورانیہ آزمائیں یا HR سے رابطہ کریں۔"
        )
    if lang == "Roman Urdu":
        return (
            f"📭 Pichle *{months} mahine* ki koi submitted salary slip nahi mili.\n"
            "Dusra duration try karein ya HR se rabta karein."
        )
    return (
        f"📭 No submitted salary slips found for the last *{months} month(s)*.\n"
        "Try another period or contact HR."
    )


def build_salary_slip_download_error(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return "معذرت، سیلری سلپ PDF بن نہیں سکی۔ براہ کرم دوبارہ کوشش کریں یا HR سے رابطہ کریں۔"
    if lang == "Roman Urdu":
        return "Maazrat, salary slip PDF generate nahi ho saki. Dobara koshish karein ya HR se rabta karein."
    return "Sorry, we couldn't generate your salary slip PDF. Please try again or contact HR."


def build_slip_document_caption(
    context: dict[str, Any],
    slip: dict[str, Any],
    index: int,
    total: int,
) -> str:
    """Caption for each PDF document sent on WhatsApp."""
    lang = context.get("preferred_language", "English")
    period = formatdate(slip.get("start_date"), "MMMM YYYY")
    net_pay = slip.get("net_pay")
    net_part = f" | Net: {net_pay}" if net_pay is not None else ""
    count_part = f" ({index}/{total})" if total > 1 else ""

    if lang == "Urdu":
        return f"📄 *{period}* سیلری سلپ{count_part}{net_part}"
    if lang == "Roman Urdu":
        return f"📄 *{period}* salary slip{count_part}{net_part}"
    return f"📄 *{period}* salary slip{count_part}{net_part}"


def build_salary_slip_download_outbound(
    context: dict[str, Any],
    months: int,
    *,
    show_period_options_after: bool = False,
) -> OutboundMessage:
    """Build outbound message chain: PDF(s) then navigation buttons."""
    from ai_workplace.services.response_helpers import (
        wrap_salary_slip_period_options,
        wrap_with_menu_again,
    )

    employee_id = context.get("employee") or ""
    slips = get_salary_slips_for_months(employee_id, months)

    def _wrap_error(body: str) -> OutboundMessage:
        if show_period_options_after:
            return wrap_salary_slip_period_options(body, context)
        return wrap_with_menu_again(body, context)

    if not slips:
        return _wrap_error(build_salary_slip_not_found(context, months))

    documents: list[OutboundMessage] = []
    total = len(slips)
    for idx, slip in enumerate(slips):
        try:
            pdf_bytes, filename = generate_salary_slip_pdf(slip["name"])
        except Exception:
            frappe.log_error(title="WhatsApp salary slip PDF failed", message=frappe.get_traceback())
            return _wrap_error(build_salary_slip_download_error(context))

        caption = build_slip_document_caption(context, slip, idx + 1, total)
        documents.append(
            OutboundMessage(
                body_text=caption,
                document_caption=caption,
                document_bytes=pdf_bytes,
                document_filename=filename,
                document_mimetype="application/pdf",
            )
        )

    from ai_workplace.whatsapp.interactive import build_show_menu_again_button

    if show_period_options_after:
        tail = [build_salary_slip_period_options_message(context)]
    else:
        menu_btn = build_show_menu_again_button(context)
        tail = [menu_btn] if menu_btn else []

    if len(documents) == 1:
        documents[0].follow_up = tail
        return documents[0]

    for i in range(len(documents) - 1):
        documents[i].follow_up = [documents[i + 1]]
    documents[-1].follow_up = tail
    return documents[0]
