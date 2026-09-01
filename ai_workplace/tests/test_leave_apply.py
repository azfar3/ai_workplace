"""
ai_workplace/tests/test_leave_apply.py
──────────────────────────────────────
Tests for step-by-step leave application workflow.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.leave_apply import (
    _parse_user_date,
    _resolve_leave_type,
    handle_leave_apply_message,
    start_leave_application,
)


class TestLeaveApplyHelpers(unittest.TestCase):
    def test_parse_user_date(self):
        self.assertIsNotNone(_parse_user_date("01-Sep-2026"))
        self.assertIsNotNone(_parse_user_date("2026-09-01"))

    def test_resolve_leave_type_by_index(self):
        draft = {
            "leave_types": [
                {"leave_type": "Casual Leave", "remaining": "5.0"},
                {"leave_type": "Sick Leave", "remaining": "3.0"},
            ]
        }
        self.assertEqual(_resolve_leave_type(draft, "lt_1"), "Sick Leave")


class TestLeaveApplyFlow(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        self.conv = MagicMock()
        self.conv.name = "CONV-TEST"
        self.conv.employee = "EMP-TEST"
        self.conv.draft_payload = None
        self.context = {
            "employee": "EMP-TEST",
            "user": "Administrator",
            "preferred_language": "English",
            "person_type": "Employee",
        }

    def tearDown(self):
        frappe.db.rollback()

    @patch("ai_workplace.services.leave_apply.update_conversation")
    @patch("ai_workplace.services.leave_apply.get_leave_balance_data")
    def test_start_requires_leave_types(self, mock_balance, mock_update):
        mock_balance.return_value = []
        out = start_leave_application(self.conv, self.context)
        self.assertIn("No active leave allocation", out.body_text)

    @patch("ai_workplace.services.leave_apply.update_conversation")
    @patch("ai_workplace.services.leave_apply.get_leave_balance_data")
    def test_start_sets_processing_state(self, mock_balance, mock_update):
        mock_balance.return_value = [{"leave_type": "Casual Leave", "remaining": "5.0"}]
        out = start_leave_application(self.conv, self.context)
        self.assertIn("Apply for Leave", out.body_text)
        mock_update.assert_called()
        call_kwargs = mock_update.call_args[1]
        self.assertEqual(call_kwargs["state"], ConversationState.PROCESSING)
        self.assertEqual(call_kwargs["current_intent"], "leave_apply")

    @patch("ai_workplace.services.leave_apply._save_draft")
    def test_handle_leave_type_step(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_leave_type",
            "leave_types": [{"leave_type": "Casual Leave", "remaining": "5.0"}],
        })
        out = handle_leave_apply_message(self.conv, "lt_0", self.context)
        self.assertIn("From Date", out.body_text)
        mock_save.assert_called()
