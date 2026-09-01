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


# Message types supported for inbound processing.
SUPPORTED_TYPES = {"text", "interactive"}
MEDIA_TYPES = {"image", "document", "video", "audio", "sticker"}
LOCATION_TYPES = {"location"}

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

    # Filter out SMB Message Echoes sent from WhatsApp Business app in Coexistence mode
    metadata = value.get("metadata", {})
    display_phone = metadata.get("display_phone_number", "")
    if msg.get("from") == display_phone or msg.get("is_echo"):
        frappe.logger("ai_workplace").info(
            f"AI Workplace: Ignored WhatsApp Business app message echo for message {msg.get('id')}."
        )
        return None

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

    # Extract text / interactive / media / location content.
    text = ""
    media_id = ""
    media_filename = ""
    media_mime_type = ""
    latitude = None
    longitude = None
    location_name = ""
    location_address = ""
    context_message_id = ""
    if raw_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif raw_type == "interactive":
        text = _extract_interactive_input(msg.get("interactive", {}))
    elif raw_type in MEDIA_TYPES:
        media_block = msg.get(raw_type) or {}
        media_id = media_block.get("id") or ""
        media_filename = media_block.get("filename") or ""
        media_mime_type = media_block.get("mime_type") or ""
        text = media_block.get("caption") or ""
    elif raw_type == "location":
        loc = msg.get("location") or {}
        latitude = loc.get("latitude")
        longitude = loc.get("longitude")
        location_name = loc.get("name") or ""
        location_address = loc.get("address") or ""
        text = location_name or location_address or "location"

    ctx = msg.get("context") or {}
    context_message_id = ctx.get("id") or ""

    # Determine internal message_type.
    if raw_type in SUPPORTED_TYPES:
        message_type = raw_type
    elif raw_type in MEDIA_TYPES:
        message_type = raw_type
    elif raw_type in LOCATION_TYPES:
        message_type = "location"
    else:
        message_type = "unsupported"
        frappe.logger("ai_workplace").warning(
            f"AI Workplace: Unsupported WhatsApp message type '{raw_type}' "
            f"for message {message_id}.  Acknowledging without processing."
        )

    result = {
        "message_id": message_id,
        "wa_id": wa_id,
        "phone_number": phone_number,
        "message_type": message_type,
        "text": text,
        "timestamp": timestamp,
        "business_phone_number_id": business_phone_number_id,
        "raw_type": raw_type,
        "media_id": media_id,
        "media_filename": media_filename,
        "media_mime_type": media_mime_type,
        "latitude": latitude,
        "longitude": longitude,
        "location_name": location_name,
        "location_address": location_address,
        "context_message_id": context_message_id,
    }
    return result


def _extract_interactive_input(interactive: dict[str, Any]) -> str:
    """
    Normalize interactive button/list replies to internal selection ids.
    Returns e.g. lang_en, svc_hr, or the visible title as fallback.
    """
    itype = interactive.get("type", "")
    if itype == "button_reply":
        reply = interactive.get("button_reply") or {}
        return reply.get("id") or reply.get("title") or ""
    if itype == "list_reply":
        reply = interactive.get("list_reply") or {}
        return reply.get("id") or reply.get("title") or ""
    return ""


def _parse_status(status: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a delivery/read status update.  These are not inbound messages;
    we return them with message_type = "status" so the controller can
    acknowledge and skip.
    """
    metadata = value.get("metadata", {})
    meta_status = (status.get("status") or "").strip().lower()
    return {
        "message_id": status.get("id", ""),
        "wa_id": status.get("recipient_id", ""),
        "phone_number": status.get("recipient_id", ""),
        "message_type": "status",
        "text": "",
        "timestamp": status.get("timestamp", ""),
        "business_phone_number_id": metadata.get("phone_number_id", ""),
        "raw_type": "status",
        "delivery_status": meta_status,
    }
