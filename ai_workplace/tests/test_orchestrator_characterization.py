import unittest
import frappe

from ai_workplace.identity.resolver import IdentityResult
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.whatsapp.outbound import OutboundMessage

class TestOrchestratorExtendedCharacterization(unittest.TestCase):

    def setUp(self):
        frappe.db.rollback()
        
        # Get or create User
        user_email = "john@example.com"
        if not frappe.db.exists("User", user_email):
            frappe.get_doc({
                "doctype": "User",
                "email": user_email,
                "first_name": "John",
                "send_welcome_email": 0,
            }).insert(ignore_permissions=True)
            
        # Get or create Employee
        emp = frappe.db.get_value("Employee", {"user_id": user_email}, "name")
        if not emp:
            doc = frappe.get_doc({
                "doctype": "Employee",
                "first_name": "John",
                "user_id": user_email,
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01"
            }).insert(ignore_permissions=True)
            emp = doc.name

        self.phone = "+923001234567"
        self.identity = IdentityResult(
            status="matched",
            normalized_phone=self.phone,
            user=user_email,
            employee=emp,
            full_name="John Doe",
        )
        
        # Advance conversation to English menu
        process_message("Hi", self.identity, message_id=f"init-1-{self.id()}", trace_id="tr-init")
        self.menu_resp = process_message("lang_en", self.identity, message_id=f"init-2-{self.id()}", trace_id="tr-init2")

    def tearDown(self):
        frappe.db.rollback()
        
    def test_payroll_menu_navigation(self):
        resp = process_message("svc_payroll", self.identity, message_id=f"pay-1-{self.id()}", trace_id="tr-pay")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.is_interactive())
        
        # Test leaf node in payroll (e.g., pay_download_slip)
        # We expect a placeholder or actual response since it's AWAITING_SELECTION
        resp_leaf = process_message("pay_download_slip", self.identity, message_id=f"pay-2-{self.id()}", trace_id="tr-pay2")
        self.assertIsInstance(resp_leaf, OutboundMessage)
        # Should be wrapped with menu again or return a document
        self.assertIsNotNone(resp_leaf.body_text)
        
    def test_attendance_menu_navigation(self):
        resp = process_message("svc_attendance_leave", self.identity, message_id=f"att-1-{self.id()}", trace_id="tr-att")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.is_interactive())
        
    def test_invalid_menu_selection_fallback(self):
        resp = process_message("invalid_svc_code", self.identity, message_id=f"inv-1-{self.id()}", trace_id="tr-inv")
        self.assertIsInstance(resp, OutboundMessage)
        # Usually fallback says invalid selection and reprints menu
        self.assertTrue(resp.is_interactive() or "menu" in resp.body_text.lower())
        
    def test_global_menu_command(self):
        resp = process_message("menu", self.identity, message_id=f"menu-1-{self.id()}", trace_id="tr-menu")
        self.assertIsInstance(resp, OutboundMessage)
        self.assertTrue(resp.is_interactive())
        self.assertIn("tap", resp.body_text.lower())
