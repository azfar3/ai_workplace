"""
ai_workplace/whatsapp/media.py
──────────────────────────────
Download inbound WhatsApp media from Meta and store as Frappe Files.
"""

from __future__ import annotations

import mimetypes
import os
import uuid
from typing import Any, Optional

import frappe
import requests

from ai_workplace.whatsapp.sender import _DEFAULT_GRAPH_API_VERSION, _get_access_token

_DOWNLOAD_TIMEOUT_SECONDS = 60
_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".zip", ".ppt", ".pptx", ".rar", ".7z"}
ALLOWED_ATTACHMENT_EXTENSIONS = _IMAGE_EXTENSIONS | _DOCUMENT_EXTENSIONS


def is_allowed_attachment_filename(filename: str) -> bool:
    """Return True when filename extension is an allowed WhatsApp upload type."""
    ext = os.path.splitext((filename or "").strip())[1].lower()
    return bool(ext) and ext in ALLOWED_ATTACHMENT_EXTENSIONS


def _validate_file_content(content: bytes, filename: str) -> None:
    if len(content) > _MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File size exceeds {_MAX_FILE_SIZE_BYTES // (1024*1024)}MB limit")

    ext = os.path.splitext(filename)[1].lower()

    if ext in (".jpg", ".jpeg") and not content.startswith(b"\xff\xd8\xff"):
        raise ValueError("Invalid JPEG file signature")
    if ext == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG file signature")
    if ext == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF file signature")


def fetch_inbound_media(parsed: dict[str, Any], settings: Optional[Any] = None) -> dict[str, Any]:
    """Download WhatsApp media referenced in a parsed webhook payload."""
    media_id = (parsed.get("media_id") or "").strip()
    if not media_id:
        return {"success": False, "file_url": "", "filename": "", "error": "Missing media id"}

    try:
        cfg = settings or frappe.get_single("AI Workplace Settings")
    except Exception as exc:
        return {"success": False, "file_url": "", "filename": "", "error": str(exc)}

    access_token = _get_access_token(cfg)
    api_version = cfg.get("graph_api_version") or _DEFAULT_GRAPH_API_VERSION
    if not access_token:
        return {"success": False, "file_url": "", "filename": "", "error": "Meta access token missing"}

    headers = {"Authorization": f"Bearer {access_token}"}
    meta_url = f"https://graph.facebook.com/{api_version}/{media_id}"

    try:
        meta_resp = requests.get(
            meta_url,
            headers=headers,
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            proxies={"http": None, "https": None},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        download_url = meta.get("url") or ""
        mime_type = meta.get("mime_type") or ""
        if not download_url:
            return {"success": False, "file_url": "", "filename": "", "error": f"No download URL: {meta}"}

        file_resp = requests.get(
            download_url,
            headers=headers,
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            proxies={"http": None, "https": None},
        )
        file_resp.raise_for_status()
        content = file_resp.content

        filename = _resolve_filename(parsed, mime_type)
        
        # Security validation
        _validate_file_content(content, filename)
        
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"WhatsApp Media: download/validation failed for {media_id}: {exc}")
        return {"success": False, "file_url": "", "filename": "", "error": str(exc)}

    file_doc = _save_file(content, filename, mime_type)
    return {
        "success": True,
        "file_url": file_doc.file_url,
        "file_doc_name": file_doc.name,
        "filename": file_doc.file_name,
        "error": None,
    }


def read_frappe_file_bytes(file_doc: Any) -> tuple[bytes, str, str]:
    """Return file bytes, filename, and mime type from a Frappe File document."""
    filename = file_doc.file_name or os.path.basename(file_doc.file_url or "attachment")
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if hasattr(file_doc, "get_content"):
        try:
            content = file_doc.get_content()
            if content:
                return content, filename, mime_type
        except Exception:
            pass

    file_path = file_doc.get_full_path()
    if file_path and os.path.exists(file_path):
        with open(file_path, "rb") as handle:
            return handle.read(), filename, mime_type

    file_url = (file_doc.file_url or "").strip()
    if file_url.startswith("/"):
        site_path = frappe.get_site_path("public", file_url.lstrip("/"))
        if os.path.exists(site_path):
            with open(site_path, "rb") as handle:
                return handle.read(), filename, mime_type
        private_path = frappe.get_site_path("private", file_url.lstrip("/"))
        if os.path.exists(private_path):
            with open(private_path, "rb") as handle:
                return handle.read(), filename, mime_type
        site_url = frappe.utils.get_url(file_url)
        response = requests.get(
            site_url,
            timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            proxies={"http": None, "https": None},
        )
        response.raise_for_status()
        return response.content, filename, mime_type

    frappe.throw(frappe._("Could not read the uploaded file."))


def _resolve_filename(parsed: dict[str, Any], mime_type: str) -> str:
    explicit = (parsed.get("media_filename") or "").strip()
    if explicit:
        return explicit

    message_type = (parsed.get("message_type") or parsed.get("raw_type") or "media").lower()
    ext = mimetypes.guess_extension(mime_type or "") or ""
    if message_type == "image" and ext in ("", ".jpe"):
        ext = ".jpg"
    if not ext:
        ext = ".bin"
    return f"whatsapp-{message_type}-{uuid.uuid4().hex[:10]}{ext}"


def _save_file(content: bytes, filename: str, mime_type: str) -> Any:
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": filename,
            "is_private": 0,
            "content": content,
        }
    )
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return file_doc
