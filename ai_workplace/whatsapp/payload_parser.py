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
MEDIA_TYPES = {"image", "document", "video", "audio", "sticker", "media"}
LOCATION_TYPES = {"location"}

# Types that Meta sends as status updates rather than inbound messages.
STATUS_TYPES = {"status"}


class ParseError(Exception):
    """Raised when the webhook payload cannot be understood at all."""


def _is_numbered_menu_reply(value: str) -> bool:
    """Return True when text is a numbered option, including common punctuation."""
    normalized = (value or "").strip().rstrip(".۔").strip()
    return bool(normalized) and normalized.isdigit()


def _should_resolve_from_menu_cache(value: str, cached_obj: dict[str, Any]) -> bool:
    """Resolve custom-adapter replies against the exact menu most recently sent."""
    if not _is_numbered_menu_reply(value):
        return True
    # Custom WhatsApp sends numbered text versions of interactive menus. The
    # active service can expose a subset of a submenu, so resolving against the
    # complete submenu would select a different item than the number shown.
    return cached_obj.get("version") == 3


def parse_webhook_payload(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Parse a Meta WhatsApp Cloud API webhook payload or Custom Baileys payload.

    Returns a normalized internal message dict, or None if the payload
    contains no actionable inbound message (e.g. pure delivery status update
    with no wamid, or a payload that carries no message entries).

    Raises :exc:`ParseError` if the payload structure is fundamentally broken.
    """
    if not isinstance(payload, dict):
        raise ParseError("Payload must be a dict")

    # Check for Custom Baileys API payload format
    if "number" in payload and "status" in payload and "message_id" in payload:
        wa_id = str(payload["number"]).replace("+", "")
        meta_status = str(payload["status"]).strip().lower()
        return {
            "message_id": payload.get("message_id", ""),
            "wa_id": wa_id,
            "phone_number": wa_id,
            "message_type": "status",
            "text": "",
            "timestamp": "",
            "business_phone_number_id": "custom_api",
            "raw_type": "status",
            "delivery_status": meta_status,
        }

    if "number" in payload and "message" in payload:
        if payload.get("fromMe") or payload.get("is_echo"):
            return None

        import uuid
        import time
        from datetime import datetime
        
        wa_id = str(payload["number"]).replace("+", "")
        message_text = str(payload["message"]).strip()

        receiver_name = str(payload.get("receiver_name") or "").strip()
        receiver = str(payload.get("receiver") or payload.get("receiver_number") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        username = str(payload.get("username") or "").strip()

        clean_receiver = "".join(filter(str.isdigit, receiver))
        if not clean_receiver and receiver_name:
            clean_receiver = "".join(filter(str.isdigit, receiver_name))

        clean_sender = "".join(filter(str.isdigit, wa_id))

        # 1. Self-echo: Sender phone matches Receiver bot phone
        if clean_receiver and len(clean_receiver) >= 7 and (clean_sender == clean_receiver or clean_sender.endswith(clean_receiver[-9:])):
            return None

        # 2. Known bot numbers cannot be treated as end-users (prevents bot-to-bot ping pong loops)
        known_bot_numbers = {"3184221489", "3111123702"}
        try:
            bot_sessions = frappe.get_all("Whatsapp Session", fields=["phone_number", "session_id", "name"])
            for bs in bot_sessions:
                b_phone = "".join(filter(str.isdigit, bs.phone_number or bs.session_id or bs.name or ""))
                if len(b_phone) >= 7:
                    known_bot_numbers.add(b_phone[-9:])
        except Exception:
            pass

        try:
            hr_phone = "".join(filter(str.isdigit, frappe.db.get_single_value("AI Workplace Settings", "hr_contact_phone") or ""))
            if len(hr_phone) >= 7:
                known_bot_numbers.add(hr_phone[-9:])
        except Exception:
            pass

        if any(clean_sender.endswith(kbn) for kbn in known_bot_numbers):
            return None

        # 3. Filter outbound bot message text echoes
        if (
            message_text.startswith("📋 *All Staff Services*")
            or message_text.startswith("📋 All Staff Services")
            or message_text.startswith("Welcome to *MicroMerger Staff Support*")
            or "_⚠️ This response was generated by AI" in message_text
            or "_⚠️ یہ جواب AI نے تیار کیا ہے" in message_text
            or "_⚠️ Yeh jawab AI ne tayar kiya hai" in message_text
        ):
            return None

        clean_phone = clean_sender or "".join(filter(str.isdigit, wa_id))
        cached_obj = (
            frappe.cache().get_value(f"custom_wa_menu_{clean_phone}")
            or frappe.cache().get_value(f"custom_wa_menu_{wa_id}")
            or frappe.cache().get_value(f"custom_wa_menu_{wa_id.split('@')[0]}")
            or (frappe.cache().get_value(f"custom_wa_menu_{clean_phone[-10:]}") if len(clean_phone) >= 10 else None)
            or (frappe.cache().get_value(f"custom_wa_menu_0{clean_phone[-10:]}") if len(clean_phone) >= 10 else None)
        )
        if cached_obj and isinstance(cached_obj, dict) and cached_obj.get("version") == 3 and _should_resolve_from_menu_cache(message_text, cached_obj):
            cached_map = cached_obj.get("map", cached_obj)
            cleaned_msg = message_text.strip()
            
            matched_id = (
                cached_map.get(message_text)
                or cached_map.get(cleaned_msg)
                or cached_map.get(cleaned_msg.lower())
                or cached_map.get(message_text.lower())
            )
            if not matched_id and "." in cleaned_msg:
                first_num = cleaned_msg.split(".")[0].strip()
                matched_id = cached_map.get(first_num)
            if not matched_id and " " in cleaned_msg:
                first_token = cleaned_msg.split()[0].strip()
                if first_token.isdigit():
                    matched_id = cached_map.get(first_token)
            
            if matched_id:
                message_text = matched_id
                if clean_phone:
                    frappe.cache().delete_value(f"custom_wa_menu_{clean_phone}")
                    if len(clean_phone) >= 10:
                        frappe.cache().delete_value(f"custom_wa_menu_{clean_phone[-10:]}")
                        frappe.cache().delete_value(f"custom_wa_menu_0{clean_phone[-10:]}")
                frappe.cache().delete_value(f"custom_wa_menu_{wa_id}")

        message_type = "text"
        if payload.get("media_base64"):
            mime = (payload.get("mime_type") or "").lower()
            if mime.startswith("image/"):
                message_type = "image"
            elif mime.startswith("video/"):
                message_type = "video"
            elif mime.startswith("audio/"):
                message_type = "audio"
            else:
                message_type = "document"

        receiver_session = (
            receiver
            or session_id
            or username
            or receiver_name
            or ""
        )

        return {
            "message_id": payload.get("message_id") or f"custom_{uuid.uuid4().hex[:16]}",
            "wa_id": wa_id,
            "phone_number": wa_id,
            "message_type": message_type,
            "text": message_text,
            "timestamp": str(int(datetime.utcnow().timestamp())),
            "business_phone_number_id": "custom_api",
            "raw_type": message_type,
            "media_id": "",
            "media_filename": payload.get("filename") or "",
            "media_mime_type": payload.get("mime_type") or "",
            "latitude": None,
            "longitude": None,
            "location_name": "",
            "location_address": "",
            "context_message_id": "",
            "sender_name": payload.get("sender_name") or "",
            "receiver_name": receiver_name,
            "receiver": receiver or clean_receiver,
            "receiver_number": receiver or clean_receiver,
            "session_id": session_id,
            "username": username,
            "session_name": receiver_session,
            "receiving_session": receiver_session,
            "bot_number": receiver or clean_receiver,
            "media_base64": payload.get("media_base64") or "",
            "mime_type": payload.get("mime_type") or "",
        }

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
        clean_phone = "".join(filter(str.isdigit, wa_id or phone_number))
        cached_obj = (
            frappe.cache().get_value(f"custom_wa_menu_{clean_phone}")
            or frappe.cache().get_value(f"custom_wa_menu_{wa_id}")
            or (frappe.cache().get_value(f"custom_wa_menu_{clean_phone[-10:]}") if len(clean_phone) >= 10 else None)
            or (frappe.cache().get_value(f"custom_wa_menu_0{clean_phone[-10:]}") if len(clean_phone) >= 10 else None)
        )
        if cached_obj and isinstance(cached_obj, dict) and cached_obj.get("version") == 3 and _should_resolve_from_menu_cache(text, cached_obj):
            cached_map = cached_obj.get("map", cached_obj)
            cleaned_msg = text.strip()
            matched_id = (
                cached_map.get(text)
                or cached_map.get(cleaned_msg)
                or cached_map.get(cleaned_msg.lower())
                or cached_map.get(text.lower())
            )
            if not matched_id and "." in cleaned_msg:
                first_num = cleaned_msg.split(".")[0].strip()
                matched_id = cached_map.get(first_num)
            if not matched_id and " " in cleaned_msg:
                first_token = cleaned_msg.split()[0].strip()
                if first_token.isdigit():
                    matched_id = cached_map.get(first_token)
            if matched_id:
                text = matched_id
                if clean_phone:
                    frappe.cache().delete_value(f"custom_wa_menu_{clean_phone}")
                    if len(clean_phone) >= 10:
                        frappe.cache().delete_value(f"custom_wa_menu_{clean_phone[-10:]}")
                        frappe.cache().delete_value(f"custom_wa_menu_0{clean_phone[-10:]}")
                frappe.cache().delete_value(f"custom_wa_menu_{wa_id}")
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
