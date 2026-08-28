"""
ai_workplace/tests/test_phone.py
──────────────────────────────────
Unit tests for phone normalization.
No database access required.
"""

import unittest

from ai_workplace.identity.phone import (
    normalize_phone_number,
    normalize_phone_number_safe,
    phones_match,
    PhoneNormalizationError,
)


class TestPhoneNormalization(unittest.TestCase):
    """Test E.164 normalization for Pakistani and international numbers."""

    # ── Valid Pakistani numbers ───────────────────────────────────────────────

    def test_local_zero_prefix(self):
        """03001234567 → +923001234567"""
        self.assertEqual(normalize_phone_number("03001234567"), "+923001234567")

    def test_country_code_no_plus(self):
        """923001234567 → +923001234567"""
        self.assertEqual(normalize_phone_number("923001234567"), "+923001234567")

    def test_e164_already(self):
        """+923001234567 → +923001234567 (idempotent)"""
        self.assertEqual(normalize_phone_number("+923001234567"), "+923001234567")

    def test_space_separated(self):
        """0300 1234567 → +923001234567"""
        self.assertEqual(normalize_phone_number("0300 1234567"), "+923001234567")

    def test_hyphen_separated(self):
        """0300-1234567 → +923001234567"""
        self.assertEqual(normalize_phone_number("0300-1234567"), "+923001234567")

    def test_mixed_separators(self):
        """0300 123-4567 → +923001234567"""
        self.assertEqual(normalize_phone_number("0300 123-4567"), "+923001234567")

    # ── International numbers ─────────────────────────────────────────────────

    def test_uk_number(self):
        """+447911123456 → +447911123456"""
        self.assertEqual(normalize_phone_number("+447911123456"), "+447911123456")

    def test_us_number(self):
        """+12125551234 → +12125551234"""
        self.assertEqual(normalize_phone_number("+12125551234"), "+12125551234")

    # ── Invalid inputs ────────────────────────────────────────────────────────

    def test_empty_string(self):
        with self.assertRaises(PhoneNormalizationError):
            normalize_phone_number("")

    def test_short_number(self):
        with self.assertRaises(PhoneNormalizationError):
            normalize_phone_number("123")

    def test_letters(self):
        with self.assertRaises(PhoneNormalizationError):
            normalize_phone_number("abcdefgh")

    # ── Safe variant ─────────────────────────────────────────────────────────

    def test_safe_returns_none_on_error(self):
        self.assertIsNone(normalize_phone_number_safe(""))
        self.assertIsNone(normalize_phone_number_safe("abc"))

    def test_safe_returns_e164_on_success(self):
        self.assertEqual(
            normalize_phone_number_safe("03001234567"), "+923001234567"
        )

    # ── phones_match ─────────────────────────────────────────────────────────

    def test_phones_match_true(self):
        self.assertTrue(phones_match("03001234567", "+923001234567"))
        self.assertTrue(phones_match("923001234567", "0300 1234567"))

    def test_phones_match_false(self):
        self.assertFalse(phones_match("03001234567", "+923009999999"))

    def test_phones_match_none(self):
        self.assertFalse(phones_match(None, "+923001234567"))
        self.assertFalse(phones_match("", ""))
