"""
End-to-end tests for WhatsApp profile completion flows (contact + CNIC + media).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.profile_completion import (
    handle_profile_flow_media,
    handle_profile_flow_message,
    start_profile_flow,
)


def _mock_conv(draft: dict | None = None, intent: str = "prof_contact_update"):
    conv = MagicMock()
    conv.name = "CONV-TEST-001"
    conv.draft_payload = json.dumps(draft) if draft else None
    conv.current_intent = intent
    conv.current_state = ConversationState.PROCESSING
    conv.preferred_language = "English"
    return conv


class TestContactFlowComplete(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_contact_flow_submits_ticket_on_skip(self, mock_submit, mock_update):
        conv = _mock_conv(
            {
                "flow": "prof_contact_update",
                "step": "emergency",
                "data": {"cell_number": "03111123678", "prefered_email": "a@test.com"},
            }
        )
        context = {"employee": "EMP-TEST-001", "erp_user": "test@example.com"}
        mock_submit.return_value = MagicMock(body_text="✅ Request submitted: *EPCR-001*")

        handle_profile_flow_message(conv, "Skip", context)

        mock_submit.assert_called_once()
        args = mock_submit.call_args[0]
        self.assertEqual(args[2], "Contact Change")
        proposed = args[3]
        self.assertEqual(proposed["cell_number"], "03111123678")
        self.assertNotIn("emergency_phone_number", proposed)

    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_contact_flow_submits_ticket_with_emergency(self, mock_submit, mock_update):
        conv = _mock_conv(
            {
                "flow": "prof_contact_update",
                "step": "emergency",
                "data": {"cell_number": "03111123678", "prefered_email": "a@test.com"},
            }
        )
        context = {"employee": "EMP-TEST-001", "erp_user": "test@example.com"}
        mock_submit.return_value = MagicMock(body_text="submitted")

        handle_profile_flow_message(conv, "03001234567", context)

        proposed = mock_submit.call_args[0][3]
        self.assertEqual(proposed["emergency_phone_number"], "03001234567")


class TestMediaPriorityRouting(unittest.TestCase):
    def test_profile_flow_takes_priority_over_hr_session(self):
        from ai_workplace.conversation.manager import conversation_priority_expects_media
        from ai_workplace.conversation.state import ConversationState

        conv = MagicMock()
        conv.current_state = ConversationState.PROCESSING
        conv.current_intent = "prof_cnic_add"
        self.assertTrue(conversation_priority_expects_media(conv))

        conv.current_state = ConversationState.AWAITING_SELECTION
        self.assertFalse(conversation_priority_expects_media(conv))

        conv.current_state = ConversationState.LIVE_HR_CHAT
        conv.current_intent = None
        self.assertFalse(conversation_priority_expects_media(conv))


class TestCnicFlowMedia(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.update_conversation")
    def test_cnic_front_scan_advances_to_back(self, mock_update):
        conv = _mock_conv(
            {"flow": "prof_cnic_add", "step": "front_scan", "data": {"cnic": "3405408765645"}},
            intent="prof_cnic_add",
        )
        context = {"employee": "EMP-TEST-001"}

        out = handle_profile_flow_media(conv, context, "/files/cnic-front.jpg")

        self.assertIn("back", out.body_text.lower())
        saved = json.loads(mock_update.call_args[1]["draft_payload"])
        self.assertEqual(saved["step"], "back_scan")
        self.assertEqual(saved["data"]["cnic_scan_front"], "/files/cnic-front.jpg")

    @patch("ai_workplace.services.profile_completion.update_conversation")
    def test_cnic_text_at_scan_step_prompts_for_photo(self, mock_update):
        conv = _mock_conv(
            {"flow": "prof_cnic_add", "step": "front_scan", "data": {"cnic": "3405408765645"}},
            intent="prof_cnic_add",
        )
        context = {"employee": "EMP-TEST-001"}

        out = handle_profile_flow_message(conv, "Uploaded", context)

        self.assertIn("photo attachment", out.body_text.lower())
        mock_update.assert_not_called()

    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_cnic_flow_submits_ticket_at_end(self, mock_submit):
        conv = _mock_conv(
            {
                "flow": "prof_cnic_add",
                "step": "expiry_date",
                "data": {
                    "cnic": "3405408765645",
                    "cnic_scan_front": "/files/front.jpg",
                    "cnic_scan_back": "/files/back.jpg",
                    "date_of_issue": "2020-01-01",
                },
            },
            intent="prof_cnic_add",
        )
        mock_submit.return_value = MagicMock(body_text="submitted")
        context = {"employee": "EMP-TEST-001"}

        handle_profile_flow_message(conv, "2030-01-01", context)

        mock_submit.assert_called_once()
        self.assertEqual(mock_submit.call_args[0][2], "CNIC Change")


class TestWhatsappProfileTicketSubmit(unittest.TestCase):
    @patch("ai_workplace.api.profile._submit_profile_change_request")
    def test_submit_whatsapp_skips_scope_and_sets_user(self, mock_submit):
        from ai_workplace.api.profile import submit_whatsapp_profile_change_request

        mock_submit.return_value = {"success": True, "name": "EPCR-001", "status": "Submitted"}
        prev = frappe.session.user
        try:
            submit_whatsapp_profile_change_request(
                "EMP-TEST-001",
                "Contact Change",
                [{"field": "contact_change", "proposed_json": "{}"}],
                context={"employee": "EMP-TEST-001", "erp_user": "Administrator"},
            )
        finally:
            frappe.set_user(prev)

        mock_submit.assert_called_once()
        self.assertTrue(mock_submit.call_args[1].get("skip_scope_check"))


class TestWhatsappProfileApply(unittest.TestCase):
    @patch("ai_workplace.api.profile._apply_direct_profile_update")
    def test_apply_whatsapp_sets_user_and_skips_scope(self, mock_apply):
        from ai_workplace.api.profile import apply_whatsapp_profile_update

        mock_apply.return_value = {"success": True, "updated_fields": ["cell_number"]}
        prev = frappe.session.user
        try:
            apply_whatsapp_profile_update(
                "EMP-TEST-001",
                {"cell_number": "03001234567"},
                {"employee": "EMP-TEST-001", "erp_user": "Administrator"},
            )
        finally:
            frappe.set_user(prev)

        mock_apply.assert_called_once()
        self.assertTrue(mock_apply.call_args[1].get("skip_scope_check"))


class TestStartProfileFlow(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.update_conversation")
    def test_start_contact_flow_includes_approval_note(self, mock_update):
        conv = _mock_conv(None, intent=None)
        context = {"employee": "EMP-TEST-001"}

        out = start_profile_flow(conv, context, "prof_contact_update")

        self.assertIn("mobile number", out.body_text.lower())
        self.assertIn("HR for approval", out.body_text)
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args[1]["current_intent"], "prof_contact_update")


if __name__ == "__main__":
    unittest.main()
