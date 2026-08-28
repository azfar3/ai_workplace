"""
ai_workplace/tests/test_payload_parser.py
──────────────────────────────────────────
Unit tests for the WhatsApp webhook payload parser.
No database access required; no Meta API calls.
"""

import unittest
from unittest.mock import patch, MagicMock

# Patch frappe.logger before importing the module
import sys

# Create a minimal frappe mock
_frappe_mock = MagicMock()
_frappe_mock.logger.return_value = MagicMock(warning=MagicMock(), error=MagicMock(), info=MagicMock())
sys.modules.setdefault("frappe", _frappe_mock)

from ai_workplace.whatsapp.payload_parser import (
    parse_webhook_payload,
    ParseError,
)


def _make_payload(
    message_type: str = "text",
    message_text: str = "Hello",
    wa_id: str = "923001234567",
    message_id: str = "wamid.test123",
    timestamp: str = "1700000000",
):
    """Helper to build a minimal valid Meta payload."""
    msg = {
        "from": wa_id,
        "id": message_id,
        "timestamp": timestamp,
        "type": message_type,
    }
    if message_type == "text":
        msg["text"] = {"body": message_text}

    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+923001234567",
                                "phone_number_id": "phone-id-123",
                            },
                            "contacts": [{"wa_id": wa_id}],
                            "messages": [msg],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


class TestPayloadParser(unittest.TestCase):

    # ── Text message ──────────────────────────────────────────────────────────

    def test_parse_text_message(self):
        payload = _make_payload(message_type="text", message_text="Hello!")
        result = parse_webhook_payload(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["message_type"], "text")
        self.assertEqual(result["text"], "Hello!")
        self.assertEqual(result["message_id"], "wamid.test123")
        self.assertEqual(result["wa_id"], "923001234567")

    # ── Unsupported message types ─────────────────────────────────────────────

    def test_parse_image_message_returns_unsupported(self):
        payload = _make_payload(message_type="image")
        result = parse_webhook_payload(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["message_type"], "unsupported")
        self.assertEqual(result["raw_type"], "image")

    def test_parse_audio_message_returns_unsupported(self):
        payload = _make_payload(message_type="audio")
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "unsupported")

    def test_parse_video_message_returns_unsupported(self):
        payload = _make_payload(message_type="video")
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "unsupported")

    def test_parse_document_message_returns_unsupported(self):
        payload = _make_payload(message_type="document")
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "unsupported")

    # ── Status updates ────────────────────────────────────────────────────────

    def test_parse_status_update(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "entry-id",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "pid"},
                                "statuses": [
                                    {
                                        "id": "wamid.abc",
                                        "recipient_id": "923001234567",
                                        "status": "delivered",
                                        "timestamp": "1700000001",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        result = parse_webhook_payload(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["message_type"], "status")

    # ── Empty / heartbeat payload ─────────────────────────────────────────────

    def test_empty_entry_returns_none(self):
        payload = {"object": "whatsapp_business_account", "entry": []}
        result = parse_webhook_payload(payload)
        self.assertIsNone(result)

    def test_no_messages_no_statuses_returns_none(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "eid",
                    "changes": [
                        {
                            "value": {"metadata": {}},
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        result = parse_webhook_payload(payload)
        self.assertIsNone(result)

    # ── Parse errors ──────────────────────────────────────────────────────────

    def test_non_dict_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_webhook_payload("not a dict")

    def test_none_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_webhook_payload(None)
