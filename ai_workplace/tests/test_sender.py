"""
ai_workplace/tests/test_sender.py
────────────────────────────────────
Unit tests for the WhatsApp sender.
All Meta API calls are mocked — no real HTTP requests.
"""

import unittest
from unittest.mock import patch, MagicMock
import requests


def _mock_settings(
    enabled=True,
    access_token="test_token",
    phone_number_id="1234567890",
    api_version="v18.0",
):
    """Build a mock settings object."""
    settings = MagicMock()
    settings.get.side_effect = lambda key, *a: {
        "enabled": enabled,
        "meta_phone_number_id": phone_number_id,
        "graph_api_version": api_version,
    }.get(key)
    settings.get_password.return_value = access_token
    return settings


def _mock_frappe_logger():
    mock_logger = MagicMock()
    mock_logger.error = MagicMock()
    mock_logger.warning = MagicMock()
    mock_logger.info = MagicMock()
    return mock_logger


class TestWhatsAppSender(unittest.TestCase):

    def test_successful_send(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid.sent123"}]
        }
        mock_response.raise_for_status.return_value = None

        with patch("requests.post", return_value=mock_response):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "wamid.sent123")
        self.assertIsNone(result["error"])

    def test_disabled_settings(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings(enabled=False)
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["error"].lower())

    def test_missing_access_token(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings(access_token="")
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("access token", result["error"].lower())

    def test_missing_phone_number_id(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings(phone_number_id="")
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("phone number id", result["error"].lower())

    def test_timeout(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings()
        mock_logger = _mock_frappe_logger()
        with patch("requests.post", side_effect=requests.exceptions.Timeout()), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("timed out", result["error"].lower())

    def test_connection_error(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings()
        mock_logger = _mock_frappe_logger()
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("no route")), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("connection error", result["error"].lower())

    def test_http_401_error(self):
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid OAuth access token"}}
        http_err = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_err
        mock_logger = _mock_frappe_logger()

        with patch("requests.post", return_value=mock_response), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIn("401", result["error"])

    def test_strips_leading_plus(self):
        """Meta API receives number without leading +."""
        from ai_workplace.whatsapp.sender import send_text_message
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}
        mock_response.raise_for_status.return_value = None

        captured = {}

        def mock_post(url, json=None, headers=None, timeout=None):
            captured["to"] = json["to"]
            return mock_response

        with patch("requests.post", side_effect=mock_post):
            send_text_message("+923001234567", "Hi", settings=settings)

        self.assertEqual(captured["to"], "923001234567")

    def test_send_interactive_list(self):
        from ai_workplace.whatsapp.sender import send_interactive_message
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.interactive1"}]}
        mock_response.raise_for_status.return_value = None
        captured = {}

        def mock_post(url, json=None, headers=None, timeout=None):
            captured["type"] = json["type"]
            captured["interactive_type"] = json["interactive"]["type"]
            return mock_response

        interactive = {
            "type": "list",
            "body": {"text": "Choose"},
            "action": {"button": "Services", "sections": [{"title": "S", "rows": []}]},
        }

        with patch("requests.post", side_effect=mock_post):
            result = send_interactive_message("+923001234567", "Choose", interactive, settings=settings)

        self.assertTrue(result["success"])
        self.assertEqual(captured["type"], "interactive")
        self.assertEqual(captured["interactive_type"], "list")
