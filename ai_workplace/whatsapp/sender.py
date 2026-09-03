"""
ai_workplace/whatsapp/sender.py
────────────────────────────────
WhatsApp Cloud API message sender.

Supports plain text and interactive (list / button) messages.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Union

import frappe
import requests

from ai_workplace.whatsapp.outbound import OutboundMessage

_DEFAULT_GRAPH_API_VERSION = "v18.0"
_SEND_TIMEOUT_SECONDS = 30


def send_text_message(
    phone_number: str,
    message: str,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a plain-text WhatsApp message via the Meta Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }
    return _post_message(phone_number, payload, settings)


def send_interactive_message(
    phone_number: str,
    body_text: str,
    interactive: dict[str, Any],
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a WhatsApp interactive message (list or button)."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "interactive",
        "interactive": interactive,
    }
    return _post_message(phone_number, payload, settings)


def upload_media_file(
    file_path: str,
    mime_type: str,
    settings: Optional[Any] = None,
    filename: str = "",
) -> dict[str, Any]:
    """Upload a local file to Meta and return the media id."""
    upload_name = filename or os.path.basename(file_path)
    with open(file_path, "rb") as handle:
        return upload_media_bytes(handle.read(), mime_type, upload_name, settings=settings)


def upload_media_bytes(
    content: bytes,
    mime_type: str,
    filename: str,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Upload in-memory bytes to Meta and return the media id."""
    import os

    try:
        cfg = settings or frappe.get_single("AI Workplace Settings")
    except Exception as exc:
        return _error_result(f"Cannot load AI Workplace Settings: {exc}")

    access_token = _get_access_token(cfg)
    phone_number_id = cfg.get("whatsapp_phone_number_id") or cfg.get("meta_phone_number_id") or ""
    api_version = cfg.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION

    if not access_token:
        return _error_result("Meta Access Token is not configured")
    if not phone_number_id:
        return _error_result("Meta Phone Number ID is not configured")

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/media"
    headers = {"Authorization": f"Bearer {access_token}"}
    upload_name = filename or f"upload{mimetype_to_extension(mime_type)}"

    try:
        response = requests.post(
            url,
            headers=headers,
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (upload_name, content, mime_type)},
            timeout=_SEND_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        media_id = data.get("id")
        if not media_id:
            return _error_result(f"Meta media upload returned no id: {data}")
        return {"success": True, "media_id": media_id, "error": None}
    except Exception as exc:
        err = f"Meta media upload failed: {exc}"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)


def mimetype_to_extension(mime_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    }
    return mapping.get(mime_type, ".bin")


def send_image_message(
    phone_number: str,
    media_id: str,
    caption: str = "",
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a WhatsApp image message using a Meta media id."""
    image_payload: dict[str, Any] = {"id": media_id}
    if caption:
        image_payload["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "image",
        "image": image_payload,
    }
    return _post_message(phone_number, payload, settings)


def send_document_message(
    phone_number: str,
    media_id: str,
    filename: str,
    caption: str = "",
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a WhatsApp document message using a Meta media id."""
    doc_payload: dict[str, Any] = {"id": media_id, "filename": filename or "file"}
    if caption:
        doc_payload["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "document",
        "document": doc_payload,
    }
    return _post_message(phone_number, payload, settings)


def send_message(
    phone_number: str,
    outbound: Union[OutboundMessage, str],
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """
    Send an OutboundMessage (text or interactive) or plain string.
    Falls back to text if interactive send fails.
    """
    if isinstance(outbound, str):
        return send_text_message(phone_number, outbound, settings=settings)

    result = _send_single_message(phone_number, outbound, settings=settings)
    if not result.get("success"):
        return result

    last_result = result
    for extra in outbound.follow_up or []:
        follow_result = _send_single_message(phone_number, extra, settings=settings)
        if follow_result.get("success"):
            last_result = follow_result
        else:
            frappe.logger("ai_workplace").warning(
                f"AI Workplace: Follow-up message send failed: {follow_result.get('error')}"
            )
    return last_result


def _send_single_message(
    phone_number: str,
    outbound: OutboundMessage,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    if outbound.has_document():
        upload = upload_media_bytes(
            outbound.document_bytes or b"",
            outbound.document_mimetype or "application/octet-stream",
            outbound.document_filename or "file",
            settings=settings,
        )
        if not upload.get("success"):
            if outbound.body_text:
                return send_text_message(phone_number, outbound.body_text, settings=settings)
            return upload

        caption = outbound.document_caption or outbound.body_text or ""
        return send_document_message(
            phone_number,
            upload["media_id"],
            outbound.document_filename or "file",
            caption=caption,
            settings=settings,
        )

    if outbound.is_interactive():
        result = send_interactive_message(
            phone_number,
            outbound.body_text,
            outbound.interactive,
            settings=settings,
        )
        if not result.get("success"):
            # If interactive payload contained a header (e.g. image header), retry without header
            if outbound.interactive and "header" in outbound.interactive:
                frappe.logger("ai_workplace").warning(
                    f"AI Workplace: Interactive send failed with header ({result.get('error')}); retrying without header"
                )
                clean_interactive = dict(outbound.interactive)
                clean_interactive.pop("header", None)
                retry_res = send_interactive_message(
                    phone_number,
                    outbound.body_text,
                    clean_interactive,
                    settings=settings,
                )
                if retry_res.get("success"):
                    return retry_res

            fallback = outbound.body_text
            if fallback:
                frappe.logger("ai_workplace").warning(
                    f"AI Workplace: Interactive send failed ({result.get('error')}); falling back to text"
                )
                return send_text_message(phone_number, fallback, settings=settings)
        return result

    return send_text_message(phone_number, outbound.body_text, settings=settings)


def _post_message(
    phone_number: str,
    payload: dict[str, Any],
    settings: Optional[Any] = None,
) -> dict[str, Any]:
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
    phone_number_id = cfg.get("whatsapp_phone_number_id") or cfg.get("meta_phone_number_id") or ""
    api_version = cfg.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION

    if not access_token:
        return _error_result("Meta Access Token is not configured")

    if not phone_number_id:
        return _error_result("Meta Phone Number ID is not configured")

    url = (
        f"https://graph.facebook.com/{api_version}"
        f"/{phone_number_id}/messages"
    )

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
    for fieldname in ("whatsapp_system_user_access_token", "meta_access_token"):
        try:
            token = cfg.get_password(fieldname) or ""
        except Exception:
            token = cfg.get(fieldname) or ""
        if token:
            return token
    return ""


def _error_result(error_message: str) -> dict[str, Any]:
    return {"success": False, "message_id": None, "error": error_message}
