"""
ai_workplace/tests/test_hr_profile.py
───────────────────────────────────────
Unit tests for HR Profile, Masking & Reporting handlers.
"""

import unittest
from ai_workplace.services.hr_profile import (
    mask_cnic,
    mask_bank_account,
    build_my_profile_response,
    build_supervisor_reporting_response,
)


class TestHRProfile(unittest.TestCase):

    def test_mask_cnic_standard(self):
        self.assertEqual(mask_cnic("61101-1234567-1"), "61101-XXXXX67-1")
        self.assertEqual(mask_cnic("35202-9876543-9"), "35202-XXXXX43-9")

    def test_mask_cnic_unhyphenated(self):
        self.assertEqual(mask_cnic("6110112345671"), "61101-XXXXX67-1")

    def test_mask_cnic_edge_cases(self):
        self.assertEqual(mask_cnic(None), "N/A")
        self.assertEqual(mask_cnic(""), "N/A")

    def test_mask_bank_account_standard(self):
        self.assertEqual(mask_bank_account("01010102938475"), "XXXX-XXXX-8475")
        self.assertEqual(mask_bank_account("PK36 MEZN 0001 0203 0405 06"), "XXXX-XXXX-0506")

    def test_mask_bank_account_edge_cases(self):
        self.assertEqual(mask_bank_account(None), "N/A")
        self.assertEqual(mask_bank_account(""), "N/A")
        self.assertEqual(mask_bank_account("123"), "XXXX")

    def test_profile_response_fallback(self):
        ctx_en = {"employee": "NON_EXISTENT_EMP", "preferred_language": "English"}
        res = build_my_profile_response(ctx_en)
        self.assertIn("record could not be found", res)

    def test_supervisor_reporting_fallback(self):
        ctx_en = {"employee": "NON_EXISTENT_EMP", "preferred_language": "English"}
        res = build_supervisor_reporting_response(ctx_en)
        self.assertIn("No direct supervisor is currently assigned", res)
