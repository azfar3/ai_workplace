"""
Tests for Chat with HR OPEN/CLOSED WhatsApp prompts.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_workplace.services.hr_contact_prompt import (
    build_contact_hr_options_message,
    handle_contact_hr_prompt_reply,
    is_contact_hr_menu_resubmit,
)
from ai_workplace.services.office_hours import HR_STATUS_CLOSED, HR_STATUS_OPEN


class TestHRContactAvailability(unittest.TestCase):
    @patch("ai_workplace.services.office_hours.get_hr_support_status")
    def test_closed_shows_leave_message_and_main_menu_buttons(self, mock_status):
        mock_status.return_value = {
            "is_open": False,
            "status": HR_STATUS_CLOSED,
            "closed_reason": "outside_hours",
        }
        with patch(
            "ai_workplace.services.office_hours.build_closed_hours_message",
            return_value="HR is closed.",
        ):
            outbound = build_contact_hr_options_message(
                {"preferred_language": "English", "employee": "EMP-001"}
            )
        buttons = outbound.interactive["action"]["buttons"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["reply"]["title"], "Leave Message")
        self.assertEqual(buttons[1]["reply"]["title"], "Main Menu")
        self.assertEqual(buttons[1]["reply"]["id"], "main_menu")

    def test_resubmit_detection(self):
        self.assertTrue(is_contact_hr_menu_resubmit("svc_contact_hr"))
        self.assertTrue(is_contact_hr_menu_resubmit("💬 Chat with HR"))
        self.assertFalse(is_contact_hr_menu_resubmit("hr_wait_connect"))

    @patch("ai_workplace.services.office_hours.get_hr_support_status")
    def test_resubmit_rebuilds_full_prompt(self, mock_status):
        mock_status.return_value = {
            "is_open": False,
            "status": HR_STATUS_CLOSED,
            "closed_reason": "outside_hours",
        }
        conv = type("Conv", (), {"name": "TEST"})()
        with patch(
            "ai_workplace.services.office_hours.build_closed_hours_message",
            return_value="HR is closed.",
        ):
            outbound = handle_contact_hr_prompt_reply(
                conv,
                "svc_contact_hr",
                {"preferred_language": "English"},
            )
        self.assertIn("Chat with HR", outbound.body_text or "")
        self.assertTrue(outbound.is_interactive())
