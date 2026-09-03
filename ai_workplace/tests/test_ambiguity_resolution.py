"""
ai_workplace/tests/test_ambiguity_resolution.py
─────────────────────────────────────────────────
Unit tests for WhatsApp Identity disambiguation by active status and empty project field.
"""

import unittest
import frappe
from ai_workplace.identity.resolver import resolve_identity, _Candidate, _classify, IdentityResult


class TestAmbiguityResolution(unittest.TestCase):
    def test_single_active_candidate(self):
        candidates = [
            _Candidate(user="emp1@example.com", employee="HR-EMP-0001", full_name="Emp One", is_active=True, project=None),
            _Candidate(user="emp2@example.com", employee="HR-EMP-0002", full_name="Emp Two", is_active=False, project=None),
        ]
        res = _classify(candidates, "+923001111111")
        self.assertEqual(res.status, "matched")
        self.assertEqual(res.employee, "HR-EMP-0001")

    def test_multiple_active_disambiguated_by_empty_project(self):
        candidates = [
            _Candidate(user="emp1@example.com", employee="HR-EMP-0001", full_name="Project Staff", is_active=True, project="Project Alpha"),
            _Candidate(user="emp2@example.com", employee="HR-EMP-0002", full_name="Permanent Staff", is_active=True, project=None),
        ]
        res = _classify(candidates, "+923001111111")
        self.assertEqual(res.status, "matched")
        self.assertEqual(res.employee, "HR-EMP-0002")

    def test_multiple_active_all_empty_project_becomes_ambiguous(self):
        candidates = [
            _Candidate(user="emp1@example.com", employee="HR-EMP-0001", full_name="Staff One", is_active=True, project=""),
            _Candidate(user="emp2@example.com", employee="HR-EMP-0002", full_name="Staff Two", is_active=True, project=None),
        ]
        res = _classify(candidates, "+923001111111")
        self.assertEqual(res.status, "ambiguous")
        self.assertIsNone(res.employee)

    def test_multiple_active_all_with_project_becomes_ambiguous(self):
        candidates = [
            _Candidate(user="emp1@example.com", employee="HR-EMP-0001", full_name="Staff One", is_active=True, project="Project Alpha"),
            _Candidate(user="emp2@example.com", employee="HR-EMP-0002", full_name="Staff Two", is_active=True, project="Project Beta"),
        ]
        res = _classify(candidates, "+923001111111")
        self.assertEqual(res.status, "ambiguous")
        self.assertIsNone(res.employee)
