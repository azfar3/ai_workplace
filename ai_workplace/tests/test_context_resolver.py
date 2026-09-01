"""
ai_workplace/tests/test_context_resolver.py
─────────────────────────────────────────────
Unit tests for ERP Context Resolver.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.identity.resolver import IdentityResult
from ai_workplace.context.resolver import (
    EMPLOYMENT_TYPE_CONTRACT,
    EMPLOYMENT_TYPE_DELIVERABLE,
    _allowed_services_for_staff,
    _resolve_staff_category,
    has_active_expense_claim_structure_assignment,
    get_user_context,
)


class TestContextResolver(unittest.TestCase):

    def test_guest_context_no_protected_services(self):
        identity = IdentityResult(
            status="guest",
            normalized_phone="+923009999999",
        )
        with patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English"), patch(
            "ai_workplace.context.resolver._resolve_profile_image_url", return_value=None
        ):
            context = get_user_context(identity)
        self.assertEqual(context["person_type"], "Guest")
        self.assertEqual(context["identity_status"], "guest")
        self.assertIsNone(context["user"])
        self.assertIsNone(context["employee"])
        self.assertIn("guest_careers", context["allowed_services"])
        self.assertIn("guest_number_changed", context["allowed_services"])
        self.assertEqual(context["staff_category"], "")

    def test_inactive_context_no_protected_services(self):
        identity = IdentityResult(
            status="inactive",
            normalized_phone="+923001111111",
            user="former@example.com",
            employee="EMP-OLD",
            full_name="Former Employee",
        )
        with patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English"), patch(
            "ai_workplace.context.resolver._resolve_profile_image_url", return_value=None
        ):
            context = get_user_context(identity)
        self.assertEqual(context["person_type"], "Former Employee")
        self.assertEqual(context["identity_status"], "inactive")
        self.assertIn("former_letter", context["allowed_services"])

    def test_ambiguous_context_no_protected_services(self):
        identity = IdentityResult(status="ambiguous", normalized_phone="+923002222222")
        with patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English"), patch(
            "ai_workplace.context.resolver._resolve_profile_image_url", return_value=None
        ):
            context = get_user_context(identity)
        self.assertIn("guest_careers", context["allowed_services"])
        self.assertEqual(context["identity_status"], "ambiguous")

    def test_staff_category_mapping(self):
        self.assertEqual(_resolve_staff_category("Full-time"), "permanent")
        self.assertEqual(_resolve_staff_category(EMPLOYMENT_TYPE_CONTRACT), "project_contract")
        self.assertEqual(_resolve_staff_category(EMPLOYMENT_TYPE_DELIVERABLE), "project_deliverable")

    def test_allowed_services_by_staff_category(self):
        permanent = _allowed_services_for_staff("permanent")
        self.assertIn("attendance_leave", permanent)
        self.assertIn("payroll", permanent)
        self.assertIn("travel", permanent)
        self.assertNotIn("deliverables", permanent)

        deliverable = _allowed_services_for_staff("project_deliverable")
        self.assertIn("deliverables", deliverable)
        self.assertIn("hr", deliverable)
        self.assertIn("payroll", deliverable)
        self.assertIn("pay_tax_deduction", deliverable)
        self.assertIn("pay_bank_letter", deliverable)
        self.assertNotIn("attendance_leave", deliverable)
        self.assertNotIn("pay_download_slip", deliverable)
        self.assertNotIn("travel", deliverable)

        contract = _allowed_services_for_staff("project_contract")
        self.assertIn("attendance_leave", contract)
        self.assertIn("payroll", contract)
        self.assertNotIn("travel", contract)

    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=True)
    def test_contract_staff_gets_travel_with_expense_structure(self, _mock_has):
        services = _allowed_services_for_staff("project_contract", "EMP-CON-01")
        self.assertIn("travel", services)
        self.assertIn("attendance_leave", services)
        self.assertEqual(services.index("travel"), services.index("policies") - 1)

    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=True)
    def test_deliverable_staff_gets_travel_with_expense_structure(self, _mock_has):
        services = _allowed_services_for_staff("project_deliverable", "EMP-DLV-01")
        self.assertIn("travel", services)
        self.assertIn("deliverables", services)
        self.assertIn("payroll", services)
        self.assertIn("pay_tax_deduction", services)

    @patch("ai_workplace.context.resolver.frappe")
    def test_has_active_expense_claim_structure_assignment(self, mock_frappe):
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.sql.return_value = [(1,)]
        self.assertTrue(has_active_expense_claim_structure_assignment("EMP-001"))

        mock_frappe.db.sql.return_value = []
        self.assertFalse(has_active_expense_claim_structure_assignment("EMP-001"))

    @patch("ai_workplace.context.resolver._resolve_profile_image_url", return_value=None)
    @patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English")
    @patch("ai_workplace.context.resolver.frappe")
    def test_employee_context_permanent_staff(self, mock_frappe, *_mocks):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923001234567",
            user="john@example.com",
            employee="EMP-001",
            full_name="John Doe",
        )
        emp = MagicMock()
        emp.employment_type = "Full-time"
        emp.reports_to = None
        emp.employee_name = "John Doe"
        mock_frappe.get_roles.return_value = ["Employee"]
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = emp

        context = get_user_context(identity)

        self.assertEqual(context["person_type"], "Employee")
        self.assertEqual(context["staff_category"], "permanent")
        self.assertIn("hr", context["allowed_services"])
        self.assertIn("attendance_leave", context["allowed_services"])
        self.assertIn("payroll", context["allowed_services"])
        self.assertNotIn("deliverables", context["allowed_services"])

    @patch("ai_workplace.context.resolver._resolve_profile_image_url", return_value=None)
    @patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English")
    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=False)
    @patch("ai_workplace.context.resolver.frappe")
    def test_project_contract_staff_gets_full_menus(self, mock_frappe, *_mocks):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923007778888",
            user="contract@example.com",
            employee="EMP-CON-01",
            full_name="Ali Contract",
        )
        emp = MagicMock()
        emp.employment_type = EMPLOYMENT_TYPE_CONTRACT
        emp.reports_to = "EMP-MGR-01"
        emp.employee_name = "Ali Contract"
        mock_frappe.get_roles.return_value = ["Employee"]
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = emp

        context = get_user_context(identity)

        self.assertEqual(context["person_type"], "Employee")
        self.assertEqual(context["staff_category"], "project_contract")
        self.assertIn("attendance_leave", context["allowed_services"])
        self.assertIn("payroll", context["allowed_services"])
        self.assertNotIn("deliverables", context["allowed_services"])
        self.assertNotIn("travel", context["allowed_services"])
        self.assertFalse(context["has_travel_expense_structure"])

    @patch("ai_workplace.context.resolver._resolve_profile_image_url", return_value=None)
    @patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English")
    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=True)
    @patch("ai_workplace.context.resolver.frappe")
    def test_project_contract_staff_gets_travel_with_expense_structure(self, mock_frappe, *_mocks):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923007778888",
            user="contract@example.com",
            employee="EMP-CON-01",
            full_name="Ali Contract",
        )
        emp = MagicMock()
        emp.employment_type = EMPLOYMENT_TYPE_CONTRACT
        emp.reports_to = "EMP-MGR-01"
        emp.employee_name = "Ali Contract"
        mock_frappe.get_roles.return_value = ["Employee"]
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = emp

        context = get_user_context(identity)

        self.assertIn("travel", context["allowed_services"])
        self.assertTrue(context["has_travel_expense_structure"])

    @patch("ai_workplace.context.resolver._resolve_profile_image_url", return_value=None)
    @patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English")
    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=False)
    @patch("ai_workplace.context.resolver.frappe")
    def test_project_deliverable_staff_gets_minimal_menus(self, mock_frappe, *_mocks):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923008889999",
            user="deliverable@example.com",
            employee="EMP-DLV-01",
            full_name="Sara Deliverable",
        )
        emp = MagicMock()
        emp.employment_type = EMPLOYMENT_TYPE_DELIVERABLE
        emp.reports_to = "EMP-MGR-02"
        emp.employee_name = "Sara Deliverable"
        mock_frappe.get_roles.return_value = ["Consultant", "Employee"]
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = emp

        context = get_user_context(identity)

        self.assertEqual(context["person_type"], "Employee")
        self.assertEqual(context["staff_category"], "project_deliverable")
        self.assertIn("hr", context["allowed_services"])
        self.assertIn("deliverables", context["allowed_services"])
        self.assertNotIn("attendance_leave", context["allowed_services"])
        self.assertIn("payroll", context["allowed_services"])
        self.assertIn("pay_tax_deduction", context["allowed_services"])
        self.assertNotIn("pay_download_slip", context["allowed_services"])
        self.assertNotIn("travel", context["allowed_services"])

    @patch("ai_workplace.context.resolver._resolve_profile_image_url", return_value=None)
    @patch("ai_workplace.context.resolver._resolve_preferred_language", return_value="English")
    @patch("ai_workplace.context.resolver.has_active_expense_claim_structure_assignment", return_value=True)
    @patch("ai_workplace.context.resolver.frappe")
    def test_project_deliverable_staff_gets_travel_with_expense_structure(self, mock_frappe, *_mocks):
        identity = IdentityResult(
            status="matched",
            normalized_phone="+923008889999",
            user="deliverable@example.com",
            employee="EMP-DLV-01",
            full_name="Sara Deliverable",
        )
        emp = MagicMock()
        emp.employment_type = EMPLOYMENT_TYPE_DELIVERABLE
        emp.reports_to = "EMP-MGR-02"
        emp.employee_name = "Sara Deliverable"
        mock_frappe.get_roles.return_value = ["Consultant", "Employee"]
        mock_frappe.db.exists.return_value = True
        mock_frappe.get_doc.return_value = emp

        context = get_user_context(identity)

        self.assertIn("travel", context["allowed_services"])
        self.assertIn("deliverables", context["allowed_services"])
        self.assertTrue(context["has_travel_expense_structure"])
