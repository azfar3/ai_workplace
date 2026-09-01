"""Tests for policies WhatsApp service."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_workplace.services.policies import build_policies_list_message, _html_to_text


class TestPoliciesService(unittest.TestCase):
    @patch("ai_workplace.services.policies.get_applicable_policies")
    def test_empty_policies_shows_menu(self, mock_get):
        mock_get.return_value = []
        outbound = build_policies_list_message({"preferred_language": "English"})
        self.assertIn("No published policies", outbound.body_text or "")

    @patch("ai_workplace.services.policies.get_applicable_policies")
    def test_policy_list_uses_pol_sel_ids(self, mock_get):
        mock_get.return_value = [
            {"name": "POL-001", "subject": "Leave Policy", "version": "2", "published_from": "2024-01-01"},
        ]
        outbound = build_policies_list_message({"preferred_language": "English"})
        rows = outbound.interactive["action"]["sections"][0]["rows"]
        self.assertEqual(rows[0]["id"], "pol_sel_POL-001")

    def test_html_to_text(self):
        text = _html_to_text("<p>Hello <b>world</b></p>")
        self.assertIn("Hello", text)
        self.assertIn("world", text)
