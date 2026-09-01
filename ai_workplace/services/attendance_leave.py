"""
ai_workplace/services/attendance_leave.py
───────────────────────────────────────────
Service handlers for Attendance & Leave options:
- att_today: Today's check-in/out status & working hours
- att_monthly: Monthly attendance summary
- att_missing: Missing punches & unrecorded attendance dates
- leave_balance: Leave allocation & remaining balances
- leave_apply: Leave application prompt & instructions
- leave_requests: Recent leave application statuses
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, date

import frappe
from frappe.utils import today, getdate, formatdate, flt, add_months, get_first_day, get_last_day, add_days


def get_today_attendance_data(employee_id: Optional[str]) -> dict[str, Any]:
    """Fetch today's attendance & check-in logs for employee."""
    res: dict[str, Any] = {
        "date": today(),
        "status": "Not Checked In",
        "in_time": "N/A",
        "out_time": "N/A",
        "working_hours": "0.00",
        "late_entry": False,
        "early_exit": False,
        "logs_count": 0,
    }
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return res

        curr_date = today()

        # 1. Check processed Attendance record
        att_list = frappe.db.get_all(
            "Attendance",
            filters={"employee": employee_id, "attendance_date": curr_date, "docstatus": ["!=", 2]},
            fields=["status", "in_time", "out_time", "working_hours", "late_entry", "early_exit", "leave_type"],
            limit=1,
        )

        if att_list:
            att = att_list[0]
            res["status"] = att.get("status") or "Present"
            if att.get("leave_type"):
                res["status"] = f"On Leave ({att['leave_type']})"
            res["late_entry"] = bool(att.get("late_entry"))
            res["early_exit"] = bool(att.get("early_exit"))
            res["working_hours"] = f"{flt(att.get('working_hours', 0)):.2f}"
            if att.get("in_time"):
                res["in_time"] = format_time(att["in_time"])
            if att.get("out_time"):
                res["out_time"] = format_time(att["out_time"])

        # 2. Check raw Employee Checkins for today to complement or set status
        checkins = frappe.db.get_all(
            "Employee Checkin",
            filters={"employee": employee_id, "time": ["between", [f"{curr_date} 00:00:00", f"{curr_date} 23:59:59"]]},
            fields=["time", "log_type"],
            order_by="time asc",
        )

        if checkins:
            res["logs_count"] = len(checkins)
            if res["in_time"] == "N/A":
                res["in_time"] = format_time(checkins[0]["time"])
            if len(checkins) > 1 and res["out_time"] == "N/A":
                res["out_time"] = format_time(checkins[-1]["time"])

            if res["status"] == "Not Checked In":
                res["status"] = "Checked In" if len(checkins) == 1 else "Checked Out"

        return res
    except Exception:
        return res


def get_monthly_attendance_data(employee_id: Optional[str]) -> dict[str, Any]:
    """Fetch monthly attendance statistics for the current month."""
    curr_today = today()
    first_day = str(get_first_day(curr_today))
    last_day = curr_today

    res: dict[str, Any] = {
        "month_name": formatdate(curr_today, "MMMM YYYY"),
        "total_days": 0,
        "present": 0,
        "absent": 0,
        "leave": 0,
        "half_day": 0,
        "total_hours": 0.0,
        "late_entries": 0,
    }

    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return res

        att_records = frappe.db.get_all(
            "Attendance",
            filters={"employee": employee_id, "attendance_date": ["between", [first_day, last_day]], "docstatus": ["!=", 2]},
            fields=["status", "working_hours", "late_entry"],
        )

        res["total_days"] = len(att_records)
        for rec in att_records:
            st = rec.get("status")
            res["total_hours"] += flt(rec.get("working_hours", 0))
            if rec.get("late_entry"):
                res["late_entries"] += 1

            if st in ("Present", "Work From Home"):
                res["present"] += 1
            elif st == "Absent":
                res["absent"] += 1
            elif st in ("On Leave", "Half Day"):
                if st == "Half Day":
                    res["half_day"] += 1
                res["leave"] += 1

        return res
    except Exception:
        return res


def get_missing_attendance_data(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Identify missing punches or unrecorded attendance in the last 30 days."""
    missing: list[dict[str, Any]] = []
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return missing

        curr_today = today()
        start_date = str(add_months(curr_today, -1))

        # Check days marked Absent without leave application
        absents = frappe.db.get_all(
            "Attendance",
            filters={"employee": employee_id, "attendance_date": ["between", [start_date, curr_today]], "status": "Absent", "docstatus": ["!=", 2]},
            fields=["attendance_date", "status"],
            order_by="attendance_date desc",
            limit=5,
        )

        for ab in absents:
            missing.append({
                "date": formatdate(ab["attendance_date"], "dd MMM YYYY"),
                "reason": "Marked Absent (No punch / no leave logged)",
            })

        return missing
    except Exception:
        return missing


def get_leave_balance_data(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Fetch active leave allocations and remaining balances accurately."""
    balances: list[dict[str, Any]] = []
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return balances

        curr_today = today()
        allocations = frappe.db.get_all(
            "Leave Allocation",
            filters={"employee": employee_id, "to_date": [">=", curr_today], "docstatus": 1},
            fields=["leave_type", "total_leaves_allocated", "from_date", "to_date"],
            order_by="leave_type asc",
        )

        for alloc in allocations:
            leave_type = alloc.get("leave_type")
            allocated = flt(alloc.get("total_leaves_allocated", 0))
            
            # Query approved Leave Application records for this allocation period
            taken_records = frappe.db.get_all(
                "Leave Application",
                filters={
                    "employee": employee_id,
                    "leave_type": leave_type,
                    "status": "Approved",
                    "docstatus": 1,
                    "from_date": [">=", alloc.get("from_date")],
                    "to_date": ["<=", alloc.get("to_date")],
                },
                fields=["total_leave_days"]
            )
            taken = sum(flt(r.get("total_leave_days", 0)) for r in taken_records)
            remaining = max(0.0, allocated - taken)

            balances.append({
                "leave_type": leave_type or "General Leave",
                "allocated": f"{allocated:.1f}",
                "taken": f"{taken:.1f}",
                "remaining": f"{remaining:.1f}",
            })

        return balances
    except Exception:
        return balances


def get_recent_leave_requests(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Fetch recent leave applications and their status."""
    requests: list[dict[str, Any]] = []
    try:
        if not employee_id or not getattr(frappe, "db", None) or not frappe.db.exists("Employee", employee_id):
            return requests

        apps = frappe.db.get_all(
            "Leave Application",
            filters={"employee": employee_id, "docstatus": ["!=", 2]},
            fields=["leave_type", "from_date", "to_date", "total_leave_days", "status"],
            order_by="creation desc",
            limit=5,
        )

        for app in apps:
            requests.append({
                "leave_type": app.get("leave_type") or "Leave",
                "from_date": formatdate(app.get("from_date"), "dd MMM"),
                "to_date": formatdate(app.get("to_date"), "dd MMM YYYY"),
                "total_days": f"{flt(app.get('total_leave_days', 1)):.1f}",
                "status": app.get("status") or "Open",
            })

        return requests
    except Exception:
        return requests


def format_time(time_val: Any) -> str:
    """Format time string or datetime object into hh:mm AM/PM format."""
    if not time_val:
        return "N/A"
    try:
        if isinstance(time_val, str):
            if " " in time_val:
                dt = datetime.strptime(time_val.split(".")[0], "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(time_val.split(".")[0], "%H:%M:%S")
            return dt.strftime("%I:%M %p")
        elif isinstance(time_val, (datetime, date)):
            return time_val.strftime("%I:%M %p")
    except Exception:
        pass
    return str(time_val)


def format_date_safe(d_val: Any, fmt_str: str = "%d %B %Y") -> str:
    """Safely format date without requiring frappe.local context."""
    if not d_val:
        return "N/A"
    try:
        if isinstance(d_val, str):
            d_val = getdate(d_val)
        if isinstance(d_val, (date, datetime)):
            return d_val.strftime(fmt_str)
    except Exception:
        pass
    return str(d_val)


# ── Response Builders ──────────────────────────────────────────

from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage


def build_today_attendance_outbound(context: dict[str, Any]) -> OutboundMessage:
    """Today's attendance with Check In / Check Out action buttons when eligible."""
    body = build_today_attendance_response(context)
    buttons = [{"id": "svc_att_monthly", "title": "Monthly Attendance"}, {"id": "svc_main_menu", "title": "Main Menu"}]

    employee = context.get("employee") or ""
    try:
        from ai_workplace.services.attendance_location import (
            get_attendance_eligibility,
            get_today_checkin_state,
        )

        eligibility = get_attendance_eligibility(employee, user_id=context.get("user"))
        if eligibility.get("eligible"):
            state = get_today_checkin_state(employee)
            if state.get("checked_in_open"):
                buttons = [
                    {"id": "svc_att_checkout", "title": "Check Out"},
                    {"id": "svc_att_today", "title": "Refresh"},
                    {"id": "svc_main_menu", "title": "Main Menu"},
                ]
            elif not state.get("checked_out_today"):
                buttons = [
                    {"id": "svc_att_checkin", "title": "Check In"},
                    {"id": "svc_att_monthly", "title": "Monthly"},
                    {"id": "svc_main_menu", "title": "Main Menu"},
                ]
    except Exception:
        pass

    return build_button_message(body, buttons[:3])


def build_today_attendance_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Today's Attendance."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    data = get_today_attendance_data(emp_id)

    curr_date_str = format_date_safe(data["date"], "%d %B %Y")

    if lang == "Urdu":
        status_ur = {
            "Present": "موجود (Present)",
            "Absent": "غیر حاضر (Absent)",
            "Checked In": "چیک ان (Checked In)",
            "Checked Out": "چیک آؤٹ (Checked Out)",
            "Not Checked In": "ابھی چیک ان نہیں کیا",
        }.get(data["status"], data["status"])

        return (
            f"📅 *آج کی حاضری ({curr_date_str})*\n\n"
            f"👤 **ملازم کا نام:** {context.get('full_name', 'Employee')}\n"
            f"📊 **حالت:** {status_ur}\n"
            f"⏰ **چیک ان وقت:** {data['in_time']}\n"
            f"🚪 **چیک آؤٹ وقت:** {data['out_time']}\n"
            f"⏱️ **کل کام کے اوقات:** {data['working_hours']} گھنٹے\n\n"
            f"💡 *کسی بھی غلطی کی صورت میں اپنے لائن مینیجر یا ایچ آر سے رابطہ کریں۔*"
        )

    if lang == "Roman Urdu":
        return (
            f"📅 *Aaj Ki Attendance ({curr_date_str})*\n\n"
            f"👤 **Employee:** {context.get('full_name', 'Employee')}\n"
            f"📊 **Status:** {data['status']}\n"
            f"⏰ **Check-In Time:** {data['in_time']}\n"
            f"🚪 **Check-Out Time:** {data['out_time']}\n"
            f"⏱️ **Total Working Hours:** {data['working_hours']} Hours\n\n"
            f"💡 *Kisi bhi maslay ki soorat mein apne line manager se rabta karein.*"
        )

    # Default: English
    return (
        f"📅 *Today's Attendance ({curr_date_str})*\n\n"
        f"👤 **Employee:** {context.get('full_name', 'Employee')}\n"
        f"📊 **Status:** {data['status']}\n"
        f"⏰ **Check-In Time:** {data['in_time']}\n"
        f"🚪 **Check-Out Time:** {data['out_time']}\n"
        f"⏱️ **Total Working Hours:** {data['working_hours']} hrs\n\n"
        f"💡 *If you notice any discrepancy, please contact your Line Manager or HR.*"
    )


def build_monthly_attendance_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Monthly Attendance summary."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    data = get_monthly_attendance_data(emp_id)

    if lang == "Urdu":
        return (
            f"🗓️ *ماہانہ حاضری رپورٹ ({data['month_name']})*\n\n"
            f"👤 **ملازم کا نام:** {context.get('full_name', 'Employee')}\n"
            f"✅ **موجود دن (Present):** {data['present']} دن\n"
            f"❌ **غیر حاضر دن (Absent):** {data['absent']} دن\n"
            f"🏖️ **چھٹیاں (Leaves):** {data['leave']} دن\n"
            f"⏱️ **کل ریکارڈر اوقات:** {data['total_hours']:.1f} گھنٹے"
        )

    if lang == "Roman Urdu":
        return (
            f"🗓️ *Monthly Attendance Summary ({data['month_name']})*\n\n"
            f"👤 **Employee:** {context.get('full_name', 'Employee')}\n"
            f"✅ **Present Days:** {data['present']} days\n"
            f"❌ **Absent Days:** {data['absent']} days\n"
            f"🏖️ **Leaves Taken:** {data['leave']} days\n"
            f"⏱️ **Total Recorded Hours:** {data['total_hours']:.1f} hrs"
        )

    return (
        f"🗓️ *Monthly Attendance Summary ({data['month_name']})*\n\n"
        f"👤 **Employee:** {context.get('full_name', 'Employee')}\n"
        f"✅ **Present Days:** {data['present']}\n"
        f"❌ **Absent Days:** {data['absent']}\n"
        f"🏖️ **Leaves Taken:** {data['leave']}\n"
        f"⏱️ **Total Recorded Hours:** {data['total_hours']:.1f} hrs"
    )


def _attendance_detail_fields() -> list[str]:
    fields = [
        "name",
        "attendance_date",
        "status",
        "in_time",
        "out_time",
        "working_hours",
        "leave_type",
    ]
    for col in ("check_in", "check_out", "task_description", "total_worked_time"):
        if frappe.db.has_column("Attendance", col):
            fields.append(col)
    return fields


def _pick_time_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        val = record.get(key)
        if val:
            return val
    return None


def _get_checkins_for_date(employee_id: str, att_date: date) -> list[dict[str, Any]]:
    date_str = str(att_date)
    return frappe.db.get_all(
        "Employee Checkin",
        filters={
            "employee": employee_id,
            "time": ["between", [f"{date_str} 00:00:00", f"{date_str} 23:59:59"]],
        },
        fields=["time", "log_type"],
        order_by="time asc",
    )


def get_day_attendance_detail(employee_id: str, att_date: date) -> dict[str, Any]:
    """Build one day's attendance detail for chat or export."""
    detail: dict[str, Any] = {
        "date": att_date,
        "date_label": formatdate(att_date, "EEE dd MMM"),
        "status": "No Record",
        "in_time": "",
        "out_time": "",
        "hours": "",
        "task": "",
    }
    if not employee_id:
        return detail

    records = frappe.db.get_all(
        "Attendance",
        filters={
            "employee": employee_id,
            "attendance_date": att_date,
            "docstatus": ["!=", 2],
        },
        fields=_attendance_detail_fields(),
        limit=1,
    )

    if records:
        rec = records[0]
        status = rec.get("status") or "Present"
        if rec.get("leave_type"):
            status = f"On Leave ({rec['leave_type']})"
        detail["status"] = status

        in_raw = _pick_time_value(rec, "in_time", "check_in")
        out_raw = _pick_time_value(rec, "out_time", "check_out")
        if in_raw:
            detail["in_time"] = format_time(in_raw)
        if out_raw:
            detail["out_time"] = format_time(out_raw)

        hours = rec.get("working_hours")
        if hours is None and rec.get("total_worked_time"):
            hours = rec.get("total_worked_time")
        if flt(hours):
            detail["hours"] = f"{flt(hours):.1f}"

        task = (rec.get("task_description") or "").strip()
        if task:
            detail["task"] = task[:200]

    if not detail["in_time"] or not detail["out_time"]:
        checkins = _get_checkins_for_date(employee_id, att_date)
        if checkins:
            if not detail["in_time"]:
                detail["in_time"] = format_time(checkins[0]["time"])
            if not detail["out_time"] and len(checkins) > 1:
                detail["out_time"] = format_time(checkins[-1]["time"])
            if detail["status"] == "No Record":
                detail["status"] = "Present"

    return detail


def get_last_working_days_attendance(employee_id: Optional[str], count: int = 7) -> list[dict[str, Any]]:
    """Return attendance details for the last N weekdays (Mon–Fri), newest first."""
    if not employee_id:
        return []

    results: list[dict[str, Any]] = []
    cursor = getdate(today())
    scanned = 0
    while len(results) < count and scanned < 90:
        if cursor.weekday() < 5:
            results.append(get_day_attendance_detail(employee_id, cursor))
        cursor = add_days(cursor, -1)
        scanned += 1
    return results


def get_month_to_date_attendance(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """All weekday attendance details from month start through today."""
    if not employee_id:
        return []

    curr = getdate(today())
    start = getdate(get_first_day(curr))
    details: list[dict[str, Any]] = []
    day = start
    while day <= curr:
        if day.weekday() < 5:
            details.append(get_day_attendance_detail(employee_id, day))
        day = add_days(day, 1)
    return details


def _status_emoji(status: str) -> str:
    st = (status or "").lower()
    if "absent" in st:
        return "❌"
    if "leave" in st:
        return "🏖️"
    if st in ("present", "work from home", "checked in", "checked out"):
        return "✅"
    if st == "no record":
        return "➖"
    return "📌"


def _format_day_line(day: dict[str, Any], lang: str) -> str:
    emoji = _status_emoji(day.get("status") or "")
    header = f"{emoji} *{day.get('date_label')}* | {day.get('status')}"
    lines = [header]

    if day.get("in_time") or day.get("out_time"):
        in_t = day.get("in_time") or "—"
        out_t = day.get("out_time") or "—"
        time_line = f"  IN {in_t}  OUT {out_t}"
        if day.get("hours"):
            suffix = f"  |  {day['hours']} hrs"
            if lang == "Urdu":
                suffix = f"  |  {day['hours']} گھنٹے"
            time_line += suffix
        lines.append(time_line)

    if day.get("task"):
        prefix = "  📋 Task: " if lang != "Urdu" else "  📋 "
        lines.append(f"{prefix}{day['task']}")

    return "\n".join(lines)


def build_last7_attendance_response(context: dict[str, Any]) -> str:
    """Build chat message for last 7 working days."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    days = get_last_working_days_attendance(emp_id, 7)

    if lang == "Urdu":
        title = "📋 *پچھلے 7 کام کے دن*"
        empty = "📋 *پچھلے 7 کام کے دن*\n\nکوئی حاضری کا ریکارڈ نہیں ملا۔"
    elif lang == "Roman Urdu":
        title = "📋 *Last 7 Working Days*"
        empty = "📋 *Last 7 Working Days*\n\nKoi attendance record nahi mila."
    else:
        title = "📋 *Last 7 Working Days*"
        empty = "📋 *Last 7 Working Days*\n\nNo attendance records found."

    if not days:
        return empty

    body_lines = [_format_day_line(day, lang) for day in days]
    return f"{title}\n\n" + "\n\n".join(body_lines)


def generate_monthly_attendance_excel(employee_id: str, employee_name: str = "") -> tuple[bytes, str]:
    """Generate Excel bytes for current month attendance (weekdays only)."""
    from frappe.utils.xlsxutils import make_xlsx

    curr = getdate(today())
    month_label = formatdate(curr, "MMMM_YYYY")
    days = get_month_to_date_attendance(employee_id)

    rows: list[list[Any]] = [
        ["Date", "Day", "Status", "Check In", "Check Out", "Hours", "Task"],
    ]
    for day in days:
        rows.append([
            formatdate(day["date"], "yyyy-MM-dd"),
            formatdate(day["date"], "EEEE"),
            day.get("status") or "",
            day.get("in_time") or "",
            day.get("out_time") or "",
            day.get("hours") or "",
            day.get("task") or "",
        ])

    safe_name = (employee_name or employee_id or "Employee").replace("/", "-").replace(" ", "_")
    filename = f"Attendance_{safe_name}_{month_label}.xlsx"
    xlsx = make_xlsx(rows, "Attendance")
    content = xlsx.getvalue() if hasattr(xlsx, "getvalue") else bytes(xlsx)
    return content, filename


def build_monthly_download_caption(context: dict[str, Any]) -> str:
    """Caption sent with the monthly Excel file."""
    lang = context.get("preferred_language", "English")
    month_name = formatdate(today(), "MMMM YYYY")
    if lang == "Urdu":
        return (
            f"📥 *{month_name}* کی مکمل حاضری Excel فائل منسلک ہے۔\n"
            f"کالم: تاریخ | حالت | Check In | Check Out | گھنٹے | Task"
        )
    if lang == "Roman Urdu":
        return (
            f"📥 *{month_name}* ki full attendance Excel file attached hai.\n"
            f"Columns: Date | Status | Check In | Check Out | Hours | Task"
        )
    return (
        f"📥 Your *{month_name}* attendance sheet is attached (Excel).\n"
        f"Columns: Date | Status | Check In | Check Out | Hours | Task"
    )


def build_monthly_download_error(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        return "معذرت، Excel فائل بن نہیں سکی۔ براہ کرم دوبارہ کوشش کریں یا HR سے رابطہ کریں۔"
    if lang == "Roman Urdu":
        return "Maazrat, Excel file generate nahi ho saki. Dobara koshish karein ya HR se rabta karein."
    return "Sorry, we couldn't generate your Excel file. Please try again or contact HR."


def build_missing_attendance_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Missing Attendance / Punch Regularization."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    missing = get_missing_attendance_data(emp_id)

    if lang == "Urdu":
        if not missing:
            return (
                "⚠️ *گمشدہ حاضری (Missing Attendance)*\n\n"
                "✅ پچھلے 30 دنوں میں آپ کی کوئی حاضری یا پنش مسنگ نہیں ہے۔"
            )
        lines = [f"• **{m['date']}**: {m['reason']}" for m in missing]
        missing_str = "\n".join(lines)
        return (
            f"⚠️ *گمشدہ حاضری کی تفصیل (Missing Attendance)*\n\n"
            f"مندرجہ ذیل تاریخوں میں حاضری کا اندراج مکمل نہیں ہے:\n\n"
            f"{missing_str}\n\n"
            f"💡 *براہ کرم باقاعدگی (Regularization) درخواست اپنے سپروائزر کو جمع کروائیں۔*"
        ) + _att_missing_footer(context, emp_id)

    if lang == "Roman Urdu":
        if not missing:
            return (
                "⚠️ *Missing Attendance*\n\n"
                "✅ pichlay 30 dinon mein aap ki koi missing attendance nahi hai."
            )
        lines = [f"• **{m['date']}**: {m['reason']}" for m in missing]
        missing_str = "\n".join(lines)
        return (
            f"⚠️ *Missing Attendance Log*\n\n"
            f"In dates par aap ki attendance complete nahi hai:\n\n"
            f"{missing_str}\n\n"
            f"💡 *Regularization request apne supervisor ko submit karein.*"
        ) + _att_missing_footer(context, emp_id)

    # Default: English
    if not missing:
        return (
            "⚠️ *Missing Attendance*\n\n"
            "✅ Great! You have no missing punches or unrecorded attendance in the last 30 days."
        )
    lines = [f"• **{m['date']}**: {m['reason']}" for m in missing]
    missing_str = "\n".join(lines)
    return (
        f"⚠️ *Missing Attendance Discrepancies*\n\n"
        f"The following dates require attendance regularization:\n\n"
        f"{missing_str}\n\n"
        f"💡 *Please contact your supervisor or submit an Attendance Regularization request.*"
    ) + _att_missing_footer(context, emp_id)


def _att_missing_footer(context: dict[str, Any], emp_id: str | None) -> str:
    if not emp_id:
        return ""
    try:
        from ai_workplace.services.attendance_guidance import build_att_missing_footer

        return build_att_missing_footer(context, emp_id)
    except Exception:
        return ""


def build_leave_balance_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Leave Balances."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    balances = get_leave_balance_data(emp_id)

    if lang == "Urdu":
        if not balances:
            return (
                "📊 *چھٹیوں کا بقایا (Leave Balance)*\n\n"
                "فی الحال آپ کا کوئی ایکٹیو لیو ایلوکیشن نہیں ملا۔"
            )
        lines = [
            f"📌 **{b['leave_type']}**\n   مجموعی: {b['allocated']} | استعمال شدہ: {b['taken']} | **بقیہ: {b['remaining']}**"
            for b in balances
        ]
        bal_str = "\n\n".join(lines)
        return (
            f"📊 *آپ کی چھٹیوں کی تفصیل (Leave Balance)*\n\n"
            f"{bal_str}\n\n"
            f"💡 *چھٹی اپلائی کرنے کے لیے 'Apply for Leave' مینو منتخب کریں۔*"
        )

    if lang == "Roman Urdu":
        if not balances:
            return (
                "📊 *Leave Balance*\n\n"
                "Filhaal aap ka koi active leave allocation nahi mila."
            )
        lines = [
            f"📌 **{b['leave_type']}**\n   Allocated: {b['allocated']} | Used: {b['taken']} | **Remaining: {b['remaining']}**"
            for b in balances
        ]
        bal_str = "\n\n".join(lines)
        return (
            f"📊 *Aap Ka Leave Balance Summary*\n\n"
            f"{bal_str}\n\n"
            f"💡 *Chhutti apply karne ke liye 'Apply for Leave' select karein.*"
        )

    # Default: English
    if not balances:
        return (
            "📊 *Leave Balance*\n\n"
            "No active leave allocations were found for your employee record."
        )
    lines = [
        f"📌 **{b['leave_type']}**\n   Allocated: {b['allocated']} | Used: {b['taken']} | **Remaining: {b['remaining']}**"
        for b in balances
    ]
    bal_str = "\n\n".join(lines)
    return (
        f"📊 *Your Leave Balance Summary*\n\n"
        f"{bal_str}\n\n"
        f"💡 *To request leave, select 'Apply for Leave' from the Attendance & Leave menu.*"
    )


def build_apply_leave_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Apply for Leave instruction/prompt."""
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        return (
            "📝 *چھٹی کی درخواست (Apply for Leave)*\n\n"
            "چھٹی کی درخواست کے لیے درج ذیل تفصیلات فراہم کریں:\n"
            "1️⃣ **چھٹی کی قسم:** (Casual / Sick / Annual)\n"
            "2️⃣ **شروعاتی تاریخ:** (مثلاً 01-Sep-2026)\n"
            "3️⃣ **آخری تاریخ:** (مثلاً 03-Sep-2026)\n"
            "4️⃣ **وجہ:** (مختصر تفصیل)\n\n"
            "💡 *یا آپ ایچ آر پورٹل سے براہِ راست بھی چھٹی کی درخواست جمع کروا سکتے ہیں۔*"
        )

    if lang == "Roman Urdu":
        return (
            "📝 *Apply for Leave*\n\n"
            "Chhutti apply karne ke liye yeh details faraham karein:\n"
            "1️⃣ **Leave Type:** (Casual / Sick / Annual)\n"
            "2️⃣ **From Date:** (e.g. 01-Sep-2026)\n"
            "3️⃣ **To Date:** (e.g. 03-Sep-2026)\n"
            "4️⃣ **Reason:** (Mukhtasar waja)\n\n"
            "💡 *Aap direct HR portal se bhi leave application submit kar sakte hain.*"
        )

    # Default: English
    return (
        "📝 *Apply for Leave*\n\n"
        "To submit a new leave application, please prepare the following details:\n"
        "1️⃣ **Leave Type:** (Casual / Sick / Annual)\n"
        "2️⃣ **From Date:** (e.g. 01-Sep-2026)\n"
        "3️⃣ **To Date:** (e.g. 03-Sep-2026)\n"
        "4️⃣ **Reason:** (Brief description)\n\n"
        "💡 *You can also apply directly through the MicroMerger HR Employee Self-Service Portal.*"
    )


def build_leave_requests_response(context: dict[str, Any]) -> str:
    """Build multi-lingual response for Recent Leave Requests."""
    lang = context.get("preferred_language", "English")
    emp_id = context.get("employee")
    reqs = get_recent_leave_requests(emp_id)

    status_icon = {
        "Approved": "🟢 Approved",
        "Open": "⏳ Open (Pending Approval)",
        "Rejected": "🔴 Rejected",
        "Cancelled": "⚪ Cancelled",
    }

    if lang == "Urdu":
        if not reqs:
            return (
                "📋 *میرے لیو کی درخواستیں (My Leave Requests)*\n\n"
                "آپ کی حال ہی میں کوئی جمع کروائی گئی چھٹی کی درخواست نہیں مل سکی۔"
            )
        lines = [
            f"• **{r['leave_type']}** ({r['from_date']} - {r['to_date']})\n  دن: {r['total_days']} | حالت: {status_icon.get(r['status'], r['status'])}"
            for r in reqs
        ]
        req_str = "\n\n".join(lines)
        return (
            f"📋 *حالیہ چھٹی کی درخواستوں کی رپورٹ*\n\n"
            f"{req_str}\n\n"
            f"💡 *مزید معلومات کے لیے اپنے مینیجر یا ایچ آر سے رابطہ کریں۔*"
        )

    if lang == "Roman Urdu":
        if not reqs:
            return (
                "📋 *My Leave Requests*\n\n"
                "Aap ki haal hi mein koi submit ki gayi leave application nahi mili."
            )
        lines = [
            f"• **{r['leave_type']}** ({r['from_date']} - {r['to_date']})\n  Days: {r['total_days']} | Status: {status_icon.get(r['status'], r['status'])}"
            for r in reqs
        ]
        req_str = "\n\n".join(lines)
        return (
            f"📋 *Recent Leave Applications*\n\n"
            f"{req_str}\n\n"
            f"💡 *Approval status monitor karne ke liye HR portal dekhein.*"
        )

    # Default: English
    if not reqs:
        return (
            "📋 *My Leave Requests*\n\n"
            "You have no recently submitted leave applications."
        )
    lines = [
        f"• **{r['leave_type']}** ({r['from_date']} - {r['to_date']})\n  Days: {r['total_days']} | Status: {status_icon.get(r['status'], r['status'])}"
        for r in reqs
    ]
    req_str = "\n\n".join(lines)
    return (
        f"📋 *Recent Leave Applications Status*\n\n"
        f"{req_str}\n\n"
        f"💡 *For urgent approvals, please reach out to your designated Leave Approver.*"
    )
