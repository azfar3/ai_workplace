"""
ai_workplace/tests/test_dynamic_menu.py
─────────────────────────────────────────
Unit tests for Dynamic Menu & Menu Selection Parser.
"""

import unittest

from ai_workplace.conversation.menu import build_menu, parse_menu_selection, build_invalid_selection_message


class TestDynamicMenu(unittest.TestCase):

    def setUp(self):
        self.emp_context = {
            "full_name": "John Doe",
            "person_type": "Employee",
            "allowed_services": ["hr", "policy", "travel", "help"],
            "preferred_language": "English",
        }
        self.guest_context = {
            "full_name": None,
            "person_type": "Guest",
            "allowed_services": ["help"],
            "preferred_language": "English",
        }

    def test_build_employee_menu(self):
        menu_text, services = build_menu(self.emp_context)
        self.assertIn("Welcome John Doe! 👋", menu_text)
        self.assertIn("1️⃣ My HR", menu_text)
        self.assertIn("2️⃣ My Policies", menu_text)
        self.assertIn("3️⃣ My Travel", menu_text)
        self.assertIn("4️⃣ Help", menu_text)
        self.assertEqual(len(services), 4)

    def test_build_guest_menu(self):
        menu_text, services = build_menu(self.guest_context)
        self.assertIn("Hello! 👋", menu_text)
        self.assertNotIn("My HR", menu_text)
        self.assertIn("1️⃣ Help", menu_text)
        self.assertEqual(len(services), 1)

    def test_numeric_selection(self):
        svc_1 = parse_menu_selection("1", self.emp_context)
        self.assertIsNotNone(svc_1)
        self.assertEqual(svc_1["key"], "hr")

        svc_2 = parse_menu_selection("2", self.emp_context)
        self.assertIsNotNone(svc_2)
        self.assertEqual(svc_2["key"], "policy")

        svc_3 = parse_menu_selection("3", self.emp_context)
        self.assertIsNotNone(svc_3)
        self.assertEqual(svc_3["key"], "travel")

        svc_4 = parse_menu_selection("4", self.emp_context)
        self.assertIsNotNone(svc_4)
        self.assertEqual(svc_4["key"], "help")

    def test_textual_selection(self):
        svc_hr = parse_menu_selection("HR", self.emp_context)
        self.assertIsNotNone(svc_hr)
        self.assertEqual(svc_hr["key"], "hr")

        svc_pol = parse_menu_selection("My Policies", self.emp_context)
        self.assertIsNotNone(svc_pol)
        self.assertEqual(svc_pol["key"], "policy")

    def test_invalid_selection(self):
        svc_inv = parse_menu_selection("99", self.emp_context)
        self.assertIsNone(svc_inv)

        svc_xyz = parse_menu_selection("xyz", self.emp_context)
        self.assertIsNone(svc_xyz)

        inv_msg = build_invalid_selection_message(self.emp_context)
        self.assertIn("I didn't recognize that option.", inv_msg)
        self.assertIn("1️⃣ My HR", inv_msg)
