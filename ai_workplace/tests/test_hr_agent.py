"""
Unit tests for HR Agent service.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.services.hr_agent import (
    handle_hr_agent_message,
    _mask_sensitive,
    _fallback_tools,
    ESCALATION_KEYWORDS,
)


class TestHRAgent(unittest.TestCase):
    def test_mask_cnic(self):
        masked = _mask_sensitive("My CNIC is 1234512345671")
        self.assertNotIn("1234512345671", masked)

    def test_escalation_keywords(self):
        self.assertTrue(ESCALATION_KEYWORDS.search("I want to report harassment"))

    def test_fallback_tools_policy(self):
        tools = _fallback_tools("What is the leave policy?")
        self.assertIn("search_knowledge", tools)

    def test_fallback_tools_profile(self):
        tools = _fallback_tools("How complete is my profile?")
        self.assertIn("get_profile_gaps", tools)

    @patch("ai_workplace.services.hr_agent.complete")
    @patch("ai_workplace.services.hr_agent.search_knowledge")
    @patch("ai_workplace.services.hr_agent._select_tools")
    @patch("ai_workplace.services.hr_agent._run_tools")
    @patch("ai_workplace.services.hr_agent._log_agent_turn")
    def test_handle_message_success(self, mock_log, mock_tools, mock_select, mock_search, mock_complete):
        mock_select.return_value = ["search_knowledge"]
        mock_tools.return_value = "search_knowledge: []"
        mock_search.return_value = [{"text": "Leave policy text", "source": "policies", "source_title": "Leave Policy"}]
        mock_complete.return_value = {"success": True, "text": "You get 24 casual leaves per year."}

        conv = MagicMock()
        conv.current_intent = "hr_ai_agent"
        conv.name = "CONV-001"
        conv.whatsapp_identity = "WA-001"
        conv.erp_user = "user@test.com"
        conv.draft_payload = None

        outbound = handle_hr_agent_message(conv, "How many leaves do I get?", {"employee": "EMP-001"})
        body = outbound.body_text or ""
        self.assertIn("Leave", body)

    @patch("ai_workplace.services.hr_agent.build_button_message")
    def test_escalation_routes_to_hr(self, mock_btn):
        mock_btn.return_value = MagicMock(body_text="escalated")
        conv = MagicMock()
        conv.current_intent = "hr_ai_agent"
        outbound = handle_hr_agent_message(conv, "I need a lawyer for harassment", {"employee": "EMP-001"})
        mock_btn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
