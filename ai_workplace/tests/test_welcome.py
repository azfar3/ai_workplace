"""
ai_workplace/tests/test_welcome.py
────────────────────────────────────
Unit tests for the welcome message service.
No database access required.
"""

import unittest

from ai_workplace.services.welcome import build_welcome_message, _personalized_welcome, _generic_welcome


class TestWelcomeMessage(unittest.TestCase):

    def test_matched_identity_personalized(self):
        identity = {
            "status": "matched",
            "full_name": "John Doe",
            "user": "john@example.com",
            "employee": "HR-EMP-0001",
            "normalized_phone": "+923001234567",
        }
        msg = build_welcome_message(identity)
        self.assertIn("John Doe", msg)
        self.assertIn("👋", msg)
        self.assertIn("How can I help you today?", msg)

    def test_matched_no_name_falls_back_to_there(self):
        identity = {
            "status": "matched",
            "full_name": None,
            "user": "john@example.com",
            "employee": None,
            "normalized_phone": "+923001234567",
        }
        msg = build_welcome_message(identity)
        self.assertIn("there", msg)
        self.assertIn("👋", msg)

    def test_guest_identity_generic(self):
        identity = {
            "status": "guest",
            "full_name": None,
            "user": None,
            "employee": None,
            "normalized_phone": "+923009999999",
        }
        msg = build_welcome_message(identity)
        self.assertNotIn("None", msg)
        self.assertIn("Hello", msg)
        self.assertIn("👋", msg)
        self.assertIn("How can I help you today?", msg)

    def test_ambiguous_identity_generic(self):
        identity = {"status": "ambiguous", "full_name": "Alice", "user": "a@b.com"}
        msg = build_welcome_message(identity)
        # Must NOT expose the real name for ambiguous identities.
        self.assertNotIn("Alice", msg)
        self.assertIn("Hello", msg)

    def test_inactive_identity_generic(self):
        identity = {"status": "inactive", "full_name": "Bob", "user": "b@b.com"}
        msg = build_welcome_message(identity)
        self.assertNotIn("Bob", msg)
        self.assertIn("Hello", msg)

    def test_unknown_status_generic(self):
        identity = {"status": "some_future_status"}
        msg = build_welcome_message(identity)
        self.assertIn("Hello", msg)

    def test_generic_does_not_reveal_employee_status(self):
        """Guest response must not reveal 'not registered', 'not found', etc."""
        msg = _generic_welcome()
        for forbidden in [
            "not registered",
            "not found",
            "no employee",
            "not an employee",
            "account",
            "number",
        ]:
            self.assertNotIn(forbidden.lower(), msg.lower())

    def test_personalized_format(self):
        msg = _personalized_welcome("Jane Smith")
        self.assertEqual(msg, "Welcome Jane Smith! 👋\n\nHow can I help you today?")

    def test_generic_format(self):
        msg = _generic_welcome()
        self.assertEqual(msg, "Hello! 👋\n\nWelcome. How can I help you today?")
