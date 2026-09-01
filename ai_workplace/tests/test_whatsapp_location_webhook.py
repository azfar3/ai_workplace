"""
Tests for WhatsApp location webhook routing and HR session priority.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.conversation.manager import conversation_priority_expects_location
from ai_workplace.conversation.state import ConversationState


class TestConversationPriorityLocation(unittest.TestCase):
    def test_att_checkin_processing_expects_location(self):
        conv = MagicMock()
        conv.current_state = ConversationState.PROCESSING
        conv.current_intent = "att_checkin"
        self.assertTrue(conversation_priority_expects_location(conv))

    def test_att_checkout_processing_expects_location(self):
        conv = MagicMock()
        conv.current_state = ConversationState.PROCESSING
        conv.current_intent = "att_checkout"
        self.assertTrue(conversation_priority_expects_location(conv))

    def test_menu_state_does_not_expect_location(self):
        conv = MagicMock()
        conv.current_state = ConversationState.MENU
        conv.current_intent = "att_checkin"
        self.assertFalse(conversation_priority_expects_location(conv))

    def test_hr_profile_does_not_expect_location(self):
        conv = MagicMock()
        conv.current_state = ConversationState.PROCESSING
        conv.current_intent = "prof_cnic"
        self.assertFalse(conversation_priority_expects_location(conv))


class TestInboundLocationRouting(unittest.TestCase):
    @patch("ai_workplace.conversation.orchestrator.process_inbound_location")
    @patch("ai_workplace.conversation.manager.get_or_create_conversation")
    @patch("ai_workplace.conversation.manager.conversation_priority_expects_location")
    @patch("ai_workplace.services.hr_chat.get_active_session_for_identity")
    @patch("ai_workplace.api.whatsapp_webhook._create_message_log")
    @patch("ai_workplace.api.whatsapp_webhook._is_duplicate")
    @patch("ai_workplace.api.whatsapp_webhook.resolve_identity")
    def test_attendance_flow_takes_priority_over_hr_session(
        self,
        mock_resolve,
        mock_dup,
        mock_log,
        mock_session,
        mock_priority,
        mock_conv,
        mock_process_loc,
    ):
        from ai_workplace.api.whatsapp_webhook import _process_inbound_location
        from ai_workplace.whatsapp.outbound import OutboundMessage

        mock_dup.return_value = False
        mock_resolve.return_value = MagicMock(whatsapp_identity="WI-1")
        mock_log.return_value = "LOG-1"
        mock_session.return_value = "HR-SESSION-1"
        mock_priority.return_value = True
        mock_conv.return_value = MagicMock()
        mock_process_loc.return_value = OutboundMessage(body_text="Checked in")

        parsed = {
            "message_id": "wamid.loc1",
            "wa_id": "923001234567",
            "phone_number": "923001234567",
            "latitude": 33.6844,
            "longitude": 73.0479,
            "location_name": "Office",
        }
        resp = _process_inbound_location(parsed, "trace-1")
        self.assertEqual(resp.status_code, 200)
        mock_process_loc.assert_called_once()

    @patch("ai_workplace.services.hr_chat.append_inbound_message")
    @patch("ai_workplace.services.hr_chat.get_session_doc")
    @patch("ai_workplace.conversation.orchestrator.process_inbound_location")
    @patch("ai_workplace.conversation.manager.get_or_create_conversation")
    @patch("ai_workplace.conversation.manager.conversation_priority_expects_location")
    @patch("ai_workplace.services.hr_chat.get_active_session_for_identity")
    @patch("ai_workplace.api.whatsapp_webhook._finalize_log")
    @patch("ai_workplace.api.whatsapp_webhook._create_message_log")
    @patch("ai_workplace.api.whatsapp_webhook._is_duplicate")
    @patch("ai_workplace.api.whatsapp_webhook.resolve_identity")
    def test_hr_session_receives_location_when_no_attendance_flow(
        self,
        mock_resolve,
        mock_dup,
        mock_log,
        mock_finalize,
        mock_session,
        mock_priority,
        mock_conv,
        mock_process_loc,
        mock_get_session,
        mock_append,
    ):
        from ai_workplace.api.whatsapp_webhook import _process_inbound_location

        mock_dup.return_value = False
        mock_resolve.return_value = MagicMock(whatsapp_identity="WI-1")
        mock_log.return_value = "LOG-1"
        mock_session.return_value = "HR-SESSION-1"
        mock_priority.return_value = False
        mock_conv.return_value = MagicMock()
        session_doc = MagicMock(ready_for_hr=True, status="Active")
        mock_get_session.return_value = session_doc

        parsed = {
            "message_id": "wamid.loc2",
            "wa_id": "923001234567",
            "phone_number": "923001234567",
            "latitude": 33.6844,
            "longitude": 73.0479,
            "location_name": "Office",
        }
        resp = _process_inbound_location(parsed, "trace-2")
        self.assertEqual(resp.status_code, 200)
        mock_append.assert_called_once()
        mock_process_loc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
