"""
ai_workplace/whatsapp/sender.py
────────────────────────────────
WhatsApp Cloud API message sender.

Encapsulates all HTTP communication with the Meta Graph API.
Credentials are always read from AI Workplace Settings.

Public API:
  send_text_message(phone_number: str, message: str) -> dict

The function returns a dict with:
  {
      "success":    bool,
      "message_id": str | None,  # Meta's wamid of the sent message
      "error":      str | None,
  }

Phase 1: text messages only.
Future phases can add templates, media, interactive messages etc.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe
import requests

# Fallback API version if not configured.
_DEFAULT_GRAPH_API_VERSION = "v18.0"
_SEND_TIMEOUT_SECONDS = 30


def send_text_message(
    phone_number: str,
    message: str,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Send a plain-text WhatsApp message via the Meta Cloud API.

    Parameters
    ----------
    phone_number : str
        Recipient phone number in E.164 format (e.g. +923001234567).
        Meta accepts the number with or without the leading +.
    message : str
        Text body to send.
    settings : optional
        Pre-fetched AI Workplace Settings document (for testing / performance).
        If None, fetched internally.

    Returns
    -------
    dict
        {"success": bool, "message_id": str|None, "error": str|None}
    """
    try:
        cfg = settings or frappe.get_single("AI Workplace Settings")
    except Exception as exc:
        return _error_result(f"Cannot load AI Workplace Settings: {exc}")

    enabled = cfg.get("enabled")
    if enabled is None:
        enabled = True
    if not enabled:
        return _error_result("AI Workplace is disabled in Settings")

    access_token = _get_access_token(cfg)
    phone_number_id = cfg.get("meta_phone_number_id") or ""
    api_version = cfg.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION

    if not access_token:
        return _error_result("Meta Access Token is not configured")

    if not phone_number_id:
        return _error_result("Meta Phone Number ID is not configured")

    # Strip leading + for Meta's API (it accepts either format but is most
    # consistent without it).
    recipient = phone_number.lstrip("+")

    url = (
        f"https://graph.facebook.com/{api_version}"
        f"/{phone_number_id}/messages"
    )

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=_SEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        message_id = None
        messages = data.get("messages", [])
        if messages:
            message_id = messages[0].get("id")

        return {"success": True, "message_id": message_id, "error": None}

    except requests.exceptions.Timeout:
        err = f"Meta API request timed out after {_SEND_TIMEOUT_SECONDS}s"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)

    except requests.exceptions.ConnectionError as exc:
        err = f"Meta API connection error: {exc}"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)

    except requests.exceptions.HTTPError as exc:
        body = ""
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text
        err = f"Meta API HTTP error {exc.response.status_code}: {body}"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)

    except Exception as exc:
        err = f"Unexpected error sending WhatsApp message: {exc}"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)


def _get_access_token(cfg: Any) -> str:
    """Read and return the Meta access token from settings."""
    try:
        return cfg.get_password("meta_access_token") or ""
    except Exception:
        return cfg.get("meta_access_token") or ""


def _error_result(error_message: str) -> dict[str, Any]:
    return {"success": False, "message_id": None, "error": error_message}
