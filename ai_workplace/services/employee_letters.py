"""
ai_workplace/services/employee_letters.py
────────────────────────────────────────────
Generate Experience / Bank letter PDFs for WhatsApp download.
Uses the same Letter Template + Employee Letter flow as the HR profile.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import frappe
from frappe.utils import fmt_money, formatdate, get_first_day, get_last_day, getdate, today

from ai_workplace.config import BOT_PDF_LETTERHEAD


BANK_CHOICES = ("Faysal Bank", "Standard Chartered Bank")

WORK_HISTORY_TABLE_TEMPLATE = """
<style>
    .work-history-card {
        width: 700px;
        margin: 20px auto;
        font-family: Arial, sans-serif;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border: 1px solid #e0e0e0;
    }

    .work-history-header {
        background-color: #2c3e50;
        color: white;
        padding: 10px;
        text-align: center;
        font-size: 16px;
        font-weight: bold;
    }

    .work-history-table {
        width: 100%;
        border-collapse: collapse;
    }

    .work-history-table th {
        background-color: #f4f6f9;
        padding: 10px;
        font-size: 13px;
        text-align: left;
        border-bottom: 1px solid #ddd;
    }

    .work-history-table td {
        padding: 8px 10px;
        font-size: 13px;
        border-bottom: 1px solid #eee;
    }

    .work-history-table tr:nth-child(even) {
        background-color: #fafafa;
    }

    .work-history-table tr:hover {
        background-color: #f1f7ff;
    }

    .date-column {
        white-space: nowrap;
        color: #555;
    }
</style>

<div class="work-history-card">

    <table class="work-history-table">
        <thead>
            <tr>
                <th>Designation</th>
                <th>From</th>
                <th>To</th>
            </tr>
        </thead>
        <tbody>
            {% for i in internal_work_history %}
            <tr>
                <td><strong>{{ i.designation }}</strong></td>
                <td class="date-column">
                    {% if i.from_date %}
                        {{ frappe.utils.formatdate(i.from_date, "dd-MMM-yyyy") }}
                    {% else %}
                        -
                    {% endif %}
                </td>
                <td class="date-column">
                    {% if i.to_date %}
                        {{ frappe.utils.formatdate(i.to_date, "dd-MMM-yyyy") }}
                    {% else %}
                        Present
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""


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

    content = letter.actual_content or ""
    needs_update = False

    # Replace {{ series }} and {{ name }} with the assigned letter.name
    if letter.name:
        if "{{ series }}" in content or "{{series}}" in content:
            content = re.sub(r"\{\{\s*series\s*\}\}", letter.name, content)
            needs_update = True
        if "{{ name }}" in content or "{{name}}" in content:
            content = re.sub(r"\{\{\s*name\s*\}\}", letter.name, content)
            needs_update = True

    # Handle QR code placeholder
    if letter.qr_code and ("{{ qr_code }}" in content or "{{qr_code}}" in content):
        qr_html = f'<img class="qr_code" src="{letter.qr_code}" style="width:70px;">'
        content = re.sub(r"\{\{\s*qr_code\s*\}\}", qr_html, content)
        needs_update = True
    elif "{{ qr_code }}" in content or "{{qr_code}}" in content:
        content = re.sub(r"\{\{\s*qr_code\s*\}\}", "", content)
        needs_update = True

    if needs_update:
        letter.actual_content = content
        letter.save(ignore_permissions=True)

    return letter.name


def _letter_pdf_bytes(letter_name: str) -> bytes:
    print_format = frappe.get_meta("Employee Letter").default_print_format or "Employee Letter"
    prev_user = frappe.session.user
    prev_form_dict = frappe.local.form_dict
    try:
        frappe.set_user("Administrator")
        # Isolate the print request from webhook parameters and use Frappe's
        # configured PDF renderer for the selected Print Format.
        frappe.local.form_dict = frappe._dict()
        return frappe.get_print(
            "Employee Letter",
            letter_name,
            print_format=print_format,
            as_pdf=True,
            letterhead=BOT_PDF_LETTERHEAD,
        )
    finally:
        frappe.local.form_dict = prev_form_dict
        frappe.set_user(prev_user)


def render_experience_letter_content(emp: Any, template_content: str) -> str:
    """Render experience letter HTML from Letter Template content and employee doc/dict."""
    args = emp.as_dict() if (hasattr(emp, "as_dict") and callable(getattr(emp, "as_dict", None))) else dict(emp)

    raw_history = args.get("internal_work_history") or []
    valid_history: list[dict[str, Any]] = []
    for row in raw_history:
        if isinstance(row, dict):
            row_dict = dict(row)
        elif hasattr(row, "as_dict") and callable(getattr(row, "as_dict", None)):
            row_dict = row.as_dict()
        else:
            row_dict = dict(row)

        if row_dict.get("designation"):
            valid_history.append(row_dict)

    if args.get("date_of_joining"):
        args["date_of_joining"] = formatdate(args["date_of_joining"], "dd-MMM-yyyy")
    else:
        args["date_of_joining"] = "-"

    if args.get("relieving_date"):
        args["relieving_date"] = formatdate(args["relieving_date"], "dd-MMM-yyyy")
    else:
        args["relieving_date"] = "-"

    employee_id = args.get("name") or getattr(emp, "name", "")
    args["cnic"] = _decrypt_if_needed("Employee", employee_id, "cnic", args.get("cnic"))
    args["fathers_name"] = _decrypt_if_needed("Employee", employee_id, "fathers_name", args.get("fathers_name"))
    district = args.get("custom_district_name") or ""
    province = args.get("custom_province_name") or ""
    args["custom_district_name"] = district or "-"
    args["custom_province_name"] = province or "-"

    message = frappe.render_template(template_content, args)

    # If internal_work_history is filled, render styled table and replace {table}
    if valid_history and "{table}" in template_content:
        table_html = frappe.render_template(
            WORK_HISTORY_TABLE_TEMPLATE,
            {"internal_work_history": valid_history},
        )
        if re.search(r"<p>\s*\{table\}(?:<strong>\s*</strong>)?\s*</p>", message):
            message = re.sub(r"<p>\s*\{table\}(?:<strong>\s*</strong>)?\s*</p>", table_html, message)
        else:
            message = message.replace("{table}", table_html)
    else:
        # Otherwise, experience letter without table (simple one-designation role letter)
        message = re.sub(r"<p>\s*\{table\}(?:<strong>\s*</strong>)?\s*</p>", "", message)
        message = message.replace("{table}", "")

    # Clean unused dynamic fields {{ first_field }}, {{ second_field }}, etc.
    message = re.sub(
        r"<p[^>]*>\s*(?:<strong[^>]*>)?\s*(?:\{\{\s*(?:first|second|third|fourth)_field\s*\}\}\s*)*(?:</strong>)?\s*</p>",
        "",
        message,
    )
    for field in ("first_field", "second_field", "third_field", "fourth_field"):
        message = re.sub(r"\{\{\s*" + field + r"\s*\}\}", "", message)

    message = re.sub(r"\{\{\s*today_date\s*\}\}", formatdate(today(), "dd-MMM-yyyy"), message)

    code_parts = str(employee_id).split("-")
    emp_code = code_parts[1] if len(code_parts) == 2 else code_parts[-1]
    message = re.sub(r"\{\{\s*employee_code\s*\}\}", emp_code, message)

    hr_sign = frappe.db.get_value("Employee", "EMP-MM-00075", "hr_signature") or ""
    message = re.sub(r"\{\{\s*hr_signature\s*\}\}", str(hr_sign), message)

    return message


def generate_experience_letter_pdf(employee_id: str) -> tuple[bytes, str]:
    """Create and return Experience Letter PDF for an employee."""
    if not employee_id:
        frappe.throw("Employee ID is required.")

    hr_settings = frappe.get_single("HR Settings")
    template_name = hr_settings.experience_letter_template or "Experience Letter"
    if not frappe.db.exists("Letter Template", template_name):
        frappe.throw(f"Experience letter template '{template_name}' not found.")

    emp = frappe.get_doc("Employee", employee_id)
    email_template = frappe.get_doc("Letter Template", template_name)

    rendered_message = render_experience_letter_content(emp, email_template.letter_content)

    letter_name = _create_employee_letter(
        employee_id,
        naming_series="EXP-LTR-.####",
        template_name=template_name,
        rendered_content=rendered_message,
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
    from ai_workplace.services.response_helpers import label_automated_response

    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        type_str = "تجربہ سرٹیفکیٹ" if "Experience" in letter_type else ("بینک لیٹر" if "Bank" in letter_type else letter_type)
        return label_automated_response(f"سسٹم کی عارضی خرابی کے باعث آپ کا {type_str} تیار نہیں ہو سکا۔ براہ کرم کچھ دیر بعد دوبارہ کوشش کریں یا فوری ضرورت کے لیے HR سے رابطہ کریں۔")
    if lang == "Roman Urdu":
        return label_automated_response(f"System ki aarzi kharabi ki wajah se aap ka {letter_type} tayar nahi ho saka. Kuch dair baad dobara koshish karein ya zaroorat par HR se rabta karein.")
    return label_automated_response(
        f"I couldn’t generate your requested *{letter_type}* due to a temporary system issue. "
        "Please try again later. If you need the document urgently, contact HR for assistance."
    )


def build_letter_download_outbound(
    context: dict[str, Any],
    pdf_bytes: bytes,
    filename: str,
    caption: str,
    parent_key: str = "main_menu",
) -> "OutboundMessage":
    from ai_workplace.whatsapp.outbound import OutboundMessage
    from ai_workplace.whatsapp.interactive import build_return_to_parent_button

    outbound = OutboundMessage(
        body_text=caption,
        document_caption=caption,
        document_bytes=pdf_bytes,
        document_filename=filename,
        document_mimetype="application/pdf",
    )
    parent_btn = build_return_to_parent_button(context, parent_key)
    if parent_btn:
        outbound.follow_up = [parent_btn]
    return outbound
