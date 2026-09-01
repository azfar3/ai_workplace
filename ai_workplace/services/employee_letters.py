"""
ai_workplace/services/employee_letters.py
────────────────────────────────────────────
Generate Experience / Bank letter PDFs for WhatsApp download.
Uses the same Letter Template + Employee Letter flow as the HR profile.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe
from frappe.utils import fmt_money, formatdate, get_first_day, get_last_day, getdate, today


BANK_CHOICES = ("Faysal Bank", "Standard Chartered Bank")


def _decrypt_if_needed(doctype: str, docname: str, fieldname: str, value: str | None) -> str:
    if not value:
        return ""
    if "gAAAA" in str(value):
        try:
            from mm_app.overrides.hr.employee import decrypt_field

            return decrypt_field(doctype, docname, fieldname) or ""
        except Exception:
            return value
    return value


def _create_employee_letter(
    employee_id: str,
    *,
    naming_series: str,
    template_name: str,
    rendered_content: str,
    template_body: str,
) -> str:
    emp = frappe.get_doc("Employee", employee_id)
    letter = frappe.new_doc("Employee Letter")
    letter.naming_series = naming_series
    letter.letter_template = template_name
    letter.employee = emp.name
    letter.employee_name = emp.employee_name
    letter.designation = emp.designation
    letter.company = emp.company
    letter.cnic = emp.cnic
    letter.letter = template_body
    letter.actual_content = rendered_content
    letter.save(ignore_permissions=True)
    letter.reload()
    if letter.qr_code and "{{ qr_code }}" in (letter.actual_content or ""):
        qr_html = f'<img class="qr_code" src="{letter.qr_code}" style="width:120px;">'
        letter.actual_content = letter.actual_content.replace("{{ qr_code }}", qr_html)
        letter.save(ignore_permissions=True)
    return letter.name


def _letter_pdf_bytes(letter_name: str) -> bytes:
    print_format = frappe.get_meta("Employee Letter").default_print_format or "Employee Letter"
    prev_user = frappe.session.user
    try:
        if prev_user == "Guest":
            frappe.set_user("Administrator")
        return frappe.get_print(
            "Employee Letter",
            letter_name,
            print_format=print_format,
            as_pdf=True,
            letterhead="MM",
        )
    finally:
        frappe.set_user(prev_user)


def generate_experience_letter_pdf(employee_id: str) -> tuple[bytes, str]:
    """Create and return Experience Letter PDF for an employee."""
    hr_settings = frappe.get_single("HR Settings")
    template_name = hr_settings.experience_letter_template
    if not template_name:
        frappe.throw("No experience letter template set in HR Settings.")

    emp = frappe.get_doc("Employee", employee_id)
    args = emp.as_dict()
    args["internal_work_history"] = args.get("internal_work_history") or []
    args["date_of_joining"] = formatdate(args.get("date_of_joining"), "dd-MMM-yyyy")
    args["cnic"] = _decrypt_if_needed("Employee", employee_id, "cnic", args.get("cnic"))
    args["fathers_name"] = _decrypt_if_needed("Employee", employee_id, "fathers_name", args.get("fathers_name"))

    table_html = frappe.render_template(
        """
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Designation</th><th>From</th><th>To</th></tr>
            {% for i in internal_work_history %}
            <tr>
                <td>{{ i.designation }}</td>
                <td>{{ i.from_date }}</td>
                <td>{{ i.to_date }}</td>
            </tr>
            {% endfor %}
        </table>
        """,
        args,
    )

    email_template = frappe.get_doc("Letter Template", template_name)
    message = frappe.render_template(email_template.letter_content, args)
    message = message.replace("{{ today_date }}", formatdate(today(), "dd-MMM-yyyy"))
    message = message.replace("{{ series }}", "0001")
    message = message.replace("{table}", table_html)
    hr_sign = frappe.db.get_value("Employee", "EMP-MM-00075", "hr_signature")
    if hr_sign:
        message = message.replace("{{ hr_signature }}", str(hr_sign))

    letter_name = _create_employee_letter(
        employee_id,
        naming_series="EXP-LTR-.####",
        template_name=template_name,
        rendered_content=message,
        template_body=email_template.letter_content,
    )
    safe_name = (emp.employee_name or employee_id).replace("/", "-").replace(" ", "_")
    filename = f"Experience_Letter_{safe_name}.pdf"
    return _letter_pdf_bytes(letter_name), filename


def generate_bank_letter_pdf(employee_id: str, bank_name: str) -> tuple[bytes, str]:
    """Create and return Bank Letter PDF for an employee."""
    hr_settings = frappe.get_single("HR Settings")
    template_name = hr_settings.bank_letter_template
    if not template_name:
        frappe.throw("No bank letter template set in HR Settings.")
    if not bank_name:
        frappe.throw("Bank name is required.")

    emp = frappe.get_doc("Employee", employee_id)
    args = emp.as_dict()
    args["date_of_joining"] = formatdate(args.get("date_of_joining"), "dd-MMM-yyyy")
    args["cnic"] = _decrypt_if_needed("Employee", employee_id, "cnic", args.get("cnic"))
    args["fathers_name"] = _decrypt_if_needed("Employee", employee_id, "fathers_name", args.get("fathers_name"))

    emp_salary = frappe.get_all(
        "Salary Structure Assignment",
        filters={"employee": employee_id, "docstatus": 1},
        fields=["base", "medical", "special_allowance"],
        order_by="creation desc",
        limit=1,
    )
    if not emp_salary:
        frappe.throw("Salary not defined yet. Please contact HR.")
    latest = emp_salary[0]
    total = (latest.get("base") or 0) + (latest.get("medical") or 0) + (latest.get("special_allowance") or 0)
    salary = fmt_money(total, currency="PKR")

    email_template = frappe.get_doc("Letter Template", template_name)
    message = frappe.render_template(email_template.letter_content, args)
    message = message.replace("{{ bank }}", bank_name)
    message = message.replace("{{ today_date }}", formatdate(today(), "dd-MMM-yyyy"))
    message = message.replace("{{ series }}", "0001")
    message = message.replace("{{ employee_code }}", args.get("name") or employee_id)
    message = message.replace("{{ salary }}", str(salary))
    hr_sign = frappe.db.get_value("Employee", "EMP-MM-00075", "hr_signature")
    if hr_sign:
        message = message.replace("{{ hr_signature }}", str(hr_sign))

    letter_name = _create_employee_letter(
        employee_id,
        naming_series="BK-LTR-.####",
        template_name=template_name,
        rendered_content=message,
        template_body=email_template.letter_content,
    )
    safe_name = (emp.employee_name or employee_id).replace("/", "-").replace(" ", "_")
    bank_slug = bank_name.replace(" ", "_")[:20]
    filename = f"Bank_Letter_{safe_name}_{bank_slug}.pdf"
    return _letter_pdf_bytes(letter_name), filename


def resolve_bank_name(context: dict[str, Any]) -> Optional[str]:
    """Use employee bank from profile when set."""
    employee_id = context.get("employee")
    if not employee_id:
        return None
    bank = frappe.db.get_value("Employee", employee_id, "bank_name")
    if bank and bank.strip():
        return bank.strip()
    return None


def build_letter_download_error(context: dict[str, Any], letter_type: str) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return f"معذرت، {letter_type} PDF بن نہیں سکی۔ براہ کرم HR سے رابطہ کریں۔"
    if lang == "Roman Urdu":
        return f"Maazrat, {letter_type} PDF generate nahi ho saki. HR se rabta karein."
    return f"Sorry, we couldn't generate your {letter_type} PDF. Please contact HR."


def build_letter_download_outbound(
    context: dict[str, Any],
    pdf_bytes: bytes,
    filename: str,
    caption: str,
) -> "OutboundMessage":
    from ai_workplace.whatsapp.outbound import OutboundMessage
    from ai_workplace.services.response_helpers import wrap_with_menu_again

    outbound = OutboundMessage(
        body_text=caption,
        document_caption=caption,
        document_bytes=pdf_bytes,
        document_filename=filename,
        document_mimetype="application/pdf",
    )
    menu = wrap_with_menu_again("", context)
    if menu.follow_up:
        outbound.follow_up = menu.follow_up
    return outbound
