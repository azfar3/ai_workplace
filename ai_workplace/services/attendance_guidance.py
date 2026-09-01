"""
Attendance guidance for proactive nudges and agent tools.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import frappe


def get_attendance_snapshot(employee_id: str) -> dict[str, Any]:
    today = frappe.utils.today()
    checked_in_today = bool(
        frappe.db.exists("Employee Checkin", {"employee": employee_id, "time": [">=", today]})
        or frappe.db.exists("Attendance", {"employee": employee_id, "attendance_date": today, "status": "Present"})
    )

    missing_days = 0
    try:
        from ai_workplace.services.attendance_leave import get_missing_attendance_data

        missing = get_missing_attendance_data(employee_id) or []
        missing_days = len(missing)
    except Exception:
        pass

    mobile_attendance = frappe.db.get_value("Employee", employee_id, "mobile_attendance") or 0
    whatsapp_enabled = False
    try:
        from ai_workplace.services.attendance_location import get_attendance_eligibility

        whatsapp_enabled = bool(
            get_attendance_eligibility(
                employee_id,
                user_id=frappe.db.get_value("Employee", employee_id, "user_id"),
            ).get("eligible")
        )
    except Exception:
        pass

    return {
        "employee": employee_id,
        "checked_in_today": checked_in_today,
        "missing_days_last_period": missing_days,
        "mobile_attendance_enabled": bool(mobile_attendance),
        "whatsapp_attendance_enabled": whatsapp_enabled,
        "guidance": _guidance(checked_in_today, missing_days, mobile_attendance, whatsapp_enabled),
        "portal_checkin_url": frappe.utils.get_url("/hrms"),
    }


def _guidance(checked_in: bool, missing_days: int, mobile_attendance: int, whatsapp_enabled: bool = False) -> str:
    parts = []
    if not checked_in:
        if whatsapp_enabled:
            parts.append("You have not checked in today. Use *Check In* from the Attendance menu and share your location.")
        else:
            parts.append("You have not checked in today. Use the HRMIS Portal or mobile app to check in.")
    if missing_days > 0:
        parts.append(f"You have {missing_days} missing attendance day(s). Contact your supervisor or use Attendance Request in Portal.")
    if mobile_attendance:
        parts.append("Mobile attendance is enabled on your profile.")
    return " ".join(parts) if parts else "Your attendance looks up to date for today."


def build_att_missing_footer(context: dict[str, Any], employee_id: str) -> str:
    """Polished footer for att_missing handler."""
    snap = get_attendance_snapshot(employee_id)
    base = snap.get("guidance", "")
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return f"\n\n📌 *رہنمائی:* {base}"
    return f"\n\n📌 *Guidance:* {base}"
