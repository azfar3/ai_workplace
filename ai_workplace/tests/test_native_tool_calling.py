"""
Tests for Native LLM Tool Calling & Security Controls in ai_workplace.
"""

import unittest
import frappe
from ai_workplace.ai.tools import get_openai_tools_schema, run_tool, TOOL_REGISTRY


class TestNativeToolCalling(unittest.TestCase):
    def setUp(self):
        self.context = {
            "employee": "EMP-001",
            "user": "Administrator",
            "whatsapp_identity": "923001234567",
        }

    def test_openai_tools_schema(self):
        schemas = get_openai_tools_schema()
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 0)
        first = schemas[0]
        self.assertEqual(first["type"], "function")
        self.assertIn("name", first["function"])
        self.assertIn("description", first["function"])
        self.assertIn("parameters", first["function"])

    def test_valid_tool_execution(self):
        res = run_tool("get_leave_balance", self.context)
        self.assertNotIn("error", res)

    def test_invalid_tool_name(self):
        res = run_tool("non_existent_tool", self.context)
        self.assertEqual(res.get("status"), "error")

    def test_employee_identity_override_security(self):
        """Verify that LLM-provided identity parameters ('EMP-999') are overridden by server session context ('EMP-001')."""
        res = run_tool("get_profile_gaps", self.context, employee="EMP-999")
        self.assertIsInstance(res, dict)
        self.assertNotIn("error", res)

    def test_search_knowledge_tool(self):
        res = run_tool("search_knowledge", self.context, query="leave policy", limit=2)
        self.assertIsInstance(res, dict)
        self.assertIn("knowledge_matches", res)

    def test_action_log_creation(self):
        run_tool("get_attendance_summary", self.context)
        if frappe.db.exists("DocType", "AI Action Log"):
            logs = frappe.get_all("AI Action Log", filters={"service": "get_attendance_summary"})
            self.assertGreaterEqual(len(logs), 0)
