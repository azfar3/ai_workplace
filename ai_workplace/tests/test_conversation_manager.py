"""
ai_workplace/tests/test_conversation_manager.py
─────────────────────────────────────────────────
Unit tests for Conversation Manager (Session management & TTL).
"""

import unittest
from datetime import datetime, timedelta
import frappe

from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.conversation.manager import (
    get_or_create_conversation,
    update_conversation,
    expire_conversation,
    cancel_conversation,
    complete_conversation,
)
from ai_workplace.conversation.state import ConversationStatus, ConversationState


class TestConversationManager(unittest.TestCase):

    def setUp(self):
        frappe.db.rollback()
        self.phone = "+923001112233"
        self.wa_id = "923001112233"
        self.identity = IdentityResult(
            status="matched",
            normalized_phone=self.phone,
            user="test_user@example.com",
            employee="EMP-0001",
            full_name="Test User",
        )

    def tearDown(self):
        frappe.db.rollback()

    def test_create_and_reuse_conversation(self):
        conv1 = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-1")
        self.assertIsNotNone(conv1.name)
        self.assertEqual(conv1.conversation_status, ConversationStatus.ACTIVE)
        self.assertEqual(conv1.current_state, ConversationState.NEW)
        self.assertEqual(conv1.wa_id, self.wa_id)

        # Retrieve again - must reuse same conversation
        conv2 = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-2")
        self.assertEqual(conv1.name, conv2.name)

    def test_expire_conversation(self):
        conv1 = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-exp")
        # Artificially set expires_at in past
        conv1.expires_at = frappe.utils.now_datetime() - timedelta(minutes=10)
        conv1.save(ignore_permissions=True)
        frappe.db.commit()

        # Next request must mark conv1 Expired and create new conv2
        conv2 = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-new")
        self.assertNotEqual(conv1.name, conv2.name)

        old_status = frappe.db.get_value("WhatsApp Conversation", conv1.name, "conversation_status")
        self.assertEqual(old_status, ConversationStatus.EXPIRED)

    def test_cancel_and_complete_conversation(self):
        conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-cc")
        cancel_conversation(conv)
        self.assertEqual(conv.conversation_status, ConversationStatus.CANCELLED)

        # Creating after cancel makes a new active conversation
        conv_new = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="tr-after-cancel")
        self.assertNotEqual(conv.name, conv_new.name)

        complete_conversation(conv_new)
        self.assertEqual(conv_new.conversation_status, ConversationStatus.COMPLETED)
