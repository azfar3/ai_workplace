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


def send_video_message(
    phone_number: str,
    media_id: str,
    caption: str = "",
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a WhatsApp video message using a Meta media id."""
    video_payload: dict[str, Any] = {"id": media_id}
    if caption:
        video_payload["caption"] = caption
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "video",
        "video": video_payload,
    }
    return _post_message(phone_number, payload, settings)


def send_audio_message(
    phone_number: str,
    media_id: str,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    """Send a WhatsApp audio message using a Meta media id."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "audio",
        "audio": {"id": media_id},
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

    cfg = settings
    if not cfg:
        try:
            cfg = frappe.get_single("AI Workplace Settings")
        except Exception:
            pass
    is_custom = cfg.get("custom_whatsapp_api_enabled") if cfg else False

    if is_custom and outbound.follow_up:
        _consolidate_custom_api_interactive(outbound)

    result = _send_single_message(phone_number, outbound, settings=settings)
    if not result.get("success"):
        return result

    last_result = result
    for extra in outbound.follow_up or []:
        follow_result = send_message(phone_number, extra, settings=settings)
        if follow_result.get("success"):
            last_result = follow_result
        else:
            frappe.logger("ai_workplace").warning(
                f"AI Workplace: Follow-up message send failed: {follow_result.get('error')}"
            )
    return last_result

def _consolidate_custom_api_interactive(outbound: OutboundMessage) -> None:
    """
    Consolidates multiple interactive follow-up messages into the first one 
    when using the Custom Baileys API, avoiding multi-message clutter.
    """
    interactives = [msg for msg in outbound.follow_up if msg.is_interactive()]
    if len(interactives) <= 1:
        return
        
    primary = interactives[0]
    p_type = primary.interactive.get("type")
    p_action = primary.interactive.setdefault("action", {})
    
    for secondary in interactives[1:]:
        s_type = secondary.interactive.get("type")
        s_action = secondary.interactive.get("action", {})
        
        if p_type == "button" and s_type == "button":
            p_action.setdefault("buttons", []).extend(s_action.get("buttons", []))
        elif p_type == "list" and s_type == "list":
            p_action.setdefault("sections", []).extend(s_action.get("sections", []))
        elif p_type == "button" and s_type == "list":
            # Convert primary to list by creating a section from its buttons
            buttons = p_action.get("buttons", [])
            rows = []
            for btn in buttons:
                reply = btn.get("reply", {})
                rows.append({"id": reply.get("id"), "title": reply.get("title", ""), "description": ""})
            p_type = "list"
            primary.interactive["type"] = "list"
            p_action["sections"] = [{"title": "Options", "rows": rows}] + s_action.get("sections", [])
            p_action.pop("buttons", None)
            p_action["button"] = "Select Option"
        elif p_type == "list" and s_type == "button":
            # Append secondary buttons as list rows to the primary list
            buttons = s_action.get("buttons", [])
            rows = []
            for btn in buttons:
                reply = btn.get("reply", {})
                rows.append({"id": reply.get("id"), "title": reply.get("title", ""), "description": ""})
            if p_action.get("sections"):
                p_action["sections"][-1].setdefault("rows", []).extend(rows)
            else:
                p_action["sections"] = [{"title": "Options", "rows": rows}]
                
        outbound.follow_up.remove(secondary)


def _send_single_message(
    phone_number: str,
    outbound: OutboundMessage,
    settings: Optional[Any] = None,
) -> dict[str, Any]:
    if outbound.has_document():
        cfg = settings
        if not cfg:
            try:
                cfg = frappe.get_single("AI Workplace Settings")
            except Exception:
                pass
        
        is_custom = cfg.get("custom_whatsapp_api_enabled") if cfg else False
        
        if is_custom:
            from frappe.utils.file_manager import save_file
            import uuid
            
            fname = outbound.document_filename or f"media_{uuid.uuid4().hex[:8]}"
            file_doc = save_file(
                fname=fname,
                content=outbound.document_bytes or b"",
                dt="User",
                dn="Guest",
                is_private=0
            )
            media_url = frappe.utils.get_url(file_doc.file_url)
            media_type = "image" if (outbound.document_mimetype or "").startswith("image/") else "document"
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone_number.lstrip("+"),
                "type": "media",
                "media_url": media_url,
                "media_type": media_type,
            }
            if outbound.document_caption or outbound.body_text:
                payload["text"] = {"body": outbound.document_caption or outbound.body_text}
            return _post_message(phone_number, payload, settings=settings)

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

    is_custom = cfg.get("custom_whatsapp_api_enabled")
    if is_custom:
        url = cfg.get("custom_whatsapp_api_url")
        if not url:
            return _error_result("Custom WhatsApp API URL is not configured")
        
        custom_token = ""
        if cfg.get("custom_whatsapp_api_token"):
            try:
                custom_token = cfg.get_password("custom_whatsapp_api_token") or ""
            except Exception:
                custom_token = cfg.get("custom_whatsapp_api_token") or ""
            
        headers = ["-H", "Content-Type: application/json"]
        if custom_token:
            headers.extend(["-H", f"Authorization: Bearer {custom_token}"])
            
        payload = _transform_to_baileys(payload)
    else:
        if not access_token:
            return _error_result("Meta Access Token is not configured")

        if not phone_number_id:
            return _error_result("Meta Phone Number ID is not configured")

        url = (
            f"https://graph.facebook.com/{api_version}"
            f"/{phone_number_id}/messages"
        )
        headers = [
            "-H", f"Authorization: Bearer {access_token}",
            "-H", "Content-Type: application/json"
        ]

    import subprocess
    import json

    try:
        cmd = ["curl", "-s", "-X", "POST", url] + headers + ["-d", json.dumps(payload)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SEND_TIMEOUT_SECONDS)
        
        if result.returncode != 0:
            return _error_result(f"Curl failed with code {result.returncode}: {result.stderr}")
            
        if is_custom:
            try:
                data = json.loads(result.stdout)
                msg_id = data.get("message_id") or data.get("id") or "custom"
            except Exception:
                msg_id = "custom"
            return {"success": True, "message_id": msg_id, "error": None}

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


def _transform_to_baileys(payload: dict[str, Any]) -> dict[str, Any]:
    """Transforms a Meta Graph API payload into a Baileys-compatible payload."""
    number = payload.get("to", "")
    message: Any = ""
    msg_type = payload.get("type", "text")
    
    media_url = ""
    media_type = ""
    
    if msg_type == "text":
        message = payload.get("text", {}).get("body", "")
    elif msg_type == "media":
        message = payload.get("text", {}).get("body", "")
        media_url = payload.get("media_url", "")
        media_type = payload.get("media_type", "")
    elif msg_type == "interactive":
        interactive = payload.get("interactive", {})
        itype = interactive.get("type")
        body_text = interactive.get("body", {}).get("text", "")
        header_text = interactive.get("header", {}).get("text", "")
        footer_text = interactive.get("footer", {}).get("text", "")
        
        full_text = body_text
        if header_text:
            full_text = f"{header_text}\n\n{full_text}"
        if footer_text:
            full_text = f"{full_text}\n\n{footer_text}"
            
        import time
        now = int(time.time())
        
        if itype == "button":
            menu_text = f"{full_text}\n"
            existing_cache_obj = frappe.cache().get_value(f"custom_wa_menu_{number.lstrip('+')}")
            
            existing_map = {}
            if existing_cache_obj and isinstance(existing_cache_obj, dict) and "map" in existing_cache_obj:
                if existing_cache_obj.get("timestamp", 0) > now - 15:
                    existing_map = existing_cache_obj.get("map", {})
                
            start_idx = len(existing_map) + 1
            option_map = dict(existing_map)
            
            for idx, btn in enumerate(interactive.get("action", {}).get("buttons", [])):
                opt_num = str(start_idx + idx)
                reply = btn.get("reply", {})
                menu_text += f"\n{opt_num}. {reply.get('title', '')}"
                option_map[opt_num] = reply.get("id") or reply.get("title")
            message = menu_text.strip()
            if option_map:
                new_cache_obj = {
                    "timestamp": existing_cache_obj.get("timestamp") if (isinstance(existing_cache_obj, dict) and existing_cache_obj.get("timestamp", 0) > now - 15) else now,
                    "map": option_map
                }
                frappe.cache().set_value(f"custom_wa_menu_{number.lstrip('+')}", new_cache_obj, expires_in_sec=86400)
                
        elif itype == "list":
            menu_text = f"{full_text}\n"
            existing_cache_obj = frappe.cache().get_value(f"custom_wa_menu_{number.lstrip('+')}")
            
            existing_map = {}
            if existing_cache_obj and isinstance(existing_cache_obj, dict) and "map" in existing_cache_obj:
                if existing_cache_obj.get("timestamp", 0) > now - 15:
                    existing_map = existing_cache_obj.get("map", {})
                
            opt_idx = len(existing_map) + 1
            option_map = dict(existing_map)
            
            for sec in interactive.get("action", {}).get("sections", []):
                if sec.get("title"):
                    menu_text += f"\n*{sec.get('title')}*\n"
                for row in sec.get("rows", []):
                    opt_num = str(opt_idx)
                    menu_text += f"{opt_num}. {row.get('title')}\n"
                    option_map[opt_num] = row.get("id") or row.get("title")
                    opt_idx += 1
            message = menu_text.strip()
            if option_map:
                new_cache_obj = {
                    "timestamp": existing_cache_obj.get("timestamp") if (isinstance(existing_cache_obj, dict) and existing_cache_obj.get("timestamp", 0) > now - 15) else now,
                    "map": option_map
                }
                frappe.cache().set_value(f"custom_wa_menu_{number.lstrip('+')}", new_cache_obj, expires_in_sec=86400)
        else:
            message = full_text
    else:
        message = "Message type not supported by custom API."
    
    try:
        active_session = frappe.get_all("Whatsapp Session", filters={"status": "connected"}, fields=["email"], limit=1)
        username = active_session[0].email if active_session and active_session[0].email else "AI Workplace"
    except Exception:
        username = "AI Workplace"

    out = {
        "number": number,
        "message": message,
        "username": username
    }
    
    if media_url:
        out["media_url"] = media_url
        out["media_type"] = media_type
        
    if payload.get("media_base64"):
        out["media_base64"] = payload.get("media_base64")
        out["mime_type"] = payload.get("mime_type")
        
    return out

