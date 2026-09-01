"""
Unit tests for Employee Profile Change Request applier and validation.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock

import frappe


class TestProfileChangeApplier(unittest.TestCase):
    @patch("ai_workplace.services.profile_change_applier.frappe")
    def test_apply_education_row(self, mock_frappe):
        item = MagicMock()
        item.proposed_json = json.dumps({"qualification": "Bachelors", "school_univ": "NUST"})
        item.attachment = "/files/degree.pdf"
        item.target_field = ""

        employee = MagicMock()
        employee.append.return_value = MagicMock()

        from ai_workplace.services.profile_change_applier import _apply_item

        _apply_item(employee, "Education", item)
        employee.append.assert_called_with("education", {})

    @patch("ai_workplace.services.profile_change_applier.frappe")
    def test_apply_next_of_kin(self, mock_frappe):
        item = MagicMock()
        item.proposed_json = json.dumps({"name": "Ali", "relationship": "Brother"})
        item.attachment = ""
        item.target_field = ""
        item.proposed_value = ""

        employee = MagicMock()
        row = MagicMock()
        employee.append.return_value = row

        from ai_workplace.services.profile_change_applier import _apply_item

        _apply_item(employee, "Next of Kin", item)
        employee.append.assert_called_with("next_of_kin", {})

    @patch("ai_workplace.services.profile_change_applier.frappe")
    def test_apply_cnic_change_fields(self, mock_frappe):
        mock_frappe.db.has_column.return_value = True
        item = MagicMock()
        item.proposed_json = json.dumps({
            "cnic": "3405408765645",
            "cnic_scan_front": "/files/front.jpg",
            "valid_upto": "2030-01-01",
        })
        item.attachment = ""
        item.target_field = ""

        employee = MagicMock()

        from ai_workplace.services.profile_change_applier import _apply_item

        _apply_item(employee, "CNIC Change", item)
        self.assertTrue(employee.set.called)


class TestProfileRequestValidation(unittest.TestCase):
    def test_blocks_employee_designation_change(self):
        from ai_workplace.api.profile import _validate_ticket_items

        with self.assertRaises(Exception):
            _validate_ticket_items(
                [{"field": "designation", "value": "Manager", "proposed_json": "{}"}],
                "Other",
            )

        with self.assertRaises(Exception):
            _validate_ticket_items(
                [{"field": "contact", "proposed_json": json.dumps({"designation": "Manager"})}],
                "Contact Change",
            )

    def test_allows_work_history_designation_in_child_row(self):
        from ai_workplace.api.profile import _validate_ticket_items

        items = [{
            "field": "work_history",
            "proposed_json": json.dumps({
                "company_name": "ABC",
                "designation": "Engineer",
                "employment_period": "2020-2022",
            }),
        }]
        _validate_ticket_items(items, "Work History")


class TestProfileNotifications(unittest.TestCase):
    def test_approved_message(self):
        from ai_workplace.services.profile_notifications import _build_message

        doc = MagicMock()
        doc.status = "Approved"
        doc.name = "EPCR-2026-00001"
        doc.request_type = "Education"
        msg = _build_message(doc, "Approved", "", "")
        self.assertIn("Approved", msg)
        self.assertIn("EPCR-2026-00001", msg)

    def test_rejected_message(self):
        from ai_workplace.services.profile_notifications import _build_message

        doc = MagicMock()
        doc.status = "Rejected"
        doc.name = "EPCR-2026-00002"
        doc.request_type = "Work History"
        doc.rejection_reason = "Incomplete documents"
        doc.hr_remarks = ""
        msg = _build_message(doc, "Rejected", "Incomplete documents", "")
        self.assertIn("Rejected", msg)


if __name__ == "__main__":
    unittest.main()
