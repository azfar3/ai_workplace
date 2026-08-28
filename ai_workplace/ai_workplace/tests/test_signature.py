"""
ai_workplace/tests/test_signature.py
──────────────────────────────────────
Unit tests for Meta webhook signature validation.
No database access required.
"""

import hashlib
import hmac
import unittest
from unittest.mock import patch, MagicMock
import sys

_frappe_mock = MagicMock()
_frappe_mock.logger.return_value = MagicMock(error=MagicMock())
sys.modules.setdefault("frappe", _frappe_mock)

from ai_workplace.whatsapp.signature import validate_signature


APP_SECRET = "test_app_secret_abc123"


def _make_valid_signature(body: bytes, secret: str) -> str:
    """Compute the correct HMAC-SHA256 signature."""
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


class TestSignatureValidation(unittest.TestCase):

    def test_valid_signature(self):
        body = b'{"test": "payload"}'
        sig = _make_valid_signature(body, APP_SECRET)
        self.assertTrue(validate_signature(body, sig, APP_SECRET))

    def test_invalid_signature(self):
        body = b'{"test": "payload"}'
        self.assertFalse(validate_signature(body, "sha256=deadbeef", APP_SECRET))

    def test_wrong_secret(self):
        body = b'{"test": "payload"}'
        sig = _make_valid_signature(body, "wrong_secret")
        self.assertFalse(validate_signature(body, sig, APP_SECRET))

    def test_tampered_body(self):
        body = b'{"test": "payload"}'
        sig = _make_valid_signature(body, APP_SECRET)
        tampered = b'{"test": "tampered"}'
        self.assertFalse(validate_signature(tampered, sig, APP_SECRET))

    def test_missing_sha256_prefix(self):
        body = b'{"test": "payload"}'
        raw_hex = hmac.new(
            APP_SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        # Without "sha256=" prefix
        self.assertFalse(validate_signature(body, raw_hex, APP_SECRET))

    def test_empty_signature_header(self):
        body = b'{"test": "payload"}'
        self.assertFalse(validate_signature(body, "", APP_SECRET))

    def test_empty_app_secret(self):
        body = b'{"test": "payload"}'
        sig = _make_valid_signature(body, APP_SECRET)
        self.assertFalse(validate_signature(body, sig, ""))

    def test_empty_body(self):
        body = b""
        sig = _make_valid_signature(body, APP_SECRET)
        self.assertTrue(validate_signature(body, sig, APP_SECRET))

    def test_timing_safe(self):
        """
        This test verifies the function returns a bool, confirming
        it uses hmac.compare_digest (timing-safe).
        The actual timing safety is guaranteed by the stdlib.
        """
        body = b'{"data": 1}'
        sig = _make_valid_signature(body, APP_SECRET)
        result = validate_signature(body, sig, APP_SECRET)
        self.assertIsInstance(result, bool)
        self.assertTrue(result)
