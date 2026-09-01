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
from ai_workplace.whatsapp.outbound import OutboundMessage


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

    def _text(self, outbound) -> str:
        return outbound.log_text() if isinstance(outbound, OutboundMessage) else str(outbound)

    def test_language_then_menu_flow(self):
        # 1. First message → language selection buttons
        resp1 = process_message("Hi", self.identity, message_id="msg-1", trace_id="tr-1")
        self.assertIsInstance(resp1, OutboundMessage)
        self.assertTrue(resp1.is_interactive())
        self.assertEqual(resp1.interactive["type"], "button")
        self.assertIn("preferred language", resp1.body_text.lower())

        # 2. Select English → quick action buttons + full service list follow-up
        resp2 = process_message("lang_en", self.identity, message_id="msg-2", trace_id="tr-1")
        self.assertTrue(resp2.is_interactive())
        self.assertEqual(resp2.interactive["type"], "button")
        self.assertIn("Language set to English", resp2.body_text)
        self.assertTrue(resp2.follow_up)
        rows = resp2.follow_up[0].interactive["action"]["sections"][0]["rows"]
        self.assertEqual(rows[0]["id"], "svc_hr")

        # 3. Select HR via interactive id -> submenu quick buttons + remaining list
        resp3 = process_message("svc_hr", self.identity, message_id="msg-3", trace_id="tr-1")
        self.assertTrue(resp3.is_interactive())
        self.assertEqual(resp3.interactive["type"], "button")
        self.assertTrue(resp3.follow_up)
        rows3 = resp3.follow_up[0].interactive["action"]["sections"][0]["rows"]
        row_ids = [r["id"] for r in rows3]
        self.assertIn("svc_main_menu", row_ids)

        # 4. Selecting svc_main_menu from sub menu -> returns main menu again
        resp4 = process_message("svc_main_menu", self.identity, message_id="msg-4", trace_id="tr-1")
        self.assertTrue(resp4.is_interactive())
        self.assertIn(resp4.interactive["type"], ("button", "list"))
        if resp4.interactive["type"] == "button" and resp4.follow_up:
            main_rows = resp4.follow_up[0].interactive["action"]["sections"][0]["rows"]
        else:
            main_rows = resp4.interactive["action"]["sections"][0]["rows"]
        self.assertEqual(main_rows[0]["id"], "svc_hr")

    def test_end_to_end_guest_flow_b2(self):
        guest_identity = IdentityResult(
            status="guest",
            normalized_phone="+923009999999",
        )
        resp1 = process_message("Hi", guest_identity, message_id="gmsg-1", trace_id="tr-g1")
        self.assertIn("MicroMerger", self._text(resp1))

    def test_inactive_flow_b2(self):
        inactive_identity = IdentityResult(
            status="inactive",
            normalized_phone="+923008888888",
            user="former@example.com",
            employee="EMP-OLD",
            full_name="Former Employee",
        )
        resp = process_message("Hi", inactive_identity, message_id="imsg-1", trace_id="tr-i1")
        self.assertIn("MicroMerger", self._text(resp))


    def test_simulation_harness_integration(self):
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

    def test_greeting_triggers_welcome_and_language(self):
        greetings = ["Hi", "Hello!", "Assalam o alikum", "Assalam-o-alaikum", "Salam", "AOA"]
        for g in greetings:
            resp = process_message(g, self.identity, message_id=f"gmsg-{g}", trace_id="tr-greet")
            self.assertIsInstance(resp, OutboundMessage)
            self.assertTrue(resp.is_interactive())
            self.assertEqual(resp.interactive["type"], "button")
            # Should contain personalized welcome and language prompt
            self.assertIn("Assalam-o-Alaikum", resp.body_text)
            self.assertIn("John Doe", resp.body_text)
            self.assertIn("preferred language", resp.body_text.lower())
            buttons = resp.interactive["action"]["buttons"]
            button_ids = [b["reply"]["id"] for b in buttons]
            self.assertEqual(button_ids, ["lang_en", "lang_ur", "lang_roman"])

    def test_greeting_restarts_session(self):
        # Move into HR service first
        process_message("Hi", self.identity, message_id="m-1")
        process_message("lang_en", self.identity, message_id="m-2")
        process_message("svc_hr", self.identity, message_id="m-3")

        # Now send greeting mid-session
        resp = process_message("Assalam o alikum", self.identity, message_id="m-4")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.is_interactive())
        self.assertEqual(resp.interactive["type"], "button")
        self.assertIn("Assalam-o-Alaikum", resp.body_text)
        self.assertIn("John Doe", resp.body_text)

        # Confirm conversation state was reset to AWAITING_LANGUAGE
        from ai_workplace.conversation.manager import get_or_create_conversation
        conv = get_or_create_conversation(self.identity)
        self.assertEqual(conv.current_state, "AWAITING_LANGUAGE")
        self.assertIsNone(conv.active_service)

