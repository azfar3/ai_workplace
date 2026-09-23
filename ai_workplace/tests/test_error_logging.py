"""
ai_workplace/tests/test_error_logging.py
──────────────────────────────────────────
Unit tests verifying standardized error logging using frappe.log_error across AI Workplace.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.services.attendance_request_apply import _create_attendance_request
from ai_workplace.services.concern_report import _create_employee_grievance
from ai_workplace.services.travel import _create_travel_authorisation
from ai_workplace.ai.tools import run_tool
from ai_workplace.ai.router import complete
from ai_workplace.conversation.orchestrator import process_message


class TestErrorLogging(unittest.TestCase):
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

    def tearDown(self):
        if getattr(frappe.local, "db", None):
            frappe.db.rollback()

    @patch("frappe.log_error")
    def test_attendance_request_error_logging(self, mock_log_error):
        draft = {"employee": "EMP-001", "from_date": "2026-10-01", "to_date": "2026-10-02"}
        context = {"employee": "EMP-001"}
        with patch("frappe.get_cached_doc", side_effect=Exception("Database retrieval failed")):
            with self.assertRaises(Exception):
                _create_attendance_request(draft, context)
        mock_log_error.assert_called_once()
        self.assertEqual(mock_log_error.call_args[1]["title"], "Attendance Request Submission Failed")

    @patch("frappe.log_error")
    def test_employee_grievance_error_logging(self, mock_log_error):
        draft = {"grievance_type": "Harassment"}
        context = {}
        with patch("frappe.new_doc") as mock_new_doc:
            mock_doc = MagicMock()
            mock_doc.insert.side_effect = Exception("DB error")
            mock_new_doc.return_value = mock_doc
            with self.assertRaises(Exception):
                _create_employee_grievance(draft, context)
        mock_log_error.assert_called_once()
        self.assertEqual(mock_log_error.call_args[1]["title"], "Employee Grievance Submission Failed")

    @patch("frappe.log_error")
    def test_travel_authorisation_error_logging(self, mock_log_error):
        draft = {"employee": "EMP-001", "purpose": "Field Work", "from_date": "2026-10-01", "to_date": "2026-10-05"}
        context = {"employee": "EMP-001"}
        with patch("frappe.get_cached_doc", side_effect=Exception("Database retrieval failed")):
            with self.assertRaises(Exception):
                _create_travel_authorisation(draft, context)
        mock_log_error.assert_called_once()
        self.assertEqual(mock_log_error.call_args[1]["title"], "Travel Authorisation Submission Failed")

    @patch("frappe.log_error")
    def test_tool_execution_error_logging(self, mock_log_error):
        with patch("ai_workplace.services.attendance_leave.get_leave_balance_data", side_effect=Exception("Tool execution failed")):
            res = run_tool("get_leave_balance", {"employee": "EMP-001"})
            self.assertEqual(res.get("status"), "error")
            mock_log_error.assert_called_once()
            self.assertIn("AI Tool Execution Failed", mock_log_error.call_args[1]["title"])

    @patch("frappe.log_error")
    def test_router_complete_error_logging(self, mock_log_error):
        with patch("ai_workplace.ai.router._get_active_providers", return_value=[]):
            with patch("ai_workplace.ai.router._groq_settings_fallback", return_value={"success": False}):
                res = complete(prompt="Hello", channel="WhatsApp", employee="EMP-001")
                self.assertFalse(res["success"])
                mock_log_error.assert_called_once()
                self.assertEqual(mock_log_error.call_args[1]["title"], "AI Provider Completion Failed")

    @patch("frappe.log_error")
    def test_orchestrator_process_message_error_logging(self, mock_log_error):
        with patch("ai_workplace.conversation.orchestrator._process_message_internal", side_effect=Exception("Internal Crash")):
            outbound = process_message("Hello", identity=MagicMock(), trace_id="TRACE-123")
            mock_log_error.assert_called_once()
            self.assertEqual(mock_log_error.call_args[1]["title"], "AI Orchestrator Message Failed [TRACE-123]")
            self.assertIn("something went wrong", outbound.body_text)
