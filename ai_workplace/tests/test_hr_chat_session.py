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
