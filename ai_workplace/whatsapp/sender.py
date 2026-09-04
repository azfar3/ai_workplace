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
import ssl

if hasattr(ssl, "_SSLContext"):
    try:
        def _fixed_verify_mode_set(self, value):
            ssl._SSLContext.verify_mode.__set__(self, value)
        if type(ssl.SSLContext.verify_mode) is property:
            ssl.SSLContext.verify_mode = property(
                ssl.SSLContext.verify_mode.fget,
                _fixed_verify_mode_set,
                ssl.SSLContext.verify_mode.fdel,
                ssl.SSLContext.verify_mode.__doc__
            )
    except Exception:
        pass

from ai_workplace.whatsapp.outbound import OutboundMessage

_DEFAULT_GRAPH_API_VERSION = "v18.0"
_SEND_TIMEOUT_SECONDS = 30


def _build_http_session() -> requests.Session:
    """
    Build a dedicated requests.Session isolated from host environment proxies.
    Setting trust_env = False prevents reading system proxy environment variables
    (e.g., HTTP_PROXY, HTTPS_PROXY) and avoids proxy recursion in requests/urllib3.
    """
    session = requests.Session()
    return session


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
    upload_name = filename or f"upload{mimetype_to_extension(mime_type)}"

    import subprocess
    import json
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        cmd = [
            "curl", "-s", "-X", "POST", url,
            "-H", f"Authorization: Bearer {access_token}",
            "-F", "messaging_product=whatsapp",
            "-F", f"type={mime_type}",
            "-F", f"file=@{temp_path};filename={upload_name};type={mime_type}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SEND_TIMEOUT_SECONDS)
        try:
            os.remove(temp_path)
        except Exception:
            pass
            
        if result.returncode != 0:
            return _error_result(f"Curl failed with return code {result.returncode}: {result.stderr}")
            
        try:
            data = json.loads(result.stdout)
        except Exception as e:
            return _error_result(f"Invalid JSON response from Meta: {result.stdout}")

        if "error" in data:
            return _error_result(f"Meta API upload error: {data['error']}")
            
        media_id = data.get("id")
        if not media_id:
            return _error_result(f"Meta media upload returned no id: {data}")
        return {"success": True, "media_id": media_id, "error": None}
    except Exception as exc:
        masked_phone_id = phone_number_id[:3] + "..." + phone_number_id[-3:] if len(phone_number_id) > 6 else "***"
        err = f"Meta media upload failed: {exc}"
        frappe.logger("ai_workplace").error(
            f"WhatsApp Sender: {err} (domain=graph.facebook.com, api_ver={api_version}, phone_id={masked_phone_id})"
        )
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

    import subprocess
    import json
    
    headers = [
        "-H", f"Authorization: Bearer {access_token}",
        "-H", "Content-Type: application/json"
    ]

    try:
        cmd = ["curl", "-s", "-X", "POST", url] + headers + ["-d", json.dumps(payload)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SEND_TIMEOUT_SECONDS)
        
        if result.returncode != 0:
            return _error_result(f"Curl failed with code {result.returncode}: {result.stderr}")
            
        try:
            data = json.loads(result.stdout)
        except Exception:
            return _error_result(f"Invalid JSON response from Meta: {result.stdout}")
            
        if "error" in data:
            err_info = data.get("error", {})
            return _error_result(f"Meta API error: {err_info.get('message', str(err_info))}")
            
        message_id = None
        messages = data.get("messages", [])
        if messages:
            message_id = messages[0].get("id")

        return {"success": True, "message_id": message_id, "error": None}

    except subprocess.TimeoutExpired:
        err = f"Meta API request timed out after {_SEND_TIMEOUT_SECONDS}s"
        frappe.logger("ai_workplace").error(f"WhatsApp Sender: {err}")
        return _error_result(err)

    except Exception as exc:
        masked_phone_id = phone_number_id[:3] + "..." + phone_number_id[-3:] if len(phone_number_id) > 6 else "***"
        err = f"Unexpected error sending WhatsApp message: {exc}"
        frappe.logger("ai_workplace").error(
            f"WhatsApp Sender: {err} (domain=graph.facebook.com, api_ver={api_version}, phone_id={masked_phone_id})"
        )
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

