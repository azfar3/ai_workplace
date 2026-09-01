"""
ai_workplace/services/hr_profile.py
───────────────────────────────────
HR Profile & Reporting Services.

Handles:
1. My Profile (`my_profile`): Basic employee info with CNIC & Bank Account masking.
2. Supervisor & Reporting (`supervisor_reporting`): Reporting manager, approvers, and direct reportees.
3. Update Profile (`update_profile`): "Coming Soon" notification with HR contact guidance.
"""

from __future__ import annotations

from typing import Any, Optional
import frappe
from frappe import _


def mask_cnic(cnic: Optional[str]) -> str:
    """
    Mask CNIC / National ID for privacy.
    Example: '61101-1234567-1' -> '61101-XXXXX08-1'
    Format: 5 digits + hyphens + 7 digits + hyphen + 1 digit.
    If string doesn't match standard format, mask middle characters.
    """
    if not cnic:
        return "N/A"
    clean = cnic.strip()
    if len(clean) >= 13:
        if "-" in clean:
            parts = clean.split("-")
            if len(parts) == 3:
                mid = parts[1]
                masked_mid = "XXXXX" + (mid[-2:] if len(mid) >= 2 else "")
                return f"{parts[0]}-{masked_mid}-{parts[2]}"
        start = clean[:5]
        end = clean[-3:]
        return f"{start}-XXXXX{end[:2]}-{end[-1]}"

    if len(clean) > 4:
        return clean[:3] + "X" * (len(clean) - 5) + clean[-2:]
    return "XXXX"


def mask_bank_account(acc_no: Optional[str]) -> str:
    """
    Mask Bank Account Number or IBAN for privacy.
    Example: '01010102938475' -> 'XXXX-XXXX-475' or 'XXXX-XXXX-4567'
    Keep last 4 digits visible, mask preceding characters.
    """
    if not acc_no:
        return "N/A"
    clean = acc_no.strip().replace(" ", "").replace("-", "")
    if len(clean) <= 4:
        return "XXXX"

    last4 = clean[-4:]
    return f"XXXX-XXXX-{last4}"


def get_employee_profile_data(employee_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Retrieve raw Employee doc details from Frappe DB."""
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return None

        emp = frappe.get_doc("Employee", employee_id)

        reports_to_name = None
        if emp.reports_to and frappe.db.exists("Employee", emp.reports_to):
            reports_to_name = frappe.db.get_value("Employee", emp.reports_to, "employee_name")

        return {
            "employee_id": emp.name,
            "employee_name": emp.employee_name or f"{emp.first_name or ''} {emp.last_name or ''}".strip(),
            "designation": emp.designation or "N/A",
            "department": emp.department or "N/A",
            "employment_type": emp.employment_type or "Full-Time",
            "status": emp.status or "Active",
            "date_of_joining": str(emp.date_of_joining) if getattr(emp, "date_of_joining", None) else "N/A",
            "reports_to_id": emp.reports_to or None,
            "reports_to_name": reports_to_name or "N/A",
            "company_email": getattr(emp, "company_email", None) or getattr(emp, "prefered_email", None) or getattr(emp, "personal_email", None) or "N/A",
            "cell_number": getattr(emp, "cell_number", None) or getattr(emp, "mobile_number", None) or "N/A",
            "emergency_phone_number": getattr(emp, "emergency_phone_number", None) or "N/A",
            "person_to_be_contacted": getattr(emp, "person_to_be_contacted", None) or "N/A",
            "date_of_birth": str(emp.date_of_birth) if getattr(emp, "date_of_birth", None) else "N/A",
            "cnic": getattr(emp, "cnic", None) or getattr(emp, "national_identity_number", None) or None,
            "bank_name": getattr(emp, "bank_name", None) or "N/A",
            "bank_ac_no": getattr(emp, "bank_ac_no", None) or getattr(emp, "iban", None) or None,
        }
    except Exception:
        return None


def get_supervisor_reporting_data(employee_id: Optional[str]) -> dict[str, Any]:
    """Retrieve supervisor info and direct reportees list."""
    res: dict[str, Any] = {
        "has_supervisor": False,
        "supervisor": None,
        "leave_approver": "N/A",
        "expense_approver": "N/A",
        "is_manager": False,
        "direct_reports": [],
    }
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return res

        emp = frappe.get_doc("Employee", employee_id)

        # 1. Direct Supervisor
        if emp.reports_to and frappe.db.exists("Employee", emp.reports_to):
            sup = frappe.get_doc("Employee", emp.reports_to)
            res["has_supervisor"] = True
            res["supervisor"] = {
                "employee_id": sup.name,
                "employee_name": sup.employee_name or f"{sup.first_name or ''} {sup.last_name or ''}".strip(),
                "designation": sup.designation or "N/A",
                "department": sup.department or "N/A",
                "branch": getattr(sup, "branch", None) or getattr(sup, "location", None) or "N/A",
                "company_email": getattr(sup, "company_email", None) or getattr(sup, "prefered_email", None) or "N/A",
                "cell_number": getattr(sup, "cell_number", None) or getattr(sup, "mobile_number", None) or "N/A",
            }

        # 2. Approvers
        if getattr(emp, "leave_approver", None):
            res["leave_approver"] = emp.leave_approver
        elif res["has_supervisor"]:
            res["leave_approver"] = res["supervisor"]["employee_name"]

        if getattr(emp, "expense_approver", None):
            res["expense_approver"] = emp.expense_approver
        elif res["has_supervisor"]:
            res["expense_approver"] = res["supervisor"]["employee_name"]

        # 3. Direct Reports (if user is a manager)
        reports = frappe.db.get_all(
            "Employee",
            filters={"reports_to": employee_id, "status": "Active"},
            fields=["name", "employee_name", "designation"],
            order_by="employee_name asc",
        )
        if reports:
            res["is_manager"] = True
            res["direct_reports"] = reports

        return res
    except Exception:
        return res


def build_my_profile_response(context: dict[str, Any]) -> str:
    """Build 'My Profile' message in English, Roman Urdu, or Urdu."""
    emp_id = context.get("employee")
    lang = context.get("preferred_language", "English")

    data = get_employee_profile_data(emp_id)
    if not data:
        if lang == "Urdu":
            return "معذرت، آپ کے ایمپلائی پروفائل کی معلومات مل نہیں سکیں۔ براہ کرم HR سے رابطہ کریں۔"
        elif lang == "Roman Urdu":
            return "Aap ke employee profile ki maloomat nahi mil sakin. Barah-e-karam HR se rabta karein."
        return "Sorry, your employee profile record could not be found. Please contact HR."

    cnic_masked = mask_cnic(data["cnic"])
    bank_acc_masked = mask_bank_account(data["bank_ac_no"])
    emergency_contact = data["cell_number"]
    if data["emergency_phone_number"] != "N/A":
        relation = f" ({data['person_to_be_contacted']})" if data['person_to_be_contacted'] != "N/A" else ""
        emergency_contact = f"{data['emergency_phone_number']}{relation}"

    if lang == "Urdu":
        return (
            f"👤 *آپ کی پروفائل*\n\n"
            f"🔹 *ملازمت کی تفصیلات*\n"
            f"• *ایمپلائی آئی ڈی:* {data['employee_id']}\n"
            f"• *نام:* {data['employee_name']}\n"
            f"• *عہدہ:* {data['designation']}\n"
            f"• *شعبہ:* {data['department']}\n"
            f"• *شمولیت کی تاریخ:* {data['date_of_joining']}\n"
            f"• *رپورٹنگ مینیجر:* {data['reports_to_name']}\n\n"
            f"🔹 *رابطے کی تفصیلات*\n"
            f"• *ای میل:* {data['company_email']}\n"
            f"• *موبائل:* {data['cell_number']}\n"
            f"• *ہنگامی رابطہ:* {emergency_contact}\n\n"
            f"🔹 *ذاتی اور بینک کی معلومات*\n"
            f"• *تاریخ پیدائش:* {data['date_of_birth']}\n"
            f"• *شناختی کارڈ (CNIC):* {cnic_masked}\n"
            f"• *بینک:* {data['bank_name']}\n"
            f"• *اکاؤنٹ نمبر:* {bank_acc_masked}\n\n"
            f"💡 *پروفائل اپ ڈیٹ کے لیے مینو سے 'Contact HR' منتخب کریں۔*\n\n"
            f"مین مینو پر واپس جانے کے لیے 'menu' لکھیے۔"
        )
    elif lang == "Roman Urdu":
        return (
            f"👤 *AAP KI PROFILE*\n\n"
            f"🔹 *Mulazmat Ki Tafseelat*\n"
            f"• *Employee ID:* {data['employee_id']}\n"
            f"• *Naam:* {data['employee_name']}\n"
            f"• *Ohda (Designation):* {data['designation']}\n"
            f"• *Shoba (Department):* {data['department']}\n"
            f"• *Joining Date:* {data['date_of_joining']}\n"
            f"• *Reports To:* {data['reports_to_name']}\n\n"
            f"🔹 *Rabta Ki Tafseelat*\n"
            f"• *Email:* {data['company_email']}\n"
            f"• *Mobile:* {data['cell_number']}\n"
            f"• *Emergency Contact:* {emergency_contact}\n\n"
            f"🔹 *Zati Aur Bank Info*\n"
            f"• *Date of Birth (DOB):* {data['date_of_birth']}\n"
            f"• *CNIC:* {cnic_masked}\n"
            f"• *Bank:* {data['bank_name']}\n"
            f"• *Account No:* {bank_acc_masked}\n\n"
            f"💡 *Profile update karwane ke liye menu se 'Contact HR' select karein.*\n\n"
            f"Main menu par wapas jaane ke liye 'menu' likhein."
        )

    return (
        f"👤 *MY PROFILE*\n\n"
        f"🔹 *Employment Details*\n"
        f"• *ID:* {data['employee_id']}\n"
        f"• *Name:* {data['employee_name']}\n"
        f"• *Designation:* {data['designation']}\n"
        f"• *Department:* {data['department']}\n"
        f"• *Joining Date:* {data['date_of_joining']}\n"
        f"• *Reports To:* {data['reports_to_name']}\n\n"
        f"🔹 *Contact Details*\n"
        f"• *Email:* {data['company_email']}\n"
        f"• *Mobile:* {data['cell_number']}\n"
        f"• *Emergency Contact:* {emergency_contact}\n\n"
        f"🔹 *Personal & Bank Info*\n"
        f"• *DOB:* {data['date_of_birth']}\n"
        f"• *CNIC:* {cnic_masked}\n"
        f"• *Bank:* {data['bank_name']}\n"
        f"• *Account No:* {bank_acc_masked}\n\n"
        f"💡 *To request changes to your profile, please select 'Contact HR' from the menu.*\n\n"
        f"Type 'menu' to return to the main menu."
    )


def build_supervisor_reporting_response(context: dict[str, Any]) -> str:
    """Build 'Supervisor & Reporting' message in English, Roman Urdu, or Urdu."""
    emp_id = context.get("employee")
    lang = context.get("preferred_language", "English")

    rep_data = get_supervisor_reporting_data(emp_id)

    if lang == "Urdu":
        lines = ["👨‍💼 *سپروائزر اور HR رابطہ*\n"]
        if rep_data["has_supervisor"]:
            sup = rep_data["supervisor"]
            lines.append(
                f"🔹 *ڈائریکٹ مینیجر*\n"
                f"• *نام:* {sup['employee_name']}\n"
                f"• *عہدہ:* {sup['designation']}\n"
                f"• *شعبہ:* {sup['department']}\n"
                f"• *مقام:* {sup['branch']}\n"
                f"• *ای میل:* {sup['company_email']}\n"
                f"• *موبائل:* {sup['cell_number']}\n"
            )
        else:
            lines.append("🔹 *ڈائریکٹ مینیجر*\n• سسٹم میں کوئی ڈائریکٹ مینیجر درج نہیں ہے۔\n")

        lines.append(
            f"🔹 *منظوری دینے والے (Approvers)*\n"
            f"• *چھٹی (Leave):* {rep_data['leave_approver']}\n"
            f"• *اخراجات (Expense):* {rep_data['expense_approver']}\n"
        )

        if rep_data["is_manager"]:
            team_list = rep_data["direct_reports"]
            lines.append(f"👥 *آپ کی ٹیم (Direct Reports: {len(team_list)})*")
            for idx, member in enumerate(team_list[:5], start=1):
                lines.append(f"{idx}. *{member['employee_name']}* — {member['designation']} (`{member['name']}`)")
            if len(team_list) > 5:
                lines.append(f"*(اور دیگر {len(team_list) - 5} ممبران)*")
            lines.append("")

        lines.append("مین مینو پر واپس جانے کے لیے 'menu' لکھیے۔")
        lines.extend(_hr_contact_footer(lang))
        return "\n".join(lines)

    elif lang == "Roman Urdu":
        lines = ["👨‍💼 *Supervisor & HR Contact*\n"]
        if rep_data["has_supervisor"]:
            sup = rep_data["supervisor"]
            lines.append(
                f"🔹 *Direct Manager*\n"
                f"• *Naam:* {sup['employee_name']}\n"
                f"• *Ohda (Designation):* {sup['designation']}\n"
                f"• *Shoba (Department):* {sup['department']}\n"
                f"• *Location:* {sup['branch']}\n"
                f"• *Email:* {sup['company_email']}\n"
                f"• *Mobile:* {sup['cell_number']}\n"
            )
        else:
            lines.append("🔹 *Direct Manager*\n• System mein koi direct manager assigned nahi hai.\n")

        lines.append(
            f"🔹 *Approvers*\n"
            f"• *Leave Approver:* {rep_data['leave_approver']}\n"
            f"• *Expense Approver:* {rep_data['expense_approver']}\n"
        )

        if rep_data["is_manager"]:
            team_list = rep_data["direct_reports"]
            lines.append(f"👥 *Aap Ki Team (Direct Reports: {len(team_list)})*")
            for idx, member in enumerate(team_list[:5], start=1):
                lines.append(f"{idx}. *{member['employee_name']}* — {member['designation']} (`{member['name']}`)")
            if len(team_list) > 5:
                lines.append(f"*(aur mazeed {len(team_list) - 5} members)*")
            lines.append("")

        lines.append("Main menu par wapas jaane ke liye 'menu' likhein.")
        lines.extend(_hr_contact_footer(lang))
        return "\n".join(lines)

    lines = ["👨‍💼 *Supervisor & HR Contact*\n"]
    if rep_data["has_supervisor"]:
        sup = rep_data["supervisor"]
        lines.append(
            f"🔹 *Direct Manager*\n"
            f"• *Name:* {sup['employee_name']}\n"
            f"• *Designation:* {sup['designation']}\n"
            f"• *Department:* {sup['department']}\n"
            f"• *Location:* {sup['branch']}\n"
            f"• *Email:* {sup['company_email']}\n"
            f"• *Mobile:* {sup['cell_number']}\n"
        )
    else:
        lines.append("🔹 *Direct Manager*\n• No direct supervisor is currently assigned in the system.\n")

    lines.append(
        f"🔹 *Approvers*\n"
        f"• *Leave Approver:* {rep_data['leave_approver']}\n"
        f"• *Expense Approver:* {rep_data['expense_approver']}\n"
    )

    if rep_data["is_manager"]:
        team_list = rep_data["direct_reports"]
        lines.append(f"👥 *YOUR TEAM SUMMARY (Direct Reports: {len(team_list)})*")
        for idx, member in enumerate(team_list[:5], start=1):
            lines.append(f"{idx}. *{member['employee_name']}* — {member['designation']} (`{member['name']}`)")
        if len(team_list) > 5:
            lines.append(f"*(and {len(team_list) - 5} more members)*")
        lines.append("")

    lines.append("Type 'menu' to return to the main menu.")
    lines.extend(_hr_contact_footer(lang))
    return "\n".join(lines)


def _hr_contact_footer(lang: str) -> list[str]:
    from ai_workplace.services.hr_contact_prompt import get_hr_contact_details

    phone, email = get_hr_contact_details()
    if lang == "Urdu":
        return [
            "",
            "🔹 *HR رابطہ*",
            f"• فون: {phone}",
            f"• ای میل: {email}",
            "• مینو سے *Chat with HR* منتخب کر کے براہ راست بات کریں۔",
        ]
    if lang == "Roman Urdu":
        return [
            "",
            "🔹 *HR Contact*",
            f"• Phone: {phone}",
            f"• Email: {email}",
            "• Menu se *Chat with HR* select kar ke direct baat karein.",
        ]
    return [
        "",
        "🔹 *HR Contact*",
        f"• Phone: {phone}",
        f"• Email: {email}",
        "• Select *Chat with HR* from the menu to speak with HR directly.",
    ]

