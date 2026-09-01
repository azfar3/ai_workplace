"""
ai_workplace/tests/test_resolver.py
──────────────────────────────────────
Unit tests for identity resolution and phone field matching.
Covers BRD IR-01/IR-03 and Playwright PW-001–PW-004 scenarios.
"""

import unittest
from unittest.mock import patch

from ai_workplace.identity.resolver import (
    _Candidate,
    _classify,
    _phone_field_matches,
    resolve_identity,
)


class TestPhoneFieldMatches(unittest.TestCase):
    """PW-001 / PW-002 — personal and official mobile format matrix."""

    TARGET = "+923001234567"

    def test_cell_number_local_zero_prefix(self):
        self.assertTrue(_phone_field_matches("03001234567", self.TARGET))

    def test_cell_number_country_code_no_plus(self):
        self.assertTrue(_phone_field_matches("923001234567", self.TARGET))

    def test_cell_number_e164(self):
        self.assertTrue(_phone_field_matches("+923001234567", self.TARGET))

    def test_cell_number_with_separators(self):
        self.assertTrue(_phone_field_matches("0300 123-4567", self.TARGET))

    def test_company_mobile_local_format(self):
        self.assertTrue(_phone_field_matches("03001234567", self.TARGET))

    def test_company_mobile_international(self):
        self.assertTrue(_phone_field_matches("923001234567", self.TARGET))

    def test_no_match_different_number(self):
        self.assertFalse(_phone_field_matches("03009999999", self.TARGET))

    def test_empty_stored_value(self):
        self.assertFalse(_phone_field_matches(None, self.TARGET))
        self.assertFalse(_phone_field_matches("", self.TARGET))

    def test_invalid_stored_value_does_not_crash(self):
        self.assertFalse(_phone_field_matches("not-a-phone", self.TARGET))


class TestClassify(unittest.TestCase):
    """Classification rules for active, inactive, guest, ambiguous."""

    def test_single_active_candidate_matched(self):
        c = _Candidate(user="u@x.com", employee="EMP-1", full_name="John", is_active=True)
        result = _classify([c], "+923001234567")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.employee, "EMP-1")

    def test_inactive_only_returns_inactive(self):
        c = _Candidate(user="u@x.com", employee="EMP-1", full_name="John", is_active=False)
        result = _classify([c], "+923001234567")
        self.assertEqual(result.status, "inactive")

    def test_no_candidates_guest(self):
        result = _classify([], "+923009999999")
        self.assertEqual(result.status, "guest")

    def test_multiple_active_ambiguous(self):
        c1 = _Candidate(user="a@x.com", employee="EMP-1", is_active=True)
        c2 = _Candidate(user="b@x.com", employee="EMP-2", is_active=True)
        result = _classify([c1, c2], "+923001234567")
        self.assertEqual(result.status, "ambiguous")


class TestResolveIdentityMocked(unittest.TestCase):
    """End-to-end resolve_identity with mocked ERP data."""

    def _mock_employees(self, employees, users=None):
        users = users or []

        def side_effect(doctype, **kwargs):
            if doctype == "Employee":
                return employees
            if doctype == "User":
                return users
            return []

        return patch("ai_workplace.identity.resolver.frappe.get_all", side_effect=side_effect)

    def test_active_employee_via_cell_number_local(self):
        employees = [{
            "name": "EMP-001",
            "employee_name": "John Doe",
            "user_id": "john@example.com",
            "status": "Active",
            "cell_number": "03001234567",
            "company_mobile": "",
        }]
        with self._mock_employees(employees):
            result = resolve_identity("923001234567")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.employee, "EMP-001")
        self.assertEqual(result.normalized_phone, "+923001234567")

    def test_active_employee_via_company_mobile(self):
        employees = [{
            "name": "EMP-002",
            "employee_name": "Jane Smith",
            "user_id": "jane@example.com",
            "status": "Active",
            "cell_number": "",
            "company_mobile": "+923001234567",
        }]
        with self._mock_employees(employees):
            result = resolve_identity("03001234567")
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.full_name, "Jane Smith")

    def test_left_employee_inactive(self):
        employees = [{
            "name": "EMP-003",
            "employee_name": "Former Staff",
            "user_id": "former@example.com",
            "status": "Left",
            "cell_number": "03001234567",
            "company_mobile": "",
        }]
        with self._mock_employees(employees):
            result = resolve_identity("03001234567")
        self.assertEqual(result.status, "inactive")

    def test_unknown_number_guest(self):
        with self._mock_employees([]):
            result = resolve_identity("923009999999")
        self.assertEqual(result.status, "guest")

    def test_duplicate_active_employees_ambiguous(self):
        employees = [
            {
                "name": "EMP-A",
                "employee_name": "Alice",
                "user_id": "a@example.com",
                "status": "Active",
                "cell_number": "03001234567",
                "company_mobile": "",
            },
            {
                "name": "EMP-B",
                "employee_name": "Bob",
                "user_id": "b@example.com",
                "status": "Active",
                "cell_number": "03001234567",
                "company_mobile": "",
            },
        ]
        with self._mock_employees(employees):
            result = resolve_identity("03001234567")
        self.assertEqual(result.status, "ambiguous")
