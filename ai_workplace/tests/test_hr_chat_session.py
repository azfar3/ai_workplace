"""
ai_workplace/tests/test_hr_chat_session.py
────────────────────────────────────────────
Tests for HR live chat session lifecycle and 24-hour reply window.
"""

import unittest
from datetime import timedelta
from unittest.mock import patch

import frappe

from ai_workplace.conversation.manager import get_or_create_conversation, update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.identity.resolver import IdentityResult, get_or_create_whatsapp_identity
from ai_workplace.services.hr_chat import (
    append_inbound_message,
    assign_session,
    close_session,
    evaluate_reply_permission,
    open_session,
    send_hr_reply,
    take_session,
)


class TestHRChatSession(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        self._ensure_hr_agent_role()
        suffix = str(abs(hash(self.id())))[-6:]
        self.phone = f"+92300{suffix}"
        self.wa_id = self.phone.lstrip("+")
        self.identity = IdentityResult(
            status="matched",
            normalized_phone=self.phone,
            user=f"hrchat.{suffix}@example.com",
            employee=f"EMP-HRCHAT-{suffix}",
            full_name="HR Chat Tester",
        )
        self.wa_identity = get_or_create_whatsapp_identity(self.identity, wa_id=self.wa_id)
        self.identity.whatsapp_identity = self.wa_identity
        self.conv = get_or_create_conversation(self.identity, wa_id=self.wa_id, trace_id="hrchat-test")

    def tearDown(self):
        frappe.db.rollback()

    def _ensure_hr_agent_role(self):
        if not frappe.db.exists("Role", "HR Workplace Agent"):
            role = frappe.new_doc("Role")
            role.role_name = "HR Workplace Agent"
            role.desk_access = 1
            role.insert(ignore_permissions=True)
            frappe.db.commit()

    def _open_test_session(self):
        return open_session(
            whatsapp_identity=self.wa_identity,
            whatsapp_conversation=self.conv.name,
            wa_id=self.wa_id,
            employee=self.identity.employee,
            erp_user=self.identity.user,
            display_name=self.identity.full_name,
            person_type="Employee",
            contact_hr_selected=True,
            ready_for_hr=True,
            context={"full_name": self.identity.full_name, "employee": self.identity.employee},
        )

    def test_open_session_creates_queued_record(self):
        session = self._open_test_session()
        self.assertEqual(session.status, "Queued")
        self.assertTrue(session.session_window_expires_at)

    def test_take_session_assigns_current_user(self):
        session = self._open_test_session()
        taken = take_session(session.name, user="Administrator")
        self.assertEqual(taken.assigned_to, "Administrator")
        self.assertEqual(taken.status, "Active")

    def test_assign_session_to_hr_agent(self):
        session = self._open_test_session()
        agent_email = "hr.agent.assign@example.com"
        if not frappe.db.exists("User", agent_email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": agent_email,
                    "first_name": "HR",
                    "last_name": "Agent",
                    "send_welcome_email": 0,
                    "roles": [{"role": "HR Workplace Agent"}],
                }
            ).insert(ignore_permissions=True)
            frappe.db.commit()

        with patch("ai_workplace.services.hr_chat.get_configured_hr_chat_agents", return_value=[]):
            assigned = assign_session(session.name, agent_email, user="Administrator")
        self.assertEqual(assigned.assigned_to, agent_email)
        self.assertEqual(assigned.status, "Active")

    def test_reply_blocked_after_24h_window(self):
        session = self._open_test_session()
        take_session(session.name, user="Administrator")
        expired_at = frappe.utils.now_datetime() - timedelta(hours=25)
        frappe.db.set_value(
            "HR Live Chat Session",
            session.name,
            {
                "last_user_message_at": expired_at,
                "session_window_expires_at": expired_at + timedelta(hours=24),
            },
        )
        session.reload()
        can_reply, reason = evaluate_reply_permission(session, user="Administrator")
        self.assertFalse(can_reply)
        self.assertIn("24-hour", reason)

    def test_inbound_message_resets_window(self):
        session = self._open_test_session()
        old_expiry = session.session_window_expires_at
        append_inbound_message(session, "Hello HR", meta_message_id="")
        session.reload()
        self.assertGreater(session.session_window_expires_at, old_expiry)

    def test_close_session_resets_conversation(self):
        session = self._open_test_session()
        update_conversation(
            self.conv,
            state=ConversationState.LIVE_HR_CHAT,
            active_hr_chat_session=session.name,
        )
        close_session(session.name, user="Administrator")
        self.conv.reload()
        self.assertEqual(self.conv.current_state, ConversationState.AWAITING_SELECTION)
        self.assertFalse(self.conv.active_hr_chat_session)

    @patch("ai_workplace.services.hr_chat.send_text_message")
    def test_send_hr_reply_success(self, mock_send):
        mock_send.return_value = {"success": True, "message_id": "wamid-out-1"}
        session = self._open_test_session()
        take_session(session.name, user="Administrator")
        frappe.db.set_value(
            "WhatsApp Identity",
            self.wa_identity,
            "normalized_phone",
            self.phone,
        )
        result = send_hr_reply(session.name, "We will help you shortly.", user="Administrator")
        self.assertTrue(result["success"])
        mock_send.assert_called_once()

    def test_open_session_reuses_closed_session_for_same_employee(self):
        session1 = self._open_test_session()
        s1_name = session1.name
        close_session(s1_name, user="Administrator")
        
        # Re-open session for the same employee / identity
        session2 = self._open_test_session()
        self.assertEqual(session2.name, s1_name)
        self.assertEqual(session2.status, "Queued")
        self.assertIsNone(session2.closed_at)

    def test_get_session_thread_aggregates_messages_across_sessions(self):
        from ai_workplace.services.hr_chat import get_session_thread, get_inbox_sessions

        session1 = self._open_test_session()
        log1 = frappe.new_doc("WhatsApp Message Log")
        log1.meta_message_id = "msg-101"
        log1.direction = "Inbound"
        log1.sender = self.phone
        log1.whatsapp_id = self.wa_id
        log1.message = "First query from employee"
        log1.hr_live_chat_session = session1.name
        log1.timestamp = frappe.utils.now_datetime()
        log1.insert(ignore_permissions=True)

        close_session(session1.name, user="Administrator")

        # Open session again (will reuse session1)
        session2 = self._open_test_session()
        log2 = frappe.new_doc("WhatsApp Message Log")
        log2.meta_message_id = "msg-102"
        log2.direction = "Inbound"
        log2.sender = self.phone
        log2.whatsapp_id = self.wa_id
        log2.message = "Second query after re-open"
        log2.hr_live_chat_session = session2.name
        log2.timestamp = frappe.utils.now_datetime()
        log2.insert(ignore_permissions=True)

        thread = get_session_thread(session2.name)
        messages = [m["message"] for m in thread]
        self.assertIn("First query from employee", messages)
        self.assertIn("Second query after re-open", messages)

        # Check inbox deduplication
        inbox = get_inbox_sessions("all")
        matching = [s for s in inbox if s.get("whatsapp_identity") == self.wa_identity or s.get("wa_id") == self.wa_id]
        self.assertEqual(len(matching), 1)


