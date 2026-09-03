"""
Unit tests for Support PIN validation and authorization.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_workplace.security.support_pin import validate_pin_format, hash_pin, verify_pin_hash
from ai_workplace.security.authorization import (
    get_service_security_policy,
    requires_pin,
    POLICY_NONE,
    POLICY_PIN_REQUIRED,
)
from ai_workplace.security.menu_security import menu_security_label_to_policy
from ai_workplace.security.credential_redaction import (
    is_pin_shaped_text,
    redact_message_for_log,
    REDACTED_PLACEHOLDER,
)


class TestSupportPinValidation(unittest.TestCase):
    def test_valid_pin(self):
        ok, err = validate_pin_format("4827")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_rejects_weak_pin(self):
        ok, err = validate_pin_format("1234")
        self.assertFalse(ok)

    def test_rejects_non_numeric(self):
        ok, err = validate_pin_format("12ab")
        self.assertFalse(ok)

    def test_hash_and_verify(self):
        hashed = hash_pin("4827")
        self.assertTrue(verify_pin_hash("4827", hashed))
        self.assertFalse(verify_pin_hash("0001", hashed))


class TestServiceSecurityPolicy(unittest.TestCase):
    def test_payroll_requires_pin(self):
        self.assertEqual(get_service_security_policy("pay_download_slip"), POLICY_PIN_REQUIRED)

    def test_contact_hr_no_pin(self):
        self.assertEqual(get_service_security_policy("contact_hr"), POLICY_NONE)

    def test_requires_pin_helper(self):
        self.assertTrue(requires_pin("my_profile"))
        self.assertFalse(requires_pin("att_today"))

    @patch("ai_workplace.security.authorization.get_menu_item_security_policy")
    def test_menu_catalog_overrides_default(self, mock_menu_policy):
        mock_menu_policy.return_value = POLICY_NONE
        self.assertEqual(get_service_security_policy("pay_download_slip"), POLICY_NONE)

    @patch("ai_workplace.security.authorization.get_menu_item_security_policy")
    def test_menu_catalog_pin_required(self, mock_menu_policy):
        mock_menu_policy.return_value = POLICY_PIN_REQUIRED
        self.assertTrue(requires_pin("att_today"))


class TestMenuSecurityLabels(unittest.TestCase):
    def test_label_mapping(self):
        self.assertEqual(menu_security_label_to_policy("None"), POLICY_NONE)
        self.assertEqual(menu_security_label_to_policy("PIN Required"), POLICY_PIN_REQUIRED)
        self.assertEqual(menu_security_label_to_policy("PIN + Approval"), "pin_plus_approval")


class TestCredentialRedaction(unittest.TestCase):
    def test_pin_shaped_text(self):
        self.assertTrue(is_pin_shaped_text("4827"))
        self.assertFalse(is_pin_shaped_text("hello"))

    def test_redact(self):
        self.assertEqual(redact_message_for_log("4827", force=True), REDACTED_PLACEHOLDER)


class TestPinSetupButtons(unittest.TestCase):
    def test_normalize_button_ids(self):
        from ai_workplace.security.pin_flow import _normalize_pin_button_id

        self.assertEqual(_normalize_pin_button_id("svc_open_hrmis"), "open_hrmis")
        self.assertEqual(_normalize_pin_button_id("svc_pin_set_done"), "pin_set_done")
        self.assertEqual(_normalize_pin_button_id("Open HRMIS Portal"), "open_hrmis")
        self.assertEqual(_normalize_pin_button_id("I Have Set My PIN"), "pin_set_done")


class TestEmployeeSupportPinField(unittest.TestCase):
    @patch("ai_workplace.security.support_pin.frappe")
    def test_configured_when_custom_field_set(self, mock_frappe):
        from ai_workplace.security.support_pin import employee_support_pin_is_set

        mock_frappe.db.has_column.return_value = True
        mock_frappe.db.get_value.return_value = "4827"
        self.assertTrue(employee_support_pin_is_set("EMP-001"))

    @patch("ai_workplace.security.support_pin.frappe")
    def test_not_configured_when_empty(self, mock_frappe):
        from ai_workplace.security.support_pin import employee_support_pin_is_set

        mock_frappe.db.has_column.return_value = True
        mock_frappe.db.get_value.return_value = ""
        mock_frappe.db.exists.return_value = False
        self.assertFalse(employee_support_pin_is_set("EMP-001"))

    @patch("ai_workplace.security.support_pin.frappe")
    def test_verify_employee_support_pin_data_field(self, mock_frappe):
        from ai_workplace.security.support_pin import verify_employee_support_pin

        mock_frappe.db.has_column.return_value = True
        mock_frappe.db.get_value.return_value = "4827"
        self.assertTrue(verify_employee_support_pin("EMP-001", "4827"))
        self.assertFalse(verify_employee_support_pin("EMP-001", "9999"))

    @patch("ai_workplace.security.support_pin.frappe")
    def test_save_employee_support_pin_data_field(self, mock_frappe):
        from ai_workplace.security.support_pin import _save_employee_support_pin

        mock_frappe.db.has_column.return_value = True
        _save_employee_support_pin("EMP-001", "4827")
        mock_frappe.db.set_value.assert_called_with("Employee", "EMP-001", "custom_support_pin", "4827", update_modified=False)



if __name__ == "__main__":
    unittest.main()
