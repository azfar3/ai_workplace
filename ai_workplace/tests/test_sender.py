"""
ai_workplace/tests/test_sender.py
────────────────────────────────────
Unit tests for the WhatsApp sender.
All Meta API calls are mocked — no real HTTP requests.
"""

import unittest
from unittest.mock import patch, MagicMock
import requests

from ai_workplace.whatsapp.sender import (
    _build_http_session,
    send_interactive_message,
    send_text_message,
)


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


def _mock_session(post_return=None, post_side_effect=None):
    """Helper to build a mock requests.Session context manager."""
    mock_sess = MagicMock()
    mock_sess.__enter__.return_value = mock_sess
    mock_sess.__exit__.return_value = None
    if post_side_effect:
        mock_sess.post.side_effect = post_side_effect
    elif post_return:
        mock_sess.post.return_value = post_return
    return mock_sess


class TestWhatsAppSender(unittest.TestCase):

    def test_session_trust_env_disabled(self):
        """1. Verify HTTP Session is configured with trust_env = False."""
        session = _build_http_session()
        self.assertIsInstance(session, requests.Session)
        self.assertFalse(session.trust_env)

    def test_successful_send(self):
        """2. Test successful text message send."""
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "messages": [{"id": "wamid.sent123"}]
        }
        mock_response.raise_for_status.return_value = None
        mock_sess = _mock_session(post_return=mock_response)

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "wamid.sent123")
        self.assertIsNone(result["error"])

    def test_meta_http_error(self):
        """3. Test Meta HTTP error (401/400)."""
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "Invalid OAuth access token"}}
        http_err = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_err

        mock_sess = _mock_session(post_return=mock_response)
        mock_logger = _mock_frappe_logger()

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("401", result["error"])

    def test_timeout(self):
        """4. Test request timeout exception."""
        settings = _mock_settings()
        mock_sess = _mock_session(post_side_effect=requests.exceptions.Timeout())
        mock_logger = _mock_frappe_logger()

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("timed out", result["error"].lower())

    def test_connection_error(self):
        """5. Test connection error exception."""
        settings = _mock_settings()
        mock_sess = _mock_session(post_side_effect=requests.exceptions.ConnectionError("no route"))
        mock_logger = _mock_frappe_logger()

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess), \
             patch("frappe.logger", return_value=mock_logger):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("connection error", result["error"].lower())

    def test_generic_unexpected_exception(self):
        """6. Test generic unexpected exception (e.g. RecursionError) logs traceback and returns error dict."""
        settings = _mock_settings()
        mock_sess = _mock_session(post_side_effect=RecursionError("maximum recursion depth exceeded while calling a Python object"))
        mock_logger = _mock_frappe_logger()
        mock_log_error = MagicMock()

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess), \
             patch("frappe.logger", return_value=mock_logger), \
             patch("frappe.log_error", mock_log_error), \
             patch("frappe.get_traceback", return_value="Traceback details..."):
            result = send_text_message("+923001234567", "Hello!", settings=settings)

        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("maximum recursion depth exceeded", result["error"])
        mock_log_error.assert_called_once()
        self.assertEqual(mock_log_error.call_args[1]["title"], "WhatsApp Meta API Full Traceback")

    def test_strips_leading_plus(self):
        """7. Meta API receives recipient phone number without leading +."""
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}
        mock_response.raise_for_status.return_value = None

        captured = {}

        def mock_post(url, json=None, headers=None, timeout=None, **kwargs):
            captured["to"] = json["to"]
            return mock_response

        mock_sess = _mock_session(post_side_effect=mock_post)

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess):
            result = send_text_message("+923001234567", "Hi", settings=settings)

        self.assertTrue(result["success"])
        self.assertEqual(captured["to"], "923001234567")

    def test_no_proxies_argument_passed(self):
        """8. Verify that request does NOT pass a proxies argument to session.post."""
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc"}]}
        mock_response.raise_for_status.return_value = None

        mock_sess = _mock_session(post_return=mock_response)

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess):
            send_text_message("+923001234567", "Hi", settings=settings)

        mock_sess.post.assert_called_once()
        call_kwargs = mock_sess.post.call_args.kwargs
        self.assertNotIn("proxies", call_kwargs)

    def test_disabled_settings(self):
        """9. Test disabled settings."""
        settings = _mock_settings(enabled=False)
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("disabled", result["error"].lower())

    def test_missing_access_token(self):
        """10. Test missing access token."""
        settings = _mock_settings(access_token="")
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("access token", result["error"].lower())

    def test_missing_phone_number_id(self):
        """11. Test missing phone number ID."""
        settings = _mock_settings(phone_number_id="")
        result = send_text_message("+923001234567", "Hello!", settings=settings)
        self.assertFalse(result["success"])
        self.assertIsNone(result["message_id"])
        self.assertIn("phone number id", result["error"].lower())

    def test_send_interactive_list(self):
        """12. Test interactive message send."""
        settings = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"messages": [{"id": "wamid.interactive1"}]}
        mock_response.raise_for_status.return_value = None
        captured = {}

        def mock_post(url, json=None, headers=None, timeout=None, **kwargs):
            captured["type"] = json["type"]
            captured["interactive_type"] = json["interactive"]["type"]
            return mock_response

        mock_sess = _mock_session(post_side_effect=mock_post)

        interactive = {
            "type": "list",
            "body": {"text": "Choose"},
            "action": {"button": "Services", "sections": [{"title": "S", "rows": []}]},
        }

        with patch("ai_workplace.whatsapp.sender._build_http_session", return_value=mock_sess):
            result = send_interactive_message("+923001234567", "Choose", interactive, settings=settings)

        self.assertTrue(result["success"])
        self.assertEqual(captured["type"], "interactive")
        self.assertEqual(captured["interactive_type"], "list")
