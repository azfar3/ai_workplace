"""
ai_workplace/tests/test_attendance_leave.py
─────────────────────────────────────────────
Unit tests for Attendance & Leave handlers:
- Today's Attendance
- Monthly Attendance
- Missing Attendance
- Leave Balance
- Apply for Leave
- My Leave Requests
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.services.attendance_leave import (
    build_today_attendance_response,
    build_monthly_attendance_response,
    build_last7_attendance_response,
    generate_monthly_attendance_excel,
    build_missing_attendance_response,
    build_leave_balance_response,
    build_apply_leave_response,
    build_leave_requests_response,
    format_time,
)
from ai_workplace.services.response_helpers import (
    wrap_monthly_attendance_summary,
    wrap_monthly_attendance_detail,
)
from ai_workplace.whatsapp.interactive import build_monthly_attendance_options_message


class TestAttendanceLeaveServices(unittest.TestCase):
    def setUp(self):
        self.context_en = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "English",
        }
        self.context_ur = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "Urdu",
        }
        self.context_ru = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "Roman Urdu",
        }

    def test_format_time(self):
        self.assertEqual(format_time("09:15:00"), "09:15 AM")
        self.assertEqual(format_time("17:45:00"), "05:45 PM")
        self.assertEqual(format_time("2026-08-28 09:00:00"), "09:00 AM")
        self.assertEqual(format_time(None), "N/A")

    @patch("ai_workplace.services.attendance_leave.get_today_attendance_data")
    def test_build_today_attendance_response(self, mock_get_data):
        mock_get_data.return_value = {
            "date": "2026-08-28",
            "status": "Present",
            "in_time": "09:00 AM",
            "out_time": "05:30 PM",
            "working_hours": "8.50",
            "late_entry": False,
            "early_exit": False,
            "logs_count": 2,
        }

        # English
        res_en = build_today_attendance_response(self.context_en)
        self.assertIn("Today's Attendance", res_en)
        self.assertIn("Ali Ahmed", res_en)
        self.assertIn("Present", res_en)
        self.assertIn("09:00 AM", res_en)

        # Roman Urdu
        res_ru = build_today_attendance_response(self.context_ru)
        self.assertIn("Aaj Ki Attendance", res_ru)

        # Urdu
        res_ur = build_today_attendance_response(self.context_ur)
        self.assertIn("آج کی حاضری", res_ur)

    @patch("ai_workplace.services.attendance_leave.get_monthly_attendance_data")
    def test_build_monthly_attendance_response(self, mock_get_data):
        mock_get_data.return_value = {
            "month_name": "August 2026",
            "total_days": 20,
            "present": 18,
            "absent": 1,
            "leave": 1,
            "half_day": 0,
            "total_hours": 153.0,
            "late_entries": 2,
        }

        res_en = build_monthly_attendance_response(self.context_en)
        self.assertIn("Monthly Attendance Summary", res_en)
        self.assertIn("18", res_en)
        self.assertIn("153.0 hrs", res_en)

    @patch("ai_workplace.services.attendance_leave.get_last_working_days_attendance")
    def test_build_last7_attendance_response(self, mock_get_days):
        mock_get_days.return_value = [
            {
                "date": "2026-08-28",
                "date_label": "Thu 28 Aug",
                "status": "Present",
                "in_time": "09:00 AM",
                "out_time": "05:30 PM",
                "hours": "8.5",
                "task": "Project work",
            }
        ]

        res_en = build_last7_attendance_response(self.context_en)
        self.assertIn("Last 7 Working Days", res_en)
        self.assertIn("09:00 AM", res_en)
        self.assertIn("Project work", res_en)

        mock_get_days.return_value = []
        res_empty = build_last7_attendance_response(self.context_en)
        self.assertIn("No attendance records found", res_empty)

    @patch("ai_workplace.services.attendance_leave.get_month_to_date_attendance")
    def test_generate_monthly_attendance_excel(self, mock_get_days):
        mock_get_days.return_value = [
            {
                "date": "2026-08-28",
                "status": "Present",
                "in_time": "09:00 AM",
                "out_time": "05:30 PM",
                "hours": "8.5",
                "task": "Reports",
            }
        ]

        content, filename = generate_monthly_attendance_excel("EMP-001", "Ali Ahmed")
        self.assertTrue(filename.endswith(".xlsx"))
        self.assertIn("Ali_Ahmed", filename)
        self.assertTrue(len(content) > 100)

    def test_wrap_monthly_attendance_helpers(self):
        summary = wrap_monthly_attendance_summary("Summary text", self.context_en)
        self.assertEqual(summary.body_text, "Summary text")
        self.assertEqual(len(summary.follow_up), 1)
        btn_titles = [
            b["reply"]["title"]
            for b in summary.follow_up[0].interactive["action"]["buttons"]
        ]
        self.assertTrue(any("Last 7" in t for t in btn_titles))

        detail = wrap_monthly_attendance_detail("Detail text", self.context_en)
        self.assertEqual(detail.body_text, "Detail text")
        opts = build_monthly_attendance_options_message(self.context_en, after_summary=False)
        opts_titles = [b["reply"]["title"] for b in opts.interactive["action"]["buttons"]]
        self.assertTrue(any("Summary" in t for t in opts_titles))

    @patch("ai_workplace.services.attendance_leave.get_missing_attendance_data")
    def test_build_missing_attendance_response(self, mock_get_data):
        mock_get_data.return_value = [
            {"date": "15 Aug 2026", "reason": "Marked Absent (No punch / no leave logged)"}
        ]

        res_en = build_missing_attendance_response(self.context_en)
        self.assertIn("Missing Attendance Discrepancies", res_en)
        self.assertIn("15 Aug 2026", res_en)

    @patch("ai_workplace.services.attendance_leave.get_leave_balance_data")
    def test_build_leave_balance_response(self, mock_get_data):
        mock_get_data.return_value = [
            {"leave_type": "Casual Leave", "allocated": "10.0", "taken": "2.0", "remaining": "8.0"},
            {"leave_type": "Sick Leave", "allocated": "8.0", "taken": "0.0", "remaining": "8.0"},
        ]

        res_en = build_leave_balance_response(self.context_en)
        self.assertIn("Your Leave Balance Summary", res_en)
        self.assertIn("Casual Leave", res_en)
        self.assertIn("Remaining: 8.0", res_en)

    def test_build_apply_leave_response(self):
        res_en = build_apply_leave_response(self.context_en)
        self.assertIn("Apply for Leave", res_en)
        self.assertIn("Leave Type:", res_en)

    @patch("ai_workplace.services.attendance_leave.get_recent_leave_requests")
    def test_build_leave_requests_response(self, mock_get_data):
        mock_get_data.return_value = [
            {"leave_type": "Casual Leave", "from_date": "10 Aug", "to_date": "12 Aug 2026", "total_days": "3.0", "status": "Approved"}
        ]

        res_en = build_leave_requests_response(self.context_en)
        self.assertIn("Recent Leave Applications Status", res_en)
        self.assertIn("Casual Leave", res_en)
        self.assertIn("🟢 Approved", res_en)


if __name__ == "__main__":
    unittest.main()
