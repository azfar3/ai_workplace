"""
ai_workplace/tests/test_conversation_timeout.py
──────────────────────────────────────────────────
Unit tests for session timeout (1 hour) and post-session feedback collection.
"""

import unittest
from datetime import timedelta
import frappe

from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.conversation.manager import (
    get_or_create_conversation,
    close_inactive_sessions,
    get_default_ttl_minutes,
)
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.conversation.state import ConversationStatus, ConversationState


class TestConversationTimeout(unittest.TestCase):

    def setUp(self):
        frappe.db.rollback()
        self.phone = "+923001112233"
        self.wa_id = "923001112233"
        self.identity = IdentityResult(
            status="guest",
            normalized_phone=self.phone,
            user=None,
            employee=None,
            full_name="Test User",
        )
        self.wa_identity_name = get_or_create_whatsapp_identity(self.identity, wa_id=self.wa_id)
        self.identity.whatsapp_identity = self.wa_identity_name

    def tearDown(self):
        frappe.db.rollback()

    def test_default_ttl_is_60_minutes(self):
        ttl = get_default_ttl_minutes()
        self.assertEqual(ttl, 60)

    def test_user_bye_command_requests_feedback_and_processes_rating(self):
        conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-bye-1")
        self.assertEqual(conv.conversation_status, ConversationStatus.ACTIVE)

        # 1. Send "bye"
        outbound = process_message(
            message_text="bye",
            identity=self.identity,
            trace_id="tr-bye-1",
            wa_id=self.wa_id,
        )

        body = outbound.body_text if hasattr(outbound, "body_text") else str(outbound)
        self.assertIn("Goodbye", body)
        self.assertIn("rate your session", body.lower())

        state = frappe.db.get_value("WhatsApp Conversation", conv.name, "current_state")
        self.assertEqual(state, ConversationState.AWAITING_FEEDBACK)

        # 2. User responds with rating "5"
        fb_outbound = process_message(
            message_text="5 - Excellent service!",
            identity=self.identity,
            trace_id="tr-bye-1-fb",
            wa_id=self.wa_id,
        )

        fb_body = fb_outbound.body_text if hasattr(fb_outbound, "body_text") else str(fb_outbound)
        self.assertIn("Thank you", fb_body)

        # Verify AI Feedback Log record created
        fb_logs = frappe.get_all(
            "AI Feedback Log",
            filters={"conversation": conv.name},
            fields=["feedback_type", "query"],
        )
        self.assertTrue(len(fb_logs) > 0)
        self.assertEqual(fb_logs[0].feedback_type, "HELPFUL")

        # Session should now be marked Completed
        status = frappe.db.get_value("WhatsApp Conversation", conv.name, "conversation_status")
        self.assertEqual(status, ConversationStatus.COMPLETED)

    def test_user_khuda_hafiz_command_closes_session(self):
        conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-bye-2")
        conv.preferred_language = "Urdu"
        conv.save(ignore_permissions=True)
        frappe.db.commit()

        outbound = process_message(
            message_text="خدا حافظ",
            identity=self.identity,
            trace_id="tr-bye-2",
            wa_id=self.wa_id,
        )

        body = outbound.body_text if hasattr(outbound, "body_text") else str(outbound)
        self.assertIn("خدا حافظ", body)
        self.assertIn("درجہ بندی کریں", body)

        state = frappe.db.get_value("WhatsApp Conversation", conv.name, "current_state")
        self.assertEqual(state, ConversationState.AWAITING_FEEDBACK)

    def test_inactivity_timeout_sends_bye_and_closes_session(self):
        conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-timeout-1")
        conv.expires_at = frappe.utils.now_datetime() - timedelta(minutes=70)
        conv.save(ignore_permissions=True)
        frappe.db.commit()

        res = close_inactive_sessions()
        self.assertGreaterEqual(res.get("closed_count", 0), 1)

        status = frappe.db.get_value("WhatsApp Conversation", conv.name, "conversation_status")
        self.assertEqual(status, ConversationStatus.EXPIRED)

        # Check WhatsApp Message Log created
        logs = frappe.get_all(
            "WhatsApp Message Log",
            filters={"direction": "Outbound"},
            fields=["name", "whatsapp_id", "recipient", "message", "sender_type"],
        )
        self.assertTrue(len(logs) > 0, f"No outbound logs found. Logs: {logs}")
        self.assertTrue(
            any("expired due to inactivity" in (l.message or "").lower() or "goodbye" in (l.message or "").lower() for l in logs),
            f"Expected timeout message in logs, found: {[l.message for l in logs]}"
        )
