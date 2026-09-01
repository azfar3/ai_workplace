# ai_workplace/doctype/ai_workplace_settings/ai_workplace_settings.py

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, time_diff

HR_AGENT_ROLE = "HR Workplace Agent"
DEFAULT_OFFICE_TIMEZONE = "Asia/Karachi"

DEFAULT_WORKING_DAYS: list[tuple[str, int, str, str]] = [
    ("Monday", 1, "09:00:00", "18:00:00"),
    ("Tuesday", 1, "09:00:00", "18:00:00"),
    ("Wednesday", 1, "09:00:00", "18:00:00"),
    ("Thursday", 1, "09:00:00", "18:00:00"),
    ("Friday", 1, "09:00:00", "18:00:00"),
    ("Saturday", 0, "09:00:00", "18:00:00"),
    ("Sunday", 0, "09:00:00", "18:00:00"),
]


class AIWorkplaceSettings(Document):
    """
    AI Workplace Settings — Single DocType.
    Stores Meta/WhatsApp Cloud API configuration and HR live chat settings.
    """

    @property
    def enabled(self) -> bool:
        """Return True by default so cfg.get('enabled') evaluates to True when no explicit field is present."""
        return True


    def validate(self):
        """Enforce Phase 1 invariants and HR live chat settings."""
        if cint(self.get("proactive_notifications_enabled")):
            frappe.throw(
                "Proactive notifications must remain disabled in Phase 1. "
                "This feature is reserved for a future phase.",
                frappe.ValidationError,
            )

        graph_ver = self.get("graph_api_version")
        if graph_ver and not graph_ver.startswith("v"):
            self.graph_api_version = f"v{graph_ver}"

        retention = self.get("message_retention_days")
        if retention is not None and cint(retention) < 1:
            frappe.throw("Message Retention Days must be at least 1")

        self._ensure_office_timezone()
        self._ensure_working_days()
        self._validate_working_days()
        self._validate_chat_agents()

    def on_update(self):
        self._sync_hr_chat_agent_roles()

    def _ensure_office_timezone(self):
        tz = (self.get("office_timezone") or self.get("hr_office_timezone") or "").strip()
        if not tz:
            tz = DEFAULT_OFFICE_TIMEZONE
        self.office_timezone = tz
        self.hr_office_timezone = tz

    def _ensure_working_days(self):
        if self.get("hr_working_days"):
            return

        legacy_days = (self.get("office_days") or self.get("hr_office_days") or "").strip()
        legacy_start = self.get("office_start_time") or self.get("hr_office_start_time") or time_diff("09:00:00", "00:00:00")
        legacy_end = self.get("office_end_time") or self.get("hr_office_end_time") or time_diff("18:00:00", "00:00:00")
        legacy_abbr_to_name = {
            "Mon": "Monday",
            "Tue": "Tuesday",
            "Wed": "Wednesday",
            "Thu": "Thursday",
            "Fri": "Friday",
            "Sat": "Saturday",
            "Sun": "Sunday",
        }
        legacy_working: set[str] = set()
        if legacy_days:
            for part in legacy_days.split(","):
                abbr = part.strip()
                if abbr:
                    legacy_working.add(legacy_abbr_to_name.get(abbr, abbr))

        for day_name, default_working, start, end in DEFAULT_WORKING_DAYS:
            if legacy_working:
                is_working = 1 if day_name in legacy_working else 0
            else:
                is_working = default_working

            self.append(
                "hr_working_days",
                {
                    "day_of_week": day_name,
                    "is_working_day": is_working,
                    "start_time": legacy_start if legacy_days or legacy_start else start,
                    "end_time": legacy_end if legacy_days or legacy_end else end,
                },
            )

    def _validate_working_days(self):
        seen_days: set[str] = set()
        for row in self.get("hr_working_days") or []:
            if row.day_of_week in seen_days:
                frappe.throw(f"Duplicate working day entry: {row.day_of_week}")
            seen_days.add(row.day_of_week)

            if not row.is_working_day:
                continue

            start_seconds = _time_value_to_seconds(row.start_time)
            end_seconds = _time_value_to_seconds(row.end_time)
            if end_seconds <= start_seconds:
                frappe.throw(
                    f"End time must be after start time for {row.day_of_week}."
                )

    def _validate_chat_agents(self):
        seen_users: set[str] = set()
        for row in self.get("hr_chat_agents") or []:
            if not row.user:
                continue
            if row.user in seen_users:
                frappe.throw(f"Duplicate HR chat agent: {row.user}")
            seen_users.add(row.user)
            if not frappe.db.exists("User", row.user):
                frappe.throw(f"User {row.user} does not exist.")
            if not frappe.db.get_value("User", row.user, "enabled"):
                frappe.throw(f"User {row.user} is disabled.")

    def _sync_hr_chat_agent_roles(self):
        """Grant HR Workplace Agent role to configured chat users for Desk page access."""
        for row in self.get("hr_chat_agents") or []:
            if not row.user or not row.is_active:
                continue
            try:
                user_doc = frappe.get_doc("User", row.user)
            except Exception:
                continue
            existing_roles = {r.role for r in user_doc.get("roles") or []}
            if HR_AGENT_ROLE not in existing_roles:
                user_doc.add_roles(HR_AGENT_ROLE)


def _time_value_to_seconds(value) -> int:
    if value is None:
        return 0
    if hasattr(value, "total_seconds"):
        return int(value.total_seconds())
    if isinstance(value, str):
        parts = value.split(":")
        if len(parts) >= 2:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) > 2 else 0
            return hours * 3600 + minutes * 60 + seconds
    return 0
