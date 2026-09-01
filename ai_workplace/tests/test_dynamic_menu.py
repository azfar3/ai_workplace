"""
ai_workplace/tests/test_dynamic_menu.py
─────────────────────────────────────────
Unit tests for Dynamic Menu & Menu Selection Parser.
"""

import unittest
from unittest.mock import patch

from ai_workplace.conversation.menu import (
    build_menu,
    parse_menu_selection,
    build_invalid_selection_message,
)
from ai_workplace.response.builder import build_unregistered_response
from ai_workplace.services.registry import get_available_services_for_context
from ai_workplace.whatsapp.outbound import OutboundMessage


class TestDynamicMenu(unittest.TestCase):

    def setUp(self):
        self.emp_context = {
            "full_name": "John Doe",
            "person_type": "Employee",
            "allowed_services": ["hr", "policy", "travel", "help"],
            "preferred_language": "English",
        }
        self.deliverable_context = {
            "full_name": "Sara Deliverable",
            "person_type": "Employee",
            "staff_category": "project_deliverable",
            "allowed_services": [
                "hr",
                "deliverables",
                "payroll",
                "pay_tax_deduction",
                "pay_bank_letter",
                "pay_bank_faysal",
                "pay_bank_scb",
                "policies",
                "concerns",
                "contact_hr",
            ],
            "preferred_language": "English",
        }
        self.guest_context = {
            "full_name": None,
            "person_type": "Guest",
            "allowed_services": [],
            "preferred_language": "English",
        }

    def test_build_employee_interactive_menu(self):
        menu_out, services = build_menu(self.emp_context)
        self.assertIsInstance(menu_out, OutboundMessage)
        self.assertTrue(menu_out.is_interactive())
        if menu_out.interactive["type"] == "button":
            self.assertTrue(menu_out.follow_up)
            list_out = menu_out.follow_up[0]
            rows = list_out.interactive["action"]["sections"][0]["rows"]
            # Quick buttons: first 3 items by menu sequence
            quick_titles = [btn["reply"]["id"] for btn in menu_out.interactive["action"]["buttons"]]
            self.assertEqual(quick_titles[0], f"svc_{services[0]['key']}")
        else:
            rows = menu_out.interactive["action"]["sections"][0]["rows"]
            self.assertIn("Please choose a service below.", menu_out.body_text)
        self.assertEqual(rows[0]["id"], f"svc_{services[0]['key']}")
        self.assertGreaterEqual(len(services), 1)

    def test_build_deliverable_staff_menu_filtering(self):
        services = get_available_services_for_context(self.deliverable_context)
        keys = {svc["key"] for svc in services}
        self.assertIn("hr", keys)
        self.assertIn("deliverables", keys)
        self.assertIn("payroll", keys)
        self.assertNotIn("attendance_leave", keys)
        self.assertNotIn("travel", keys)

    @patch("ai_workplace.services.registry._fetch_menu_items")
    def test_deliverable_payroll_submenu_partial_access(self, mock_fetch):
        mock_fetch.return_value = [
            {"menu_key": "pay_download_slip", "title": "Download Slip", "sequence": 1},
            {"menu_key": "pay_tax_deduction", "title": "Tax", "sequence": 3},
            {"menu_key": "pay_bank_letter", "title": "Bank Letter", "sequence": 5},
        ]
        services = get_available_services_for_context(self.deliverable_context, parent_key="payroll")
        keys = {svc["key"] for svc in services}
        self.assertIn("pay_tax_deduction", keys)
        self.assertIn("pay_bank_letter", keys)
        self.assertNotIn("pay_download_slip", keys)

    def test_build_deliverable_interactive_menu(self):
        services = get_available_services_for_context(self.deliverable_context)
        menu_out, built_services = build_menu(self.deliverable_context)
        if menu_out.interactive["type"] == "button" and menu_out.follow_up:
            rows = menu_out.follow_up[0].interactive["action"]["sections"][0]["rows"]
        else:
            rows = menu_out.interactive["action"]["sections"][0]["rows"]
        self.assertEqual(rows[0]["id"], f"svc_{built_services[0]['key']}")
        self.assertEqual(built_services[0]["key"], services[0]["key"])

    def test_unregistered_response_b2(self):
        msg = build_unregistered_response(self.guest_context)
        self.assertIn("not registered for MicroMerger self-service", msg)

    def test_interactive_id_selection(self):
        svc = parse_menu_selection("svc_hr", self.emp_context)
        self.assertIsNotNone(svc)
        self.assertEqual(svc["key"], "hr")

    def test_numeric_selection_employee(self):
        services = get_available_services_for_context(self.emp_context)
        self.assertEqual(parse_menu_selection("1", self.emp_context)["key"], services[0]["key"])
        if len(services) >= 3:
            self.assertEqual(parse_menu_selection("3", self.emp_context)["key"], services[2]["key"])


    def test_invalid_selection_returns_interactive(self):
        inv = build_invalid_selection_message(self.emp_context)
        self.assertIsInstance(inv, OutboundMessage)
        self.assertTrue(inv.is_interactive())
