"""
ai_workplace/tests/test_orchestrator_hr_chat.py
──────────────────────────────────────────────────
Tests for Contact HR orchestration and live chat routing.
"""

import unittest
from unittest.mock import patch

import frappe

from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.conversation.state import ConversationState
from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.whatsapp.outbound import OutboundMessage


class TestOrchestratorHRChat(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()
        suffix = str(abs(hash(self.id())))[-6:]
        self.phone = f"+92301{suffix}"
        self.wa_id = self.phone.lstrip("+")
        self.identity = IdentityResult(
            status="matched",
            normalized_phone=self.phone,
            user=f"hrchat.flow.{suffix}@example.com",
            employee=f"EMP-HRCHAT-FLOW-{suffix}",
            full_name="HR Flow Tester",
        )
        self.wa_identity = get_or_create_whatsapp_identity(self.identity, wa_id=self.wa_id)
        self.identity.whatsapp_identity = self.wa_identity

    def tearDown(self):
        frappe.db.rollback()

    def _complete_language_and_menu(self):
        process_message("Hi", self.identity, message_id="hr-1", trace_id="hr-tr", wa_id=self.wa_id)
        process_message("lang_en", self.identity, message_id="hr-2", trace_id="hr-tr", wa_id=self.wa_id)

    @patch(
        "ai_workplace.services.office_hours.get_hr_support_status",
        return_value={
            "status": "Open",
            "is_open": True,
            "closed_reason": None,
            "is_holiday": False,
            "is_working_day": True,
            "timezone": "Asia/Karachi",
            "local_time": "10:00 AM",
            "local_date": "Monday",
            "local_datetime": "2026-09-07T10:00:00",
        },
    )
    @patch("ai_workplace.services.office_hours.is_hr_available", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=True)
    def test_contact_hr_opens_live_chat(self, _mock_hours, _mock_enabled, _mock_oh_avail=None, _mock_status=None):
        self._complete_language_and_menu()
        resp = process_message(
            "svc_contact_hr",
            self.identity,
            message_id="hr-3",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("connected to hr", resp.body_text.lower())

        conv_name = frappe.db.get_value(
            "WhatsApp Conversation",
            {"whatsapp_identity": self.wa_identity, "conversation_status": "Active"},
            "name",
        )
        state = frappe.db.get_value("WhatsApp Conversation", conv_name, "current_state")
        self.assertEqual(state, ConversationState.LIVE_HR_CHAT)

        session_count = frappe.db.count(
            "HR Live Chat Session",
            {
                "whatsapp_identity": self.wa_identity,
                "contact_hr_selected": 1,
                "ready_for_hr": 1,
                "status": ["in", ["Queued", "Active", "Assigned"]],
            },
        )
        self.assertGreaterEqual(session_count, 1)

    @patch(
        "ai_workplace.services.office_hours.get_hr_support_status",
        return_value={
            "status": "Closed",
            "is_open": False,
            "closed_reason": "outside_hours",
            "is_holiday": False,
            "is_working_day": True,
            "timezone": "Asia/Karachi",
            "local_time": "08:00 PM",
            "local_date": "Monday",
            "local_datetime": "2026-09-07T20:00:00",
        },
    )
    @patch("ai_workplace.services.office_hours.is_hr_available", return_value=False)
    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=False)
    def test_contact_hr_off_hours_still_connects(self, _mock_hours, _mock_enabled, _mock_oh_avail=None, _mock_status=None):
        self._complete_language_and_menu()
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="hr-4",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        resp = process_message(
            "hr_wait_connect",
            self.identity,
            message_id="hr-4b",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertIn("connected to hr", resp.body_text.lower())
        self.assertIn("pakistan time", resp.body_text.lower())

    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=True)
    def test_live_chat_inbound_skips_auto_reply(self, _mock_hours, _mock_enabled):
        self._complete_language_and_menu()
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="hr-5",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        process_message(
            "hr_wait_connect",
            self.identity,
            message_id="hr-5b",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        resp = process_message(
            "I need help with my leave balance",
            self.identity,
            message_id="hr-6",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.skip_send)

    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=True)
    def test_end_chat_returns_to_menu(self, _mock_hours, _mock_enabled):
        self._complete_language_and_menu()
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="hr-7",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        process_message(
            "hr_wait_connect",
            self.identity,
            message_id="hr-7b",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        resp = process_message(
            "end chat",
            self.identity,
            message_id="hr-8",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.is_interactive() or "menu" in resp.body_text.lower())

    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=True)
    def test_end_hr_chat_button_ends_session(self, _mock_hours, _mock_enabled):
        self._complete_language_and_menu()
        process_message(
            "svc_contact_hr",
            self.identity,
            message_id="hr-9",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        open_resp = process_message(
            "hr_wait_connect",
            self.identity,
            message_id="hr-9b",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertTrue(open_resp.is_interactive())

        resp = process_message(
            "svc_end_hr_chat",
            self.identity,
            message_id="hr-10",
            trace_id="hr-tr",
            wa_id=self.wa_id,
        )
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("hr live chat session ended", resp.body_text.lower())

