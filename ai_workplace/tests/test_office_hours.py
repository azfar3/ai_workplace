"""
ai_workplace/tests/test_office_hours.py
────────────────────────────────────────
Tests for HR office hours availability checks (working days, hours, holidays).
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import frappe

from ai_workplace.services.office_hours import (
    HR_STATUS_CLOSED,
    HR_STATUS_OPEN,
    build_closed_hours_message,
    build_off_hours_message,
    build_open_hours_message,
    build_session_open_message,
    get_hr_support_status,
    get_office_hours_info,
    get_office_timezone,
    is_hr_available,
    is_hr_support_holiday,
)


class TestOfficeHours(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()

    def tearDown(self):
        frappe.db.rollback()

    def _working_day_rows(self):
        rows = []
        for day, working in [
            ("Monday", 1),
            ("Tuesday", 1),
            ("Wednesday", 1),
            ("Thursday", 1),
            ("Friday", 1),
            ("Saturday", 0),
            ("Sunday", 0),
        ]:
            row = frappe._dict(
                {
                    "day_of_week": day,
                    "is_working_day": working,
                    "start_time": timedelta(hours=9),
                    "end_time": timedelta(hours=18),
                }
            )
            rows.append(row)
        return rows

    def _mock_settings(self, **overrides):
        defaults = {
            "hr_live_chat_enabled": 1,
            "hr_office_timezone": "Asia/Karachi",
            "hr_working_days": self._working_day_rows(),
            "hr_off_hours_message": "HR is off now.",
        }
        defaults.update(overrides)

        class FakeSettings:
            def get(self, key, default=None):
                if key == "hr_working_days" and "hr_working_days" in defaults:
                    return defaults["hr_working_days"]
                return defaults.get(key, default)

        return FakeSettings()

    def test_available_during_office_hours_weekday(self):
        tz = ZoneInfo("Asia/Karachi")
        monday_noon = datetime(2026, 8, 31, 12, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            status = get_hr_support_status(monday_noon)
            self.assertTrue(is_hr_available(monday_noon))
            self.assertEqual(status["status"], HR_STATUS_OPEN)

    def test_unavailable_on_weekend(self):
        tz = ZoneInfo("Asia/Karachi")
        saturday_noon = datetime(2026, 8, 29, 12, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            self.assertFalse(is_hr_available(saturday_noon))
            status = get_hr_support_status(saturday_noon)
            self.assertEqual(status["closed_reason"], "non_working_day")

    def test_unavailable_after_close(self):
        tz = ZoneInfo("Asia/Karachi")
        monday_evening = datetime(2026, 8, 31, 19, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            self.assertFalse(is_hr_available(monday_evening))
            status = get_hr_support_status(monday_evening)
            self.assertEqual(status["closed_reason"], "outside_hours")

    def test_unavailable_on_holiday(self):
        tz = ZoneInfo("Asia/Karachi")
        monday_noon = datetime(2026, 8, 31, 12, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            with patch(
                "ai_workplace.services.office_hours.is_hr_support_holiday",
                return_value=True,
            ):
                self.assertFalse(is_hr_available(monday_noon))
                status = get_hr_support_status(monday_noon)
                self.assertEqual(status["closed_reason"], "holiday")

    def test_off_hours_message_from_settings(self):
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            self.assertEqual(build_off_hours_message({}), "HR is off now.")

    def test_per_day_custom_hours(self):
        rows = self._working_day_rows()
        rows[0].start_time = timedelta(hours=10)
        rows[0].end_time = timedelta(hours=16)
        tz = ZoneInfo("Asia/Karachi")
        monday_noon = datetime(2026, 8, 31, 12, 0, 0, tzinfo=tz)
        monday_early = datetime(2026, 8, 31, 9, 0, 0, tzinfo=tz)
        settings = self._mock_settings(hr_working_days=rows)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=settings):
            self.assertTrue(is_hr_available(monday_noon))
            self.assertFalse(is_hr_available(monday_early))

    def test_default_timezone_is_pakistan(self):
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            self.assertEqual(str(get_office_timezone()), "Asia/Karachi")

    def test_session_open_message_off_hours_still_connects(self):
        tz = ZoneInfo("Asia/Karachi")
        saturday_noon = datetime(2026, 8, 29, 12, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            body = build_session_open_message({})
            self.assertIn("connected to hr", body.lower())
            info = get_office_hours_info(saturday_noon)
            self.assertFalse(info["is_office_hours"])
            self.assertEqual(info["hr_support_status"], HR_STATUS_CLOSED)
            self.assertIn("Asia/Karachi", info["timezone"])

    def test_open_hours_message_when_available(self):
        tz = ZoneInfo("Asia/Karachi")
        monday_noon = datetime(2026, 8, 31, 12, 0, 0, tzinfo=tz)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            with patch(
                "ai_workplace.services.office_hours.get_hr_support_status",
                return_value={"is_open": True, "status": HR_STATUS_OPEN},
            ):
                msg = build_open_hours_message({"preferred_language": "English"})
                self.assertIn("open", msg.lower())

    def test_closed_holiday_message_without_settings_override(self):
        tz = ZoneInfo("Asia/Karachi")
        monday_noon = datetime(2026, 8, 31, 12, 0, 0, tzinfo=tz)
        settings = self._mock_settings(hr_off_hours_message="")
        with patch("ai_workplace.services.office_hours._get_settings", return_value=settings):
            with patch(
                "ai_workplace.services.office_hours.get_hr_support_status",
                return_value={"is_open": False, "closed_reason": "holiday", "status": HR_STATUS_CLOSED},
            ):
                msg = build_closed_hours_message({"preferred_language": "English"})
                self.assertIn("holiday", msg.lower())

    def test_uses_server_time_when_now_omitted(self):
        tz = ZoneInfo("Asia/Karachi")
        fake_server = datetime(2026, 8, 31, 12, 0, 0)
        with patch("ai_workplace.services.office_hours._get_settings", return_value=self._mock_settings()):
            with patch("ai_workplace.services.office_hours.now_datetime", return_value=fake_server):
                with patch("ai_workplace.services.office_hours.get_system_timezone", return_value="Asia/Karachi"):
                    office_now = __import__(
                        "ai_workplace.services.office_hours", fromlist=["get_office_now"]
                    ).get_office_now()
                    self.assertEqual(office_now.hour, 12)

    @patch("ai_workplace.services.office_hours.get_hr_holiday_list", return_value="Test Holiday List")
    @patch("erpnext.setup.doctype.holiday_list.holiday_list.is_holiday", return_value=True)
    def test_is_hr_support_holiday_delegates_to_erpnext(self, _mock_is_holiday, _mock_list):
        self.assertTrue(is_hr_support_holiday("2026-08-31"))
