"""
ai_workplace/tests/test_hr_chat_agents_settings.py
────────────────────────────────────────────────────
Tests for configured HR chat agents from AI Workplace Settings.
"""

import unittest
from unittest.mock import patch

import frappe

from ai_workplace.services.hr_chat import get_configured_hr_chat_agents, user_is_hr_agent


class TestHRChatAgentsSettings(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()

    def tearDown(self):
        frappe.db.rollback()

    def _mock_settings_with_agents(self, users):
        rows = [frappe._dict({"user": u, "is_active": 1}) for u in users]

        class FakeSettings:
            def get(self, key, default=None):
                if key == "hr_chat_agents":
                    return rows
                return default

        return FakeSettings()

    @patch("ai_workplace.services.hr_chat.frappe.get_single")
    @patch("ai_workplace.services.hr_chat.frappe.db.get_value", return_value=1)
    def test_configured_agent_has_access(self, _mock_enabled, mock_get_single):
        mock_get_single.return_value = self._mock_settings_with_agents(["agent.one@example.com"])
        with patch("ai_workplace.services.hr_chat.user_is_hr_manager", return_value=False):
            with patch("ai_workplace.services.hr_chat.frappe.get_roles", return_value=[]):
                self.assertIn("agent.one@example.com", get_configured_hr_chat_agents())
                self.assertTrue(user_is_hr_agent("agent.one@example.com"))
                self.assertFalse(user_is_hr_agent("other@example.com"))
