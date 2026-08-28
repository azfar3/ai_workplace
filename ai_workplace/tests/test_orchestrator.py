"""
ai_workplace/tests/test_orchestrator.py
─────────────────────────────────────────
Integration tests for Conversation Orchestrator & End-to-End messaging pipeline.
"""

import unittest
import frappe

from ai_workplace.identity.resolver import IdentityResult
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.api.test_harness import simulate


class TestOrchestratorIntegration(unittest.TestCase):

    def setUp(self):
        frappe.db.rollback()
        self.phone = "+923001234567"
        self.identity = IdentityResult(
            status="matched",
            normalized_phone=self.phone,
            user="john@example.com",
            employee="EMP-0001",
            full_name="John Doe",
        )

    def tearDown(self):
        frappe.db.rollback()

    def test_end_to_end_employee_flow(self):
        # 1. First message "Hi" -> Expect Welcome & Menu
        resp1 = process_message("Hi", self.identity, message_id="msg-1", trace_id="tr-1")
        self.assertIn("Welcome John Doe! 👋", resp1)
        self.assertIn("1️⃣ My HR", resp1)

        # 2. Select option "1" -> Expect HR service selected
        resp2 = process_message("1", self.identity, message_id="msg-2", trace_id="tr-1")
        self.assertIn("HR service selected.", resp2)

        # 3. Send command "menu" -> Expect Main Menu again
        resp3 = process_message("menu", self.identity, message_id="msg-3", trace_id="tr-1")
        self.assertIn("How can I help you?", resp3)

        # 4. Send command "cancel" -> Expect cancelled
        resp4 = process_message("cancel", self.identity, message_id="msg-4", trace_id="tr-1")
        self.assertIn("Operation cancelled.", resp4)

    def test_end_to_end_guest_flow(self):
        guest_identity = IdentityResult(
            status="guest",
            normalized_phone="+923009999999",
        )
        resp1 = process_message("Hi", guest_identity, message_id="gmsg-1", trace_id="tr-g1")
        self.assertIn("Hello! 👋", resp1)
        self.assertNotIn("My HR", resp1)
        self.assertIn("1️⃣ Help", resp1)

        # Direct attempt to request HR by sending "1" or "HR"
        resp2 = process_message("HR", guest_identity, message_id="gmsg-2", trace_id="tr-g1")
        self.assertIn("I didn't recognize that option.", resp2)

    def test_simulation_harness_integration(self):
        # Verify test harness simulate works with orchestrator
        frappe.set_user("Administrator")
        unique_msg_id = f"sim-{frappe.generate_hash(length=8)}"
        res = simulate(
            phone_number=self.phone,
            message_id=unique_msg_id,
            message="Hi",
            dry_run=1,
        )
        self.assertIn("trace_id", res)
        self.assertIsNotNone(res.get("welcome"))
        self.assertIsNotNone(res.get("inbound_log"))
        self.assertIsNotNone(res.get("outbound_log"))

        # Verify AI Action Log created
        actions = frappe.get_all("AI Action Log", filters={"trace_id": res["trace_id"]})
        self.assertTrue(len(actions) > 0)
