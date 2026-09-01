"""
Tests for offline HR leave-message flow (Former Employee + free-text intake).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.conversation.state import ConversationState
from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.services.hr_chat import normalize_session_person_type, open_session
from ai_workplace.services.hr_contact_prompt import is_wait_for_hr_selection
from ai_workplace.whatsapp.outbound import OutboundMessage


class TestHROfflineMessage(unittest.TestCase):
    def test_normalize_session_person_type(self):
        self.assertEqual(normalize_session_person_type("Former Employee"), "Former Employee")
        self.assertEqual(normalize_session_person_type("Inactive"), "Former Employee")
        self.assertEqual(normalize_session_person_type("Employee"), "Employee")
        self.assertEqual(normalize_session_person_type(""), "Employee")

    def test_leave_message_aliases(self):
        self.assertTrue(is_wait_for_hr_selection("leave message"))
        self.assertTrue(is_wait_for_hr_selection("Leave Message"))
        self.assertTrue(is_wait_for_hr_selection("hr_wait_connect"))

    def setUp(self):
        frappe.db.rollback()
        suffix = str(abs(hash(self.id())))[-6:]
        self.phone = f"+92309{suffix}"
        self.wa_id = self.phone.lstrip("+")
        self.identity = IdentityResult(
            status="inactive",
            normalized_phone=self.phone,
            user=f"former.hr.{suffix}@example.com",
            employee=None,
            full_name="Former HR Tester",
        )
        self.wa_identity = get_or_create_whatsapp_identity(self.identity, wa_id=self.wa_id)
        self.identity.whatsapp_identity = self.wa_identity

    def tearDown(self):
        frappe.db.rollback()

    def _former_employee_context(self):
        return {
            "person_type": "Former Employee",
            "identity_status": "inactive",
            "preferred_language": "English",
            "full_name": "Former HR Tester",
            "employee": None,
            "user": self.identity.user,
            "allowed_services": [
                "former_letter",
                "former_payslip",
                "former_verification",
                "former_concern",
                "former_careers",
                "contact_hr",
            ],
            "whatsapp_identity": self.wa_identity,
            "normalized_phone": self.phone,
            "roles": [],
            "projects": [],
        }

    @patch("ai_workplace.conversation.orchestrator.get_user_context")
    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=False)
    def test_former_employee_leave_message_connects(self, _hours, _enabled, mock_ctx):
        mock_ctx.return_value = self._former_employee_context()
        process_message("Hi", self.identity, message_id="fo-1", trace_id="fo-tr", wa_id=self.wa_id)
        process_message("lang_en", self.identity, message_id="fo-2", trace_id="fo-tr", wa_id=self.wa_id)
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="fo-3",
            trace_id="fo-tr",
            wa_id=self.wa_id,
        )
        resp = process_message(
            "hr_wait_connect",
            self.identity,
            message_id="fo-4",
            trace_id="fo-tr",
            wa_id=self.wa_id,
        )
        self.assertIn("connected to hr", (resp.body_text or "").lower())

        conv_name = frappe.db.get_value(
            "WhatsApp Conversation",
            {"whatsapp_identity": self.wa_identity, "conversation_status": "Active"},
            "name",
        )
        state = frappe.db.get_value("WhatsApp Conversation", conv_name, "current_state")
        self.assertEqual(state, ConversationState.LIVE_HR_CHAT)

        session_name = frappe.db.get_value(
            "HR Live Chat Session",
            {"whatsapp_identity": self.wa_identity},
            "name",
        )
        person_type = frappe.db.get_value("HR Live Chat Session", session_name, "person_type")
        self.assertEqual(person_type, "Former Employee")

    @patch("ai_workplace.conversation.orchestrator.get_user_context")
    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=False)
    def test_free_text_while_offline_records_message(self, _hours, _enabled, mock_ctx):
        mock_ctx.return_value = self._former_employee_context()
        process_message("Hi", self.identity, message_id="ft-1", trace_id="ft-tr", wa_id=self.wa_id)
        process_message("lang_en", self.identity, message_id="ft-2", trace_id="ft-tr", wa_id=self.wa_id)
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="ft-3",
            trace_id="ft-tr",
            wa_id=self.wa_id,
        )
        salary_msg = "i want to talk about my salary deduction, plz response me when u get back"
        resp = process_message(
            salary_msg,
            self.identity,
            message_id="ft-4",
            trace_id="ft-tr",
            wa_id=self.wa_id,
        )
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("connected to hr", (resp.body_text or "").lower())

        conv_name = frappe.db.get_value(
            "WhatsApp Conversation",
            {"whatsapp_identity": self.wa_identity, "conversation_status": "Active"},
            "name",
        )
        state = frappe.db.get_value("WhatsApp Conversation", conv_name, "current_state")
        self.assertEqual(state, ConversationState.LIVE_HR_CHAT)

        session_name = frappe.db.get_value(
            "HR Live Chat Session",
            {"whatsapp_identity": self.wa_identity},
            "name",
        )
        self.assertTrue(session_name)
