"""
Unit tests for profile gap engine.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.services.profile_gaps import get_employee_profile_gaps, gap_flow_key, _gap


class TestProfileGaps(unittest.TestCase):
    @patch("ai_workplace.services.profile_gaps.frappe")
    @patch("ai_workplace.services.profile_gaps.get_pin_status")
    def test_pin_not_configured_gap(self, mock_pin, mock_frappe):
        mock_pin.return_value = {"configured": False}
        mock_frappe.db.get_value.return_value = type("Emp", (), {
            "name": "EMP-001",
            "employee_name": "Test",
            "image": "x",
            "cnic": "123",
            "cnic_scan_front": "a",
            "cnic_scan_back": "b",
            "date_of_issue": None,
            "valid_upto": None,
            "cell_number": "1",
            "prefered_email": "a@b.com",
            "bank_name": "Bank",
            "bank_ac_no": "123",
        })()
        mock_frappe.db.has_column.return_value = False
        mock_frappe.db.count.return_value = 1
        mock_frappe.db.exists.return_value = False

        report = get_employee_profile_gaps("EMP-001")
        keys = [g["key"] for g in report["all_gaps"]]
        self.assertIn("support_pin_not_configured", keys)

    @patch("ai_workplace.services.profile_gaps.frappe")
    @patch("ai_workplace.services.profile_gaps.get_pin_status")
    def test_gap_includes_flow_key(self, mock_pin, mock_frappe):
        mock_pin.return_value = {"configured": True}
        mock_frappe.db.get_value.return_value = type("Emp", (), {
            "name": "EMP-001",
            "employee_name": "Test",
            "image": None,
            "cnic": None,
            "cnic_scan_front": None,
            "cnic_scan_back": None,
            "valid_upto": None,
            "cell_number": "1",
            "prefered_email": "a@b.com",
            "bank_name": "Bank",
            "bank_ac_no": "123",
        })()
        mock_frappe.db.has_column.return_value = False
        mock_frappe.db.count.return_value = 0
        mock_frappe.db.exists.return_value = False

        report = get_employee_profile_gaps("EMP-001")
        cnic_gap = next(g for g in report["all_gaps"] if g["key"] == "cnic")
        self.assertEqual(cnic_gap["flow_key"], "prof_cnic_add")

    def test_gap_helper_sets_flow_key(self):
        g = _gap("bank", "Add bank", "critical", "ticket")
        self.assertEqual(g["flow_key"], "prof_bank_update")

    def test_flow_key_mapping(self):
        self.assertEqual(gap_flow_key("work_history"), "prof_work_history_ticket")


if __name__ == "__main__":
    unittest.main()
