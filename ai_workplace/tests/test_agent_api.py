"""Tests for external agent API sharing."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAgentAPI(FrappeTestCase):
    def setUp(self):
        if not frappe.db.exists("DocType", "AI Workplace Agent"):
            self.skipTest("AI Workplace Agent DocType not installed")

        from ai_workplace.ai.seed_agents import setup_default_agents

        setup_default_agents(force=True)
        self.agent = frappe.get_doc("AI Workplace Agent", "hr_agent")
        if not self.agent.get_password("api_key"):
            self.agent.api_key = "test-key-12345"
            self.agent.allow_external_access = 1
            self.agent.save(ignore_permissions=True)
            frappe.db.commit()
        self.api_key = self.agent.get_password("api_key")

    def test_validate_missing_key(self):
        from ai_workplace.api.agent_api import _validate_agent_access

        with self.assertRaises(frappe.AuthenticationError):
            _validate_agent_access("hr_agent", "", "")

    def test_validate_wrong_key(self):
        from ai_workplace.api.agent_api import _validate_agent_access

        with self.assertRaises(frappe.AuthenticationError):
            _validate_agent_access("hr_agent", "wrong-key", "")

    def test_validate_ok(self):
        from ai_workplace.api.agent_api import _validate_agent_access

        result = _validate_agent_access("hr_agent", self.api_key, "hrms_portal")
        self.assertEqual(result["agent_slug"], "hr_agent")

    def test_integration_info(self):
        from ai_workplace.api.agent_api import get_integration_info

        info = get_integration_info("hr_agent")
        self.assertIn("endpoint_url", info)
        self.assertIn("agent_api.chat", info["endpoint_url"])
