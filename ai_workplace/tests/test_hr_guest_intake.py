"""
ai_workplace/tests/test_hr_guest_intake.py
────────────────────────────────────────────
Tests for guest HR intake flow (name, email, query).
"""

import unittest
from unittest.mock import patch

import frappe

from ai_workplace.conversation.manager import get_or_create_conversation
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.conversation.state import ConversationState
from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.services.hr_guest_intake import handle_guest_intake_message, start_guest_intake
from ai_workplace.whatsapp.outbound import OutboundMessage


class TestHRGuestIntake(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()
        suffix = str(abs(hash(self.id())))[-6:]
        self.phone = f"+92302{suffix}"
        self.wa_id = self.phone.lstrip("+")
        self.identity = IdentityResult(
            status="guest",
            normalized_phone=self.phone,
        )
        self.wa_identity = get_or_create_whatsapp_identity(self.identity, wa_id=self.wa_id)
        self.identity.whatsapp_identity = self.wa_identity
        self.context = {
            "person_type": "Guest",
            "identity_status": "guest",
            "allowed_services": ["contact_hr", "guest_contact"],
            "preferred_language": "English",
            "whatsapp_identity": self.wa_identity,
        }
        self.conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="guest-hr")

    def tearDown(self):
        frappe.db.rollback()

    def _mark_session_ready(self, session_name: str):
        frappe.db.set_value(
            "HR Live Chat Session",
            session_name,
            {"contact_hr_selected": 1, "ready_for_hr": 1},
        )

    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    def test_guest_intake_full_flow(self, _mock_enabled):
        start_guest_intake(self.conv, self.context)
        self.conv.reload()
        self.assertEqual(self.conv.current_state, ConversationState.HR_GUEST_INTAKE)

        r1 = handle_guest_intake_message(self.conv, "Ali Khan", self.context)
        self.assertIn("email", r1.body_text.lower())

        r2 = handle_guest_intake_message(self.conv, "ali@example.com", self.context)
        self.assertIn("question", r2.body_text.lower())

        r3 = handle_guest_intake_message(self.conv, "I need help with onboarding", self.context)

        self.assertIsInstance(r3, OutboundMessage)
        session_name = frappe.db.get_value(
            "WhatsApp Conversation",
            self.conv.name,
            "active_hr_chat_session",
        )
        self.assertTrue(session_name)
        session = frappe.get_doc("HR Live Chat Session", session_name)
        self.assertEqual(session.display_name, "Ali Khan")
        self.assertEqual(session.guest_email, "ali@example.com")
        self.assertEqual(session.initial_query, "I need help with onboarding")
        self.assertEqual(session.ready_for_hr, 1)
        self.assertEqual(session.contact_hr_selected, 1)

    @patch("ai_workplace.services.hr_chat.is_hr_live_chat_enabled", return_value=True)
    @patch("ai_workplace.services.hr_chat.is_hr_available", return_value=True)
    def test_guest_contact_hr_via_orchestrator(self, _mock_hours, _mock_enabled):
        process_message("Hi", self.identity, message_id="g1", trace_id="g", wa_id=self.wa_id)
        process_message("lang_en", self.identity, message_id="g2", trace_id="g", wa_id=self.wa_id)
        resp = process_message("svc_guest_contact", self.identity, message_id="g3", trace_id="g", wa_id=self.wa_id)
        self.assertIn("051 8444 777", resp.body_text)
        resp2 = process_message("hr_wait_connect", self.identity, message_id="g3b", trace_id="g", wa_id=self.wa_id)
        self.assertIn("full name", resp2.body_text.lower())
