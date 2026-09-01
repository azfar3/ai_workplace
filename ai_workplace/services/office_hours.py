"""
ai_workplace/services/office_hours.py
───────────────────────────────────────
HR office hours availability checks for live chat.

Uses authoritative server time (`frappe.utils.now_datetime`), office timezone,
configured working days/hours, and ERPNext Holiday List (Company default).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone, now_datetime

_DEFAULT_TIMEZONE = "Asia/Karachi"
_DEFAULT_START = "09:00:00"
_DEFAULT_END = "18:00:00"
_DEFAULT_OFF_HOURS_MESSAGE = (
    "Our HR team is currently offline.\n\n"
    "Please leave your message and an HR representative will respond during working hours.\n\n"
    "Monday to Friday | 9:00 AM – 6:00 PM (Pakistan Time)"
)

DAY_ABBR_TO_NAME = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday",
}

HR_STATUS_OPEN = "OPEN"
HR_STATUS_CLOSED = "CLOSED"


def _get_settings() -> Any:
    return frappe.get_single("AI Workplace Settings")


def _time_to_seconds(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, str):
        parts = value.split(":")
        if len(parts) >= 2:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) > 2 else 0
            return hours * 3600 + minutes * 60 + seconds
    return 0


def _get_day_schedule(settings: Any, weekday_name: str) -> Optional[dict[str, Any]]:
    """Return working-day row dict for a weekday name like 'Monday'."""
    rows = settings.get("hr_working_days") or []
    for row in rows:
        if row.day_of_week == weekday_name:
            return {
                "is_working_day": bool(row.is_working_day),
                "start_time": row.start_time,
                "end_time": row.end_time,
            }
    return None


def _legacy_day_schedule(settings: Any, weekday_abbr: str) -> Optional[dict[str, Any]]:
    """Fallback for older settings that used comma-separated day abbreviations."""
    allowed_days = [
        d.strip()
        for d in (settings.get("office_days") or "Mon,Tue,Wed,Thu,Fri").split(",")
        if d.strip()
    ]
    if allowed_days and weekday_abbr not in allowed_days:
        return {"is_working_day": False, "start_time": None, "end_time": None}
    return {
        "is_working_day": True,
        "start_time": settings.get("office_start_time"),
        "end_time": settings.get("office_end_time"),
    }


def get_office_timezone() -> ZoneInfo:
    """Return configured office timezone (default Asia/Karachi / PKT)."""
    settings = _get_settings()
    tz_name = settings.get("office_timezone") or _DEFAULT_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo(_DEFAULT_TIMEZONE)


def get_office_now(now: Optional[datetime] = None) -> datetime:
    """
    Current datetime in configured office timezone.
    When `now` is omitted, uses authoritative server time from Frappe.
    """
    tz_office = get_office_timezone()
    if now is not None:
        if now.tzinfo is None:
            return now.replace(tzinfo=tz_office)
        return now.astimezone(tz_office)

    server_naive = now_datetime()
    try:
        system_tz = ZoneInfo(get_system_timezone())
    except Exception:
        system_tz = ZoneInfo(_DEFAULT_TIMEZONE)
    server_aware = server_naive.replace(tzinfo=system_tz)
    return server_aware.astimezone(tz_office)


def get_hr_holiday_list(employee: Optional[str] = None, company: Optional[str] = None) -> Optional[str]:
    """
    Resolve applicable ERPNext Holiday List for HR support availability.
    Uses Company.default_holiday_list (employee company → global default company).
    """
    if not company and employee:
        company = frappe.db.get_value("Employee", employee, "company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")
    if company:
        return frappe.db.get_value("Company", company, "default_holiday_list")
    return None


def is_hr_support_holiday(
    check_date: date | str | None = None,
    *,
    employee: Optional[str] = None,
    company: Optional[str] = None,
) -> bool:
    """Return True when the date is a holiday on the applicable ERPNext Holiday List."""
    if check_date is None:
        check_date = get_office_now().date()
    holiday_list = get_hr_holiday_list(employee=employee, company=company)
    if not holiday_list:
        return False
    try:
        from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

        return bool(is_holiday(holiday_list, check_date))
    except Exception:
        return bool(
            frappe.db.exists(
                "Holiday",
                {"parent": holiday_list, "holiday_date": check_date},
            )
        )


def get_hr_support_status(
    now: Optional[datetime] = None,
    *,
    employee: Optional[str] = None,
    company: Optional[str] = None,
) -> dict[str, Any]:
    """
    Determine whether HR Live Chat support is OPEN or CLOSED.

    OPEN only when: enabled + working day + not holiday + within hours.
    """
    office_now = get_office_now(now)
    schedule = get_working_schedule_for_datetime(office_now)
    holiday_list = get_hr_holiday_list(employee=employee, company=company)
    on_holiday = is_hr_support_holiday(office_now.date(), employee=employee, company=company)

    base = {
        "status": HR_STATUS_CLOSED,
        "is_open": False,
        "closed_reason": None,
        "holiday_list": holiday_list,
        "is_holiday": on_holiday,
        "is_working_day": bool(schedule and schedule.get("is_working_day")),
        "timezone": str(get_office_timezone()),
        "local_time": office_now.strftime("%I:%M %p"),
        "local_date": office_now.strftime("%A, %d %b %Y"),
        "local_datetime": office_now.isoformat(),
        "office_date": str(office_now.date()),
    }

    if not is_hr_live_chat_enabled():
        base["closed_reason"] = "disabled"
        return base

    if not schedule or not schedule.get("is_working_day"):
        base["closed_reason"] = "non_working_day"
        return base

    if on_holiday:
        base["closed_reason"] = "holiday"
        return base

    start_seconds = _time_to_seconds(schedule.get("start_time"))
    end_seconds = _time_to_seconds(schedule.get("end_time"))
    if end_seconds <= start_seconds:
        base["closed_reason"] = "outside_hours"
        return base

    current_seconds = office_now.hour * 3600 + office_now.minute * 60 + office_now.second
    if not (start_seconds <= current_seconds < end_seconds):
        base["closed_reason"] = "outside_hours"
        return base

    base.update(
        {
            "status": HR_STATUS_OPEN,
            "is_open": True,
            "closed_reason": None,
        }
    )
    return base


def get_office_hours_info(now: Optional[datetime] = None) -> dict[str, Any]:
    """Office-hours status for Desk UI, API, and logging."""
    status = get_hr_support_status(now)
    return {
        "is_office_hours": status["is_open"],
        "hr_support_status": status["status"],
        "closed_reason": status.get("closed_reason"),
        "is_holiday": status.get("is_holiday"),
        "holiday_list": status.get("holiday_list"),
        "is_working_day": status.get("is_working_day"),
        "timezone": status["timezone"],
        "local_time": status["local_time"],
        "local_date": status["local_date"],
        "local_datetime": status["local_datetime"],
    }


def get_working_schedule_for_datetime(
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """Return schedule row for the given datetime's weekday."""
    settings = _get_settings()
    office_now = get_office_now(now)

    weekday_name = office_now.strftime("%A")
    weekday_abbr = office_now.strftime("%a")

    schedule = _get_day_schedule(settings, weekday_name)
    if schedule is None and not settings.get("hr_working_days"):
        schedule = _legacy_day_schedule(settings, weekday_abbr)

    if schedule is None:
        # Default Mon-Fri 9-18 if day not configured in table.
        default_working = weekday_name in (
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
        )
        return {
            "is_working_day": default_working,
            "start_time": _DEFAULT_START,
            "end_time": _DEFAULT_END,
        }

    return schedule


def is_hr_live_chat_enabled() -> bool:
    try:
        settings = _get_settings()
        val = settings.get("hr_live_chat_enabled")
        if val is None:
            return True
        return bool(int(val))
    except Exception:
        return True


def is_hr_available(
    now: Optional[datetime] = None,
    *,
    employee: Optional[str] = None,
    company: Optional[str] = None,
) -> bool:
    """Return True when HR live chat is OPEN per configured rules."""
    return get_hr_support_status(now, employee=employee, company=company)["is_open"]


def build_open_hours_message(context: Optional[dict[str, Any]] = None) -> str:
    """Message when HR support is currently OPEN."""
    lang = (context or {}).get("preferred_language", "English")
    status = get_hr_support_status()
    hours_hint = _format_working_hours_hint(status)
    if lang == "Urdu":
        return (
            "🟢 *HR سپورٹ کھلی ہے*\n\n"
            "HR نمائندہ دستیاب ہے۔ نیچے *Chat with HR* منتخب کر کے بات شروع کریں۔"
            + (f"\n\n{hours_hint}" if hours_hint else "")
        )
    if lang == "Roman Urdu":
        return (
            "🟢 *HR Support open hai*\n\n"
            "HR representative available hai. Neeche *Chat with HR* select kar ke baat shuru karein."
            + (f"\n\n{hours_hint}" if hours_hint else "")
        )
    return (
        "🟢 *HR Support is open*\n\n"
        "An HR representative is available now. Tap *Chat with HR* below to start."
        + (f"\n\n{hours_hint}" if hours_hint else "")
    )


def build_closed_hours_message(
    context: Optional[dict[str, Any]] = None,
    *,
    employee: Optional[str] = None,
) -> str:
    """Message when HR support is CLOSED (off-hours, holiday, or non-working day)."""
    settings = _get_settings()
    configured = (settings.get("closed_office_hours_message") or "").strip()
    if configured:
        return configured

    status = get_hr_support_status(employee=employee)
    reason = status.get("closed_reason")
    lang = (context or {}).get("preferred_language", "English")

    if reason == "holiday":
        if lang == "Urdu":
            return (
                "🔴 *HR سپورٹ آج بند ہے*\n\n"
                "آج سرکاری/تعطیل کا دن ہے۔ آپ اپنا پیغام چھوڑ سکتے ہیں "
                "اور HR نمائندہ کام کے اوقات میں جواب دے گا۔"
            )
        if lang == "Roman Urdu":
            return (
                "🔴 *HR Support aaj band hai*\n\n"
                "Aaj holiday hai. Aap apna message chhor sakte hain "
                "aur HR representative working hours mein jawab dega."
            )
        return (
            "🔴 *HR Support is closed today*\n\n"
            "Today is a scheduled holiday. You can still leave your message "
            "and an HR representative will respond during working hours."
        )

    if reason == "non_working_day":
        if lang == "Urdu":
            return (
                "🔴 *HR سپورٹ آج بند ہے*\n\n"
                "آج کام کا دن نہیں ہے۔ آپ اپنا پیغام چھوڑ سکتے ہیں "
                "اور HR نمائندہ اگلے کام کے دن جواب دے گا۔"
            )
        if lang == "Roman Urdu":
            return (
                "🔴 *HR Support aaj band hai*\n\n"
                "Aaj working day nahi hai. Aap message chhor sakte hain "
                "aur HR representative agle working day jawab dega."
            )
        return (
            "🔴 *HR Support is closed today*\n\n"
            "Today is not an HR support working day. You can still leave your message "
            "and an HR representative will respond on the next working day."
        )

    return _DEFAULT_OFF_HOURS_MESSAGE


def build_off_hours_message(context: Optional[dict[str, Any]] = None) -> str:
    """Return the configured or computed closed-hours message for WhatsApp."""
    return build_closed_hours_message(context)


def _format_working_hours_hint(status: dict[str, Any]) -> str:
    schedule = get_working_schedule_for_datetime()
    if not schedule:
        return ""
    start = schedule.get("start_time")
    end = schedule.get("end_time")
    if hasattr(start, "total_seconds"):
        start = f"{int(start.total_seconds() // 3600):02d}:{int((start.total_seconds() % 3600) // 60):02d}"
    if hasattr(end, "total_seconds"):
        end = f"{int(end.total_seconds() // 3600):02d}:{int((end.total_seconds() % 3600) // 60):02d}"
    tz_label = status.get("timezone", _DEFAULT_TIMEZONE).split("/")[-1].replace("_", " ")
    return f"Hours today: {start} – {end} ({tz_label})"


def build_connecting_message(context: Optional[dict[str, Any]] = None) -> str:
    """Return the message sent when a live HR chat session is opened."""
    lang = (context or {}).get("preferred_language", "English")
    if lang == "Urdu":
        return (
            "آپ HR سپورٹ سے منسلک ہیں۔ براہ کرم اپنا پیغام بھیجیں "
            "اور HR نمائندہ جلد جواب دے گا۔\n\n"
            "مین مینو پر واپس جانے کے لیے 'menu' لکھیں۔"
        )
    if lang == "Roman Urdu":
        return (
            "Aap HR support se connected hain. Apna message bhejein "
            "aur HR representative jald jawab dega.\n\n"
            "Main menu par wapas jane ke liye 'menu' likhein."
        )
    return (
        "You are connected to HR support. Please type your message and "
        "an HR representative will respond shortly.\n\n"
        "Type 'menu' to return to the main menu."
    )


def build_session_open_message(context: Optional[dict[str, Any]] = None) -> str:
    """Message when a chat session opens (employee may queue when CLOSED)."""
    status = get_hr_support_status()
    base = build_connecting_message(context)
    if status["is_open"]:
        return base

    lang = (context or {}).get("preferred_language", "English")
    closed_note = build_closed_hours_message(context)
    if lang == "Urdu":
        queue_note = (
            "\n\n_آپ کا پیغام HR کو بھیج دیا گیا ہے۔ "
            "HR نمائندہ دستیاب ہونے پر جواب دے گا۔_"
        )
    elif lang == "Roman Urdu":
        queue_note = (
            "\n\n_Aap ka message HR ko bhej diya gaya hai. "
            "HR representative available hone par jawab dega._"
        )
    else:
        queue_note = (
            "\n\n_Your message has been queued for HR. "
            "A representative will respond when support reopens._"
        )
    return f"{base}\n\n{closed_note}{queue_note}"
