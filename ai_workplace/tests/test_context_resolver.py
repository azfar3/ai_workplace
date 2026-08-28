"""
ai_workplace/tests/test_context_resolver.py
─────────────────────────────────────────────
Unit tests for ERP Context Resolver.
"""

import unittest
import frappe

from ai_workplace.identity.resolver import IdentityResult
from ai_workplace.context.resolver import get_user_context


class TestContextResolver(unittest.TestCase):

    def test_guest_context(self):
        identity = IdentityResult(
            status="guest",
            normalized_phone="+923009999999",
        )
        context = get_user_context(identity)
        self.assertEqual(context["person_type"], "Guest")
        self.assertIsNone(context["user"])
        self.assertIsNone(context["employee"])
        self.assertEqual(context["allowed_services"], ["help"])

    def test_employee_context(self):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923001234567",
            user="john@example.com",
            employee="EMP-001",
            full_name="John Doe",
        )
        context = get_user_context(identity)
        self.assertEqual(context["person_type"], "Employee")
        self.assertEqual(context["user"], "john@example.com")
        self.assertEqual(context["employee"], "EMP-001")
        self.assertIn("hr", context["allowed_services"])
        self.assertIn("policy", context["allowed_services"])
        self.assertIn("travel", context["allowed_services"])
        self.assertIn("help", context["allowed_services"])

    def test_consultant_context_simulation(self):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923007778888",
            user="consultant@example.com",
            employee="EMP-CONS-01",
            full_name="Sarah Consultant",
        )
        # Mock role search to include Consultant
        orig_get_roles = frappe.get_roles
        try:
            frappe.get_roles = lambda u: ["Consultant", "Employee"]
            context = get_user_context(identity)
            self.assertEqual(context["person_type"], "Consultant")
            self.assertIn("consultant", context["allowed_services"])
            self.assertNotIn("hr", context["allowed_services"])
        finally:
            frappe.get_roles = orig_get_roles
