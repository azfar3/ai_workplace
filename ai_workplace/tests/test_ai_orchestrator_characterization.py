import unittest
import frappe

from ai_workplace.identity.resolver import IdentityResult
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.whatsapp.outbound import OutboundMessage

class TestAIOrchestratorCharacterization(unittest.TestCase):

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

    def advance_to_menu(self):
        # 1. First message to create conversation
        process_message("Hi", self.identity, message_id=f"init-1-{self.id()}", trace_id="tr-init")
        # 2. Select language
        process_message("lang_en", self.identity, message_id=f"init-2-{self.id()}", trace_id="tr-init2")

    def test_leave_balance_deterministic(self):
        self.advance_to_menu()
        resp = process_message("what is my leave balance?", self.identity, message_id="m-1", trace_id="tr-1")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("Leave Balance", resp.body_text)
        
    def test_salary_slip_deterministic(self):
        self.advance_to_menu()
        resp = process_message("show my salary slip", self.identity, message_id="m-2", trace_id="tr-2")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("Salary", resp.body_text)

    def test_office_timings_deterministic(self):
        self.advance_to_menu()
        resp = process_message("what are the office timings", self.identity, message_id="m-3", trace_id="tr-3")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertIn("Timings", resp.body_text)

