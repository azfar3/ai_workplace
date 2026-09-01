"""
ai_workplace/tests/test_payload_parser.py
──────────────────────────────────────────
Unit tests for the WhatsApp webhook payload parser.
No database access required; no Meta API calls.
"""

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.whatsapp.payload_parser import (
    parse_webhook_payload,
    ParseError,
)


def _mock_logger():
    mock_log = MagicMock()
    mock_log.warning = MagicMock()
    mock_log.error = MagicMock()
    mock_log.info = MagicMock()
    return mock_log


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

    def test_parse_image_message(self):
        payload = _make_payload(message_type="image")
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["image"] = {
            "id": "media-123",
            "mime_type": "image/jpeg",
            "caption": "Team photo",
        }
        result = parse_webhook_payload(payload)
        self.assertIsNotNone(result)
        self.assertEqual(result["message_type"], "image")
        self.assertEqual(result["media_id"], "media-123")
        self.assertEqual(result["text"], "Team photo")

    def test_parse_image_message_legacy_unsupported_type(self):
        payload = _make_payload(message_type="image")
        with patch("frappe.logger", return_value=_mock_logger()):
            result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "image")
        self.assertEqual(result["raw_type"], "image")

    def test_parse_audio_message(self):
        payload = _make_payload(message_type="audio")
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "audio")

    def test_parse_video_message(self):
        payload = _make_payload(message_type="video")
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "video")

    def test_parse_document_message(self):
        payload = _make_payload(message_type="document")
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["document"] = {
            "id": "doc-123",
            "filename": "report.pdf",
            "mime_type": "application/pdf",
        }
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "document")
        self.assertEqual(result["media_id"], "doc-123")
        self.assertEqual(result["media_filename"], "report.pdf")

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
        self.assertEqual(result["message_id"], "wamid.abc")
        self.assertEqual(result["delivery_status"], "delivered")

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

    # ── Interactive replies ───────────────────────────────────────────────────

    def test_parse_button_reply(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "eid",
                "changes": [{
                    "value": {
                        "metadata": {"phone_number_id": "pid"},
                        "contacts": [{"wa_id": "923001234567"}],
                        "messages": [{
                            "from": "923001234567",
                            "id": "wamid.btn1",
                            "timestamp": "1700000000",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {"id": "lang_en", "title": "English"},
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "interactive")
        self.assertEqual(result["text"], "lang_en")

    def test_parse_list_reply(self):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "eid",
                "changes": [{
                    "value": {
                        "metadata": {"phone_number_id": "pid"},
                        "contacts": [{"wa_id": "923001234567"}],
                        "messages": [{
                            "from": "923001234567",
                            "id": "wamid.list1",
                            "timestamp": "1700000000",
                            "type": "interactive",
                            "interactive": {
                                "type": "list_reply",
                                "list_reply": {"id": "svc_hr", "title": "My HR"},
                            },
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        result = parse_webhook_payload(payload)
        self.assertEqual(result["message_type"], "interactive")
        self.assertEqual(result["text"], "svc_hr")

    # ── Parse errors ──────────────────────────────────────────────────────────

    def test_non_dict_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_webhook_payload("not a dict")

    def test_none_raises_parse_error(self):
        with self.assertRaises(ParseError):
            parse_webhook_payload(None)
