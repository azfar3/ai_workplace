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
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Send a plain-text WhatsApp message via the Meta Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "text",
        "text": {"body": message, "preview_url": False},
    }
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


def send_interactive_message(
    phone_number: str,
    body_text: str,
    interactive: dict[str, Any],
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Send a WhatsApp interactive message (list or button)."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "interactive",
        "interactive": interactive,
    }
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


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
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
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
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


def send_document_message(
    phone_number: str,
    media_id: str,
    filename: str,
    caption: str = "",
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
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
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


def send_video_message(
    phone_number: str,
    media_id: str,
    caption: str = "",
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
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
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


def send_audio_message(
    phone_number: str,
    media_id: str,
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Send a WhatsApp audio message using a Meta media id."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number.lstrip("+"),
        "type": "audio",
        "audio": {"id": media_id},
    }
    return _post_message(
        phone_number,
        payload,
        settings,
        session_name=session_name,
        receiver=receiver,
        receiver_name=receiver_name,
        username=username,
        session_id=session_id,
    )


def send_message(
    phone_number: str,
    outbound: Union[OutboundMessage, str],
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Send an OutboundMessage (text or interactive) or plain string.
    Falls back to text if interactive send fails.
    """
    effective_receiver = receiver or (getattr(outbound, "receiver", None) if isinstance(outbound, OutboundMessage) else None)
    effective_receiver_name = receiver_name or (getattr(outbound, "receiver_name", None) if isinstance(outbound, OutboundMessage) else None)
    effective_username = username or (getattr(outbound, "username", None) if isinstance(outbound, OutboundMessage) else None)
    effective_session_id = session_id or (getattr(outbound, "session_id", None) if isinstance(outbound, OutboundMessage) else None)
    effective_session = session_name or (getattr(outbound, "session_name", None) if isinstance(outbound, OutboundMessage) else None) or effective_receiver or effective_receiver_name

    if isinstance(outbound, str):
        return send_text_message(
            phone_number,
            outbound,
            settings=settings,
            session_name=effective_session,
            receiver=effective_receiver,
            receiver_name=effective_receiver_name,
            username=effective_username,
            session_id=effective_session_id,
        )

    cfg = settings
    if not cfg:
        try:
            cfg = frappe.get_single("AI Workplace Settings")
        except Exception:
            pass
    is_custom = cfg.get("custom_whatsapp_api_enabled") if cfg else False

    if is_custom and outbound.follow_up and not outbound.preserve_follow_up:
        _consolidate_custom_api_interactive(outbound)

    result = _send_single_message(
        phone_number,
        outbound,
        settings=settings,
        session_name=effective_session,
        receiver=effective_receiver,
        receiver_name=effective_receiver_name,
        username=effective_username,
        session_id=effective_session_id,
    )
    if not result.get("success"):
        return result

    last_result = result
    for extra in outbound.follow_up or []:
        extra_receiver = getattr(extra, "receiver", None) or effective_receiver
        extra_receiver_name = getattr(extra, "receiver_name", None) or effective_receiver_name
        extra_username = getattr(extra, "username", None) or effective_username
        extra_session_id = getattr(extra, "session_id", None) or effective_session_id
        extra_session = getattr(extra, "session_name", None) or effective_session

        follow_result = send_message(
            phone_number,
            extra,
            settings=settings,
            session_name=extra_session,
            receiver=extra_receiver,
            receiver_name=extra_receiver_name,
            username=extra_username,
            session_id=extra_session_id,
        )
        if follow_result.get("success"):
            last_result = follow_result
        else:
            frappe.logger("ai_workplace").warning(
                f"AI Workplace: Follow-up message send failed: {follow_result.get('error')}"
            )
    return last_result

def _consolidate_custom_api_interactive(outbound: OutboundMessage) -> None:
    """
    Consolidates interactive follow-up messages into the primary message
    when using the Custom Baileys API, avoiding multi-message clutter.
    """
    interactives = [msg for msg in outbound.follow_up if msg.is_interactive()]
    if not interactives:
        return

    # If outbound is plain text without media, absorb single interactive button directly
    if not outbound.is_interactive() and not outbound.has_media() and len(interactives) == 1:
        single = interactives[0]
        outbound.interactive = single.interactive
        orig_body = (outbound.body_text or "").strip()
        btn_body = (single.interactive.get("body", {}).get("text") or "").strip()
        if orig_body and btn_body:
            outbound.interactive["body"] = {"text": f"{orig_body}\n\n{btn_body}"}
        elif btn_body:
            outbound.interactive["body"] = {"text": btn_body}
        outbound.follow_up.remove(single)
        return

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
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    effective_receiver = receiver or getattr(outbound, "receiver", None)
    effective_receiver_name = receiver_name or getattr(outbound, "receiver_name", None)
    effective_username = username or getattr(outbound, "username", None)
    effective_session_id = session_id or getattr(outbound, "session_id", None)
    effective_session = session_name or getattr(outbound, "session_name", None) or effective_receiver or effective_receiver_name

    if outbound.body_text:
        try:
            from ai_workplace.ai.response_formatter import ResponseFormatter
            outbound.body_text = ResponseFormatter.sanitize_whatsapp_text(outbound.body_text)
        except Exception:
            pass

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
            return _post_message(
                phone_number,
                payload,
                settings=settings,
                session_name=effective_session,
                receiver=effective_receiver,
                receiver_name=effective_receiver_name,
                username=effective_username,
                session_id=effective_session_id,
            )

        upload = upload_media_bytes(
            outbound.document_bytes or b"",
            outbound.document_mimetype or "application/octet-stream",
            outbound.document_filename or "file",
            settings=settings,
        )
        if not upload.get("success"):
            if outbound.body_text:
                return send_text_message(
                    phone_number,
                    outbound.body_text,
                    settings=settings,
                    session_name=effective_session,
                    receiver=effective_receiver,
                    receiver_name=effective_receiver_name,
                    username=effective_username,
                    session_id=effective_session_id,
                )
            return upload

        caption = outbound.document_caption or outbound.body_text or ""
        return send_document_message(
            phone_number,
            upload["media_id"],
            outbound.document_filename or "file",
            caption=caption,
            settings=settings,
            session_name=effective_session,
            receiver=effective_receiver,
            receiver_name=effective_receiver_name,
            username=effective_username,
            session_id=effective_session_id,
        )

    if outbound.is_interactive():
        result = send_interactive_message(
            phone_number,
            outbound.body_text,
            outbound.interactive,
            settings=settings,
            session_name=effective_session,
            receiver=effective_receiver,
            receiver_name=effective_receiver_name,
            username=effective_username,
            session_id=effective_session_id,
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
                    session_name=effective_session,
                    receiver=effective_receiver,
                    receiver_name=effective_receiver_name,
                    username=effective_username,
                    session_id=effective_session_id,
                )
                if retry_res.get("success"):
                    return retry_res

            fallback = outbound.body_text
            if fallback:
                frappe.logger("ai_workplace").warning(
                    f"AI Workplace: Interactive send failed ({result.get('error')}); falling back to text"
                )
                return send_text_message(
                    phone_number,
                    fallback,
                    settings=settings,
                    session_name=effective_session,
                    receiver=effective_receiver,
                    receiver_name=effective_receiver_name,
                    username=effective_username,
                    session_id=effective_session_id,
                )
        return result

    return send_text_message(
        phone_number,
        outbound.body_text,
        settings=settings,
        session_name=effective_session,
        receiver=effective_receiver,
        receiver_name=effective_receiver_name,
        username=effective_username,
        session_id=effective_session_id,
    )


def _post_message(
    phone_number: str,
    payload: dict[str, Any],
    settings: Optional[Any] = None,
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
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
            
        payload = _transform_to_baileys(
            payload,
            session_name=session_name,
            receiver=receiver,
            receiver_name=receiver_name,
            username=username,
            session_id=session_id,
        )
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


def _resolve_baileys_session(
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, str]:
    """
    Resolve the Baileys session attributes (receiver, receiver_name, username, session_id).
    Matches against 'Whatsapp Session' or propagates provided identifiers.
    """
    res = {
        "receiver": str(receiver or "").strip(),
        "receiver_name": str(receiver_name or "").strip(),
        "username": str(username or "").strip(),
        "session_id": str(session_id or "").strip(),
    }

    identifiers = [
        res["receiver"],
        res["username"],
        res["session_id"],
        session_name,
        res["receiver_name"],
    ]

    matched_session = None
    for ident in identifiers:
        if not ident:
            continue
        ident_str = str(ident).strip()
        try:
            for field in ("session_id", "phone_number", "email", "full_name", "name"):
                matched = frappe.get_all(
                    "Whatsapp Session",
                    filters={field: ident_str},
                    fields=["session_id", "email", "name", "phone_number", "full_name"],
                    limit=1,
                )
                if matched:
                    matched_session = matched[0]
                    break
            if matched_session:
                break

            digits = "".join(filter(str.isdigit, ident_str))
            if len(digits) >= 7:
                all_sessions = frappe.get_all(
                    "Whatsapp Session",
                    fields=["session_id", "email", "name", "phone_number", "full_name"],
                )
                for s in all_sessions:
                    s_phone_val = getattr(s, "phone_number", None) or (s.get("phone_number") if isinstance(s, dict) else "") or ""
                    s_phone = "".join(filter(str.isdigit, str(s_phone_val)))
                    if s_phone and (s_phone == digits or s_phone.endswith(digits[-9:]) or digits.endswith(s_phone[-9:])):
                        matched_session = s
                        break
            if matched_session:
                break
        except Exception:
            pass

    if matched_session:
        def _get_val(obj, key):
            val = getattr(obj, key, None)
            if val is None and isinstance(obj, dict):
                val = obj.get(key)
            return val

        sid = _get_val(matched_session, "session_id") or _get_val(matched_session, "email") or _get_val(matched_session, "name") or ""
        phone = _get_val(matched_session, "phone_number") or sid
        fname = _get_val(matched_session, "full_name") or ""

        # If username/session_id was not explicitly specified or was passed as display name/phone, canonicalize to sid
        if not res["username"] or res["username"] == fname or res["username"] == phone:
            res["username"] = sid
        if not res["session_id"] or res["session_id"] == fname or res["session_id"] == phone:
            res["session_id"] = sid
        if not res["receiver"] or res["receiver"] == fname:
            res["receiver"] = phone
        if not res["receiver_name"] and fname:
            res["receiver_name"] = fname

    # If still not fully resolved, fill in from any available identifier
    fallback_id = res["session_id"] or res["username"] or res["receiver"] or session_name or res["receiver_name"] or ""
    if not res["username"] and fallback_id:
        res["username"] = fallback_id
    if not res["session_id"] and fallback_id:
        res["session_id"] = fallback_id
    if not res["receiver"] and fallback_id:
        res["receiver"] = fallback_id

    # If nothing was provided at all, fallback to the default active session
    if not res["username"] and not res["receiver"]:
        try:
            active_sessions = frappe.get_all(
                "Whatsapp Session",
                filters={"status": "Connected"},
                fields=["session_id", "email", "name", "phone_number", "full_name"],
                limit=1,
            )
            if not active_sessions:
                active_sessions = frappe.get_all(
                    "Whatsapp Session",
                    fields=["session_id", "email", "name", "phone_number", "full_name"],
                    limit=1,
                )
            if active_sessions:
                s = active_sessions[0]
                def _get_val(obj, key):
                    val = getattr(obj, key, None)
                    if val is None and isinstance(obj, dict):
                        val = obj.get(key)
                    return val

                s_id = _get_val(s, "session_id") or _get_val(s, "email") or _get_val(s, "name") or ""
                res["username"] = s_id
                res["session_id"] = s_id
                res["receiver"] = _get_val(s, "phone_number") or s_id
                res["receiver_name"] = _get_val(s, "full_name") or ""
        except Exception:
            pass

    if not res["username"]:
        res["username"] = "Administrator"
    if not res["receiver"]:
        res["receiver"] = res["username"]

    return res


def _resolve_baileys_username(session_name: Optional[str] = None) -> str:
    """Backward compatibility helper for resolving username."""
    sess = _resolve_baileys_session(session_name=session_name)
    return sess.get("username") or "Administrator"


def _transform_to_baileys(
    payload: dict[str, Any],
    session_name: Optional[str] = None,
    receiver: Optional[str] = None,
    receiver_name: Optional[str] = None,
    username: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Transforms a Meta Graph API payload into a Baileys-compatible payload."""
    number = payload.get("to", "")
    message: Any = ""
    msg_type = payload.get("type", "text")

    if msg_type != "interactive":
        _clear_custom_menu_cache(number)
    
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
        import re
        now = int(time.time())
        NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        if itype == "button":
            menu_text = f"{full_text}\n"
            start_idx = 1
            option_map = {}
            
            buttons = interactive.get("action", {}).get("buttons", [])
            is_urdu = any("\u0600" <= ch <= "\u06ff" for ch in full_text) or any(
                any("\u0600" <= ch <= "\u06ff" for ch in b.get("reply", {}).get("title", "")) for b in buttons
            )
            
            for idx, btn in enumerate(buttons):
                curr_idx = start_idx + idx
                opt_num = str(curr_idx)
                reply = btn.get("reply", {})
                btn_title = reply.get("title", "")
                opt_id = reply.get("id") or btn_title
                
                if is_urdu and 0 < curr_idx <= len(NUMBER_EMOJIS):
                    prefix = NUMBER_EMOJIS[curr_idx - 1]
                    menu_text += f"\n{prefix} {btn_title}"
                    option_map[prefix] = opt_id
                else:
                    menu_text += f"\n{opt_num}. {btn_title}"
                
                option_map[opt_num] = opt_id
                option_map[f"{opt_num}."] = opt_id
                option_map[f"{opt_num}۔"] = opt_id
                urdu_digit = opt_num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                option_map[urdu_digit] = opt_id
                if btn_title:
                    option_map[btn_title] = opt_id
                    option_map[btn_title.strip()] = opt_id
                    option_map[btn_title.lower()] = opt_id
                    clean_btn = re.sub(r'[^\w\s]', '', btn_title).strip().lower()
                    if clean_btn:
                        option_map[clean_btn] = opt_id

                is_nav_btn = (
                    opt_id in ("svc_main_menu", "svc_back", "main_menu", "back_to_main")
                    or "back" in opt_id.lower()
                    or "back" in btn_title.lower()
                    or "wapas" in opt_id.lower()
                    or "menu" in btn_title.lower()
                    or "واپس" in btn_title
                    or "پچھلا" in btn_title
                )
                if is_nav_btn:
                    option_map["back"] = opt_id
                    option_map["Back"] = opt_id
                    option_map["b"] = opt_id
                    option_map["0"] = opt_id
                    option_map["wapas"] = opt_id
                    option_map["previous"] = opt_id
                    option_map["previous menu"] = opt_id
                    option_map["pichla menu"] = opt_id
                    option_map["pichle menu"] = opt_id
                    option_map["واپس"] = opt_id
                    option_map["پچھلا مینو"] = opt_id

            message = menu_text.strip()
            if option_map:
                new_cache_obj = {
                    "version": 3,
                    "timestamp": now,
                    "menu_type": "button",
                    "map": option_map
                }
                clean_num = "".join(filter(str.isdigit, number))
                if clean_num:
                    frappe.cache().set_value(f"custom_wa_menu_{clean_num}", new_cache_obj, expires_in_sec=3600)
                    if len(clean_num) >= 10:
                        frappe.cache().set_value(f"custom_wa_menu_{clean_num[-10:]}", new_cache_obj, expires_in_sec=3600)
                        frappe.cache().set_value(f"custom_wa_menu_0{clean_num[-10:]}", new_cache_obj, expires_in_sec=3600)
                frappe.cache().set_value(f"custom_wa_menu_{number.lstrip('+')}", new_cache_obj, expires_in_sec=3600)
                
        elif itype == "list":
            menu_text = f"{full_text}\n"
            opt_idx = 1
            option_map = {}
            
            sections = interactive.get("action", {}).get("sections", [])
            is_urdu = any("\u0600" <= ch <= "\u06ff" for ch in full_text) or any(
                any("\u0600" <= ch <= "\u06ff" for ch in r.get("title", "")) for sec in sections for r in sec.get("rows", [])
            )
            
            for sec in sections:
                if sec.get("title"):
                    menu_text += f"\n*{sec.get('title')}*\n"
                for row in sec.get("rows", []):
                    opt_num = str(opt_idx)
                    row_title = row.get("title", "")
                    row_desc = row.get("description", "")
                    opt_id = row.get("id") or row_title
                    
                    if is_urdu:
                        prefix = NUMBER_EMOJIS[opt_idx - 1] if 0 < opt_idx <= len(NUMBER_EMOJIS) else f"{opt_num}۔"
                        if row_desc and row_desc != row_title:
                            menu_text += f"{prefix} {row_title} — {row_desc}\n"
                        else:
                            menu_text += f"{prefix} {row_title}\n"
                        if 0 < opt_idx <= len(NUMBER_EMOJIS):
                            option_map[NUMBER_EMOJIS[opt_idx - 1]] = opt_id
                    else:
                        if row_desc and row_desc != row_title:
                            menu_text += f"{opt_num}. {row_title} - {row_desc}\n"
                        else:
                            menu_text += f"{opt_num}. {row_title}\n"
                            
                    option_map[opt_num] = opt_id
                    option_map[f"{opt_num}."] = opt_id
                    option_map[f"{opt_num}۔"] = opt_id
                    urdu_digit = opt_num.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
                    option_map[urdu_digit] = opt_id
                    if row_title:
                        option_map[row_title] = opt_id
                        option_map[row_title.strip()] = opt_id
                        option_map[row_title.lower()] = opt_id
                        clean_row = re.sub(r'[^\w\s]', '', row_title).strip().lower()
                        if clean_row:
                            option_map[clean_row] = opt_id

                    if opt_id in ("svc_main_menu", "svc_back") or "main menu" in row_title.lower() or "back" in row_title.lower():
                        option_map["0"] = opt_id
                        option_map["back"] = opt_id
                        option_map["Back"] = opt_id
                        option_map["menu"] = opt_id
                        option_map["wapas"] = opt_id
                    opt_idx += 1
            message = menu_text.strip()
            if option_map:
                new_cache_obj = {
                    "version": 3,
                    "timestamp": now,
                    "menu_type": "list",
                    "map": option_map
                }
                clean_num = "".join(filter(str.isdigit, number))
                if clean_num:
                    frappe.cache().set_value(f"custom_wa_menu_{clean_num}", new_cache_obj, expires_in_sec=3600)
                    if len(clean_num) >= 10:
                        frappe.cache().set_value(f"custom_wa_menu_{clean_num[-10:]}", new_cache_obj, expires_in_sec=3600)
                        frappe.cache().set_value(f"custom_wa_menu_0{clean_num[-10:]}", new_cache_obj, expires_in_sec=3600)
                frappe.cache().set_value(f"custom_wa_menu_{number.lstrip('+')}", new_cache_obj, expires_in_sec=3600)
        else:
            message = full_text
    else:
        message = "Message type not supported by custom API."
    
    sess_info = _resolve_baileys_session(
        session_name=session_name or payload.get("session_name"),
        receiver=receiver or payload.get("receiver") or payload.get("receiver_number"),
        receiver_name=receiver_name or payload.get("receiver_name"),
        username=username or payload.get("username"),
        session_id=session_id or payload.get("session_id"),
    )

    out = {
        "number": number,
        "message": message,
        "username": sess_info["username"],
        "session_id": sess_info["session_id"],
        "receiver": sess_info["receiver"],
        "receiver_number": sess_info["receiver"],
    }
    if sess_info.get("receiver_name"):
        out["receiver_name"] = sess_info["receiver_name"]

    if media_url:
        out["media_url"] = media_url
        out["media_type"] = media_type
        
    if payload.get("media_base64"):
        out["media_base64"] = payload.get("media_base64")
        out["mime_type"] = payload.get("mime_type")
        
    return out


def _clear_custom_menu_cache(number: str) -> None:
    """Forget numbered choices when the latest outgoing message is not a menu."""
    clean_num = "".join(filter(str.isdigit, str(number or "")))
    if not clean_num:
        return
    keys = {f"custom_wa_menu_{clean_num}"}
    if len(clean_num) >= 10:
        keys.add(f"custom_wa_menu_{clean_num[-10:]}")
        keys.add(f"custom_wa_menu_0{clean_num[-10:]}")
    try:
        for key in keys:
            frappe.cache().delete_value(key)
    except Exception:
        pass
