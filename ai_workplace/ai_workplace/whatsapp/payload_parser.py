"""
ai_workplace/whatsapp/payload_parser.py
────────────────────────────────────────
Parses raw Meta WhatsApp Cloud API webhook payloads into a normalized internal
structure.  The rest of the application works only with this internal format,
never with raw Meta JSON.

Internal message schema:
  {
      "message_id":    str,   # Meta's wamid
      "wa_id":         str,   # sender's WhatsApp ID (phone digits, no +)
      "phone_number":  str,   # sender's display phone number
      "message_type":  str,   # "text" | "image" | "audio" | ... | "status" | "unknown"
      "text":          str,   # message text (only if message_type == "text")
      "timestamp":     str,   # Unix timestamp string from Meta
      "business_phone_number_id": str,  # the receiving WABA phone ID
      "raw_type":      str,   # original type string from Meta (for logging)
  }

Supported message types in Phase 1:
  text

Unsupported types are safely logged and returned with message_type = "unsupported".
Status updates (e.g. delivered, read) are returned with message_type = "status".
"""

from __future__ import annotations

from typing import Any, Optional

import frappe


# Message types supported in Phase 1.
SUPPORTED_TYPES = {"text"}

# Types that Meta sends as status updates rather than inbound messages.
STATUS_TYPES = {"status"}


class ParseError(Exception):
    """Raised when the webhook payload cannot be understood at all."""


def parse_webhook_payload(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Parse a Meta WhatsApp Cloud API webhook payload.

    Returns a normalized internal message dict, or None if the payload
    contains no actionable inbound message (e.g. pure delivery status update
    with no wamid, or a payload that carries no message entries).

    Raises :exc:`ParseError` if the payload structure is fundamentally broken.
    """
    if not isinstance(payload, dict):
        raise ParseError("Payload must be a dict")

    # Meta wraps events under entry[].changes[].value
    entries = payload.get("entry", [])
    if not entries:
        # Heartbeat or subscription confirmation — safe to ignore.
        return None

    for entry in entries:
        for change in entry.get("changes", []):
            value = change.get("value", {})
            result = _parse_value(value)
            if result is not None:
                return result

    # No actionable message found.
    return None


def _parse_value(value: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Extract the message from a single `value` block.
    """
    messages = value.get("messages", [])
    if not messages:
        # Might be a status-only update.
        statuses = value.get("statuses", [])
        if statuses:
            return _parse_status(statuses[0], value)
        return None

    msg = messages[0]  # Process one message per webhook event.
    return _parse_message(msg, value)


def _parse_message(msg: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a single message object.
    """
    raw_type = msg.get("type", "unknown")
    wa_id = msg.get("from", "")
    message_id = msg.get("id", "")
    timestamp = msg.get("timestamp", "")

    # Resolve display phone number from metadata.
    metadata = value.get("metadata", {})
    business_phone_number_id = metadata.get("phone_number_id", "")

    # Resolve contact display phone (may differ from wa_id in edge cases).
    contacts = value.get("contacts", [])
    phone_number = wa_id
    if contacts:
        phone_number = contacts[0].get("wa_id", wa_id)

    # Extract text content.
    text = ""
    if raw_type == "text":
        text = msg.get("text", {}).get("body", "")

    # Determine internal message_type.
    if raw_type in SUPPORTED_TYPES:
        message_type = raw_type
    else:
        message_type = "unsupported"
        frappe.logger("ai_workplace").warning(
            f"AI Workplace: Unsupported WhatsApp message type '{raw_type}' "
            f"for message {message_id}.  Acknowledging without processing."
        )

    return {
        "message_id": message_id,
        "wa_id": wa_id,
        "phone_number": phone_number,
        "message_type": message_type,
        "text": text,
        "timestamp": timestamp,
        "business_phone_number_id": business_phone_number_id,
        "raw_type": raw_type,
    }


def _parse_status(status: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a delivery/read status update.  These are not inbound messages;
    we return them with message_type = "status" so the controller can
    acknowledge and skip.
    """
    metadata = value.get("metadata", {})
    return {
        "message_id": status.get("id", ""),
        "wa_id": status.get("recipient_id", ""),
        "phone_number": status.get("recipient_id", ""),
        "message_type": "status",
        "text": "",
        "timestamp": status.get("timestamp", ""),
        "business_phone_number_id": metadata.get("phone_number_id", ""),
        "raw_type": "status",
    }
