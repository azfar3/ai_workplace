"""
ai_workplace/tests/test_concern_report.py
──────────────────────────────────────────
Tests for step-by-step concern / wrongdoing report workflow.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.concern_report import (
    _normalize_cnic,
    _resolve_incident_type,
    handle_concern_report_message,
    start_concern_report,
)
from ai_workplace.services.registry import get_available_services_for_context


class TestConcernReportHelpers(unittest.TestCase):
    def test_resolve_incident_type_by_index(self):
        draft = {
            "grievance_types": [
                "Fraud or Corruption",
                "Harassment or Bullying",
                "Other",
            ]
        }
        self.assertEqual(_resolve_incident_type(draft, "gt_1"), "Harassment or Bullying")

    def test_normalize_cnic_strips_dashes(self):
        self.assertEqual(_normalize_cnic("61101-1234567-1"), "6110112345671")


class TestConcernReportRegistry(unittest.TestCase):
    def test_concerns_has_no_submenu_fallback(self):
        """Leaf menus must not fake a submenu with only Main Menu."""
        context = {
            "person_type": "Employee",
            "allowed_services": ["concerns"],
        }
        submenus = get_available_services_for_context(context, parent_key="concerns")
        self.assertEqual(submenus, [])


class TestConcernReportFlow(unittest.TestCase):
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

    @patch("ai_workplace.services.concern_report.update_conversation")
    @patch("ai_workplace.services.concern_report._get_grievance_types")
    def test_start_sets_processing_state(self, mock_types, mock_update):
        mock_types.return_value = ["Fraud or Corruption", "Other"]
        out = start_concern_report(self.conv, self.context)
        self.assertIn("Report a Concern", out.body_text)
        mock_update.assert_called()
        call_kwargs = mock_update.call_args[1]
        self.assertEqual(call_kwargs["state"], ConversationState.PROCESSING)
        self.assertEqual(call_kwargs["current_intent"], "concern_report")

    @patch("ai_workplace.services.concern_report._save_draft")
    def test_handle_incident_type_employee_skips_personal(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_incident_type",
            "is_guest": False,
            "grievance_types": ["Fraud or Corruption"],
        })
        out = handle_concern_report_message(self.conv, "gt_0", self.context)
        self.assertIn("Incident Date", out.body_text)
        mock_save.assert_called()

    @patch("ai_workplace.services.concern_report._save_draft")
    def test_handle_incident_type_guest_collects_personal(self, mock_save):
        self.conv.draft_payload = json.dumps({
            "step": "awaiting_incident_type",
            "is_guest": True,
            "grievance_types": ["Other"],
        })
        guest_context = {**self.context, "employee": None}
        out = handle_concern_report_message(self.conv, "gt_0", guest_context)
        self.assertIn("Full Name", out.body_text)
        mock_save.assert_called()
