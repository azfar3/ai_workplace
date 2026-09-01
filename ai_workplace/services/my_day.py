"""
Lightweight My Day snapshot — deterministic employee dashboard.
"""

from __future__ import annotations

from typing import Any

import frappe

from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage


def build_my_day_response(context: dict[str, Any]) -> OutboundMessage:
    employee = context.get("employee") or ""
    lang = context.get("preferred_language", "English")
    lines: list[str] = []

    if lang == "Urdu":
        lines.append("☀️ *میرا دن*")
    else:
        lines.append("☀️ *My Day*")

    lines.append("")

    # Attendance
    try:
        from ai_workplace.services.attendance_guidance import get_attendance_snapshot

        snap = get_attendance_snapshot(employee)
        if snap.get("checked_in_today"):
            lines.append("✅ Checked in today" if lang == "English" else "✅ آج چیک ان ہو چکا")
        else:
            lines.append("⏳ Not checked in yet" if lang == "English" else "⏳ ابھی چیک ان نہیں")
    except Exception:
        pass

    # Pending leave requests
    try:
        pending_leave = frappe.db.count(
            "Leave Application",
            {"employee": employee, "docstatus": 0},
        )
        if pending_leave:
            lines.append(f"📝 {pending_leave} leave request(s) pending approval")
    except Exception:
        pass

    # Upcoming travel
    try:
        from frappe.utils import today

        upcoming = frappe.db.count(
            "Travel Authorisation Request Form",
            {
                "employee": employee,
                "docstatus": 1,
                "from_date": [">=", today()],
            },
        )
        if upcoming:
            lines.append(f"🚗 {upcoming} upcoming travel request(s)")
    except Exception:
        pass

    # HR requests
    try:
        if frappe.db.exists("DocType", "Employee Profile Change Request"):
            pending_hr = frappe.db.count(
                "Employee Profile Change Request",
                {"employee": employee, "status": ["not in", ["Applied", "Rejected"]]},
            )
            if pending_hr:
                lines.append(f"📋 {pending_hr} HR request(s) in progress")
    except Exception:
        pass

    if len(lines) <= 2:
        lines.append("\nAll clear for now. Have a productive day!")

    buttons = [
        {"id": "svc_att_today", "title": "Attendance"},
        {"id": "svc_leave_requests", "title": "My Leave"},
        {"id": "svc_main_menu", "title": "Main Menu"},
    ]
    return build_button_message("\n".join(lines), buttons)
