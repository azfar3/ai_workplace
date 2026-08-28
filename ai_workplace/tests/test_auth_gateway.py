"""
ai_workplace/tests/test_auth_gateway.py
─────────────────────────────────────────
Unit tests for Authorization Gateway.
"""

import unittest

from ai_workplace.auth.gateway import authorize


class TestAuthGateway(unittest.TestCase):

    def setUp(self):
        self.employee_context = {
            "person_type": "Employee",
            "allowed_services": ["hr", "policy", "travel", "help"],
        }
        self.consultant_context = {
            "person_type": "Consultant",
            "allowed_services": ["consultant", "policy", "travel", "help"],
        }
        self.guest_context = {
            "person_type": "Guest",
            "allowed_services": ["help"],
        }

    def test_authorized_employee_service(self):
        res = authorize(None, self.employee_context, "hr")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["service"], "hr")

    def test_unauthorized_employee_service(self):
        res = authorize(None, self.employee_context, "consultant")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_guest_restrictions(self):
        # Guest help is allowed
        res_help = authorize(None, self.guest_context, "help")
        self.assertTrue(res_help["allowed"])

        # Guest HR is blocked
        res_hr = authorize(None, self.guest_context, "hr")
        self.assertFalse(res_hr["allowed"])
        self.assertEqual(res_hr["reason"], "GUEST_RESTRICTED")

        # Guest Policy is blocked
        res_policy = authorize(None, self.guest_context, "policy")
        self.assertFalse(res_policy["allowed"])
        self.assertEqual(res_policy["reason"], "GUEST_RESTRICTED")

    def test_direct_unauthorized_attempt_rejection(self):
        # Employee B context without HR
        emp_b_context = {
            "person_type": "Employee",
            "allowed_services": ["policy", "help"],
        }
        res = authorize(None, emp_b_context, "hr")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")
