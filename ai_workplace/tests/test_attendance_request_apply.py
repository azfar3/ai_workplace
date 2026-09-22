"""
ai_workplace/tests/test_attendance_request_apply.py
────────────────────────────────────────────────────
Tests for Attendance Request permission checks and multi-step application workflow.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.attendance_request_apply import (
    _parse_user_date,
    check_attendance_request_permission,
    handle_attendance_request_message,
    start_attendance_request_application,
)


class TestAttendanceRequestApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not getattr(frappe.local, "db", None):
            import os
            os.chdir("/home/erp/frappe-v15/sites")
            frappe.init(site="erp.v15")
            frappe.connect()

    def setUp(self):
        if getattr(frappe.local, "db", None):
            frappe.db.rollback()
            frappe.set_user("Administrator")
        self.conv = MagicMock()
        self.conv.name = "CONV-ATT-TEST"
        self.conv.employee = "EMP-TEST"
        self.conv.draft_payload = None
        self.context = {
            "employee": "EMP-TEST",
            "user": "Administrator",
            "preferred_language": "English",
            "person_type": "Employee",
        }

    def tearDown(self):
        if getattr(frappe.local, "db", None):
            frappe.db.rollback()

    def test_parse_user_date(self):
        self.assertIsNotNone(_parse_user_date("19-Jun-2026"))
        self.assertIsNotNone(_parse_user_date("2026-06-19"))
        self.assertIsNotNone(_parse_user_date("today"))

    @patch("ai_workplace.services.attendance_request_apply.frappe.has_permission")
    def test_check_permission_guest(self, mock_has_perm):
        self.assertFalse(check_attendance_request_permission("Guest"))
        mock_has_perm.assert_not_called()

    @patch("ai_workplace.services.attendance_request_apply.frappe.has_permission")
    def test_check_permission_allowed(self, mock_has_perm):
        mock_has_perm.return_value = True
        self.assertTrue(check_attendance_request_permission("test@example.com"))
        mock_has_perm.assert_called_with("Attendance Request", ptype="create", user="test@example.com")

    @patch("ai_workplace.services.attendance_request_apply.check_attendance_request_permission")
    def test_start_permission_denied(self, mock_perm):
        mock_perm.return_value = False
        out = start_attendance_request_application(self.conv, self.context)
        self.assertIn("do not have permission", out.body_text)

    @patch("ai_workplace.services.attendance_request_apply.update_conversation")
    @patch("ai_workplace.services.attendance_request_apply.check_attendance_request_permission")
    def test_start_success_presents_reasons(self, mock_perm, mock_update):
        mock_perm.return_value = True
        out = start_attendance_request_application(self.conv, self.context)
        self.assertIn("Attendance Request Reason", out.body_text)
        mock_update.assert_called()

    @patch("ai_workplace.services.attendance_request_apply._save_draft")
    def test_handle_reason_step(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_reason",
            "reasons": ["Check In Miss", "Check Out Miss"],
        })
        out = handle_attendance_request_message(self.conv, "att_reason_0", self.context)
        self.assertIn("Check In Miss", out.body_text)
        self.assertIn("From Date", out.body_text)
        mock_save.assert_called()

    @patch("ai_workplace.services.attendance_request_apply._save_draft")
    def test_handle_from_date_step(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_from_date",
            "reason": "Check In Miss",
        })
        out = handle_attendance_request_message(self.conv, "19-Jun-2026", self.context)
        self.assertIn("To Date", out.body_text)
        mock_save.assert_called()

    @patch("ai_workplace.services.attendance_request_apply._save_draft")
    def test_handle_explanation_and_confirm(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_explanation",
            "reason": "Check In Miss",
            "from_date": "2026-06-19",
            "to_date": "2026-06-19",
        })
        out = handle_attendance_request_message(self.conv, "Forgot to scan badge on entry", self.context)
        self.assertIn("Submit this attendance request", out.body_text)
        self.assertIn("Check In Miss", out.body_text)
        self.assertIn("Forgot to scan badge on entry", out.body_text)
