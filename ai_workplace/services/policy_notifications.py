"""
Policy Notifications Service — Direct chunking of System Notifications of type 'Policy'
into AI Workplace Knowledge Chunk without requiring AI Workplace Knowledge Source or AI Knowledge Entry doctype records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import frappe
from frappe.utils import strip_html


def clean_text_content(html_content: str) -> str:
    """Clean HTML content into plain text for knowledge indexing."""
    if not html_content:
        return ""
    text = strip_html(html_content or "")
    text = re.sub(r"\n\s*\n", "\n\n", text).strip()
    return text


def extract_text_from_file_path_or_url(file_url: str) -> str:
    """Extract plain text from PDF, DOCX, TXT, MD attachments."""
    if not file_url:
        return ""

    clean_url = file_url.strip().lstrip("/")
    possible_paths = [
        frappe.get_site_path(clean_url),
        frappe.get_site_path("public", clean_url),
        frappe.get_site_path("private", clean_url),
        os.path.join(frappe.get_site_path(), clean_url),
    ]

    file_path = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.isfile(p):
            file_path = p
            break

    if not file_path:
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pdf":
            try:
                import fitz
                pdf_doc = fitz.open(file_path)
                return "\n".join(page.get_text().strip() for page in pdf_doc if page.get_text().strip())
            except Exception:
                try:
                    import pypdf
                    reader = pypdf.PdfReader(file_path)
                    return "\n".join(page.extract_text().strip() for page in reader.pages if page.extract_text())
                except Exception:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        return "\n".join(page.extract_text().strip() for page in reader.pages if page.extract_text())
        elif ext == ".docx":
            import docx
            doc = docx.Document(file_path)
            return "\n".join(para.text.strip() for para in doc.paragraphs if para.text.strip())
        elif ext in (".txt", ".md", ".csv", ".json"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Failed to parse policy document attachment {file_url}: {exc}")

    return ""


def sync_policy_notification_to_chunks(doc, method=None) -> None:
    """
    Directly chunk and index a System Notifications record of type 'Policy'
    into AI Workplace Knowledge Chunk.
    """
    if isinstance(doc, str):
        if not frappe.db.exists("System Notifications", doc):
            return
        doc = frappe.get_doc("System Notifications", doc)

    if not hasattr(doc, "doctype") or doc.doctype != "System Notifications":
        return

    is_policy = (doc.get("notification_type") or "").strip().lower() == "policy"
    is_published = bool(doc.get("is_published"))

    # If not a policy notification or not published, clean up any existing chunks
    if not is_policy or not is_published:
        delete_policy_notification_chunks(doc)
        return

    # Extract text from HTML body
    notif_body_html = doc.get("notifiction") or ""
    body_text = clean_text_content(notif_body_html)

    # Extract text from attachment if present
    attachment_url = doc.get("policy_document") or ""
    attachment_text = extract_text_from_file_path_or_url(attachment_url) if attachment_url else ""

    subject = (doc.get("subject") or doc.name).strip()
    version = doc.get("version") or "1.0"

    full_content_parts = [f"[Policy: {subject}] (Version: {version})"]
    if body_text:
        full_content_parts.append(body_text)
    if attachment_text:
        full_content_parts.append(f"--- Attachment Content ---\n{attachment_text}")

    combined_text = "\n\n".join(full_content_parts).strip()
    if not combined_text:
        delete_policy_notification_chunks(doc)
        return

    from ai_workplace.ai.indexer import _chunk_text_with_overlap, generate_embedding, _get_setting

    raw_chunks = _chunk_text_with_overlap(combined_text, doc_name=subject)
    if not raw_chunks:
        delete_policy_notification_chunks(doc)
        return

    _ensure_policy_knowledge_source_exists()
    delete_policy_notification_chunks(doc)

    emb_model = _get_setting("embedding_model", "text-embedding-3-small")
    effective_date = doc.get("last_updated_on") or doc.get("published_from") or frappe.utils.today()

    for idx, chunk_info in enumerate(raw_chunks):
        text = chunk_info["text"]
        c_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        vec = generate_embedding(text)
        emb_json = json.dumps(vec) if vec else ""

        chunk = frappe.new_doc("AI Workplace Knowledge Chunk")
        chunk.knowledge_source = "policies"
        chunk.chunk_index = idx
        chunk.chunk_text = text
        chunk.content_hash = c_hash
        chunk.document_name = subject
        chunk.document_type = "System Notifications"
        chunk.section = chunk_info.get("section") or subject
        chunk.policy_version = version
        chunk.effective_date = effective_date
        chunk.access_level = f"sysnotif:{doc.name}"
        chunk.embedding_model = emb_model
        chunk.embedding_dimensions = len(vec) if vec else 128
        chunk.embedding_json = emb_json

        chunk.insert(ignore_permissions=True)

    frappe.db.commit()


def delete_policy_notification_chunks(doc, method=None) -> None:
    """Delete all Knowledge Chunks generated for a specific System Notifications doc."""
    doc_name = doc.get("name") if hasattr(doc, "get") else str(doc)
    if not doc_name:
        return

    frappe.db.delete(
        "AI Workplace Knowledge Chunk",
        {
            "document_type": "System Notifications",
            "access_level": f"sysnotif:{doc_name}",
        },
    )

    subject = doc.get("subject") if hasattr(doc, "get") else None
    if subject:
        frappe.db.delete(
            "AI Workplace Knowledge Chunk",
            {
                "document_type": "System Notifications",
                "document_name": subject,
            },
        )
    frappe.db.commit()


def sync_all_policy_notifications() -> dict[str, int]:
    """
    Sync all published System Notifications of type 'Policy' directly into AI Workplace Knowledge Chunk,
    and remove obsolete legacy policy knowledge sources.
    """
    notifications = frappe.db.get_all(
        "System Notifications",
        filters={"notification_type": "Policy", "is_published": 1},
        fields=["name"],
    )

    synced_count = 0
    for n in notifications:
        doc = frappe.get_doc("System Notifications", n.name)
        sync_policy_notification_to_chunks(doc)
        synced_count += 1

    _cleanup_legacy_policy_knowledge_sources()
    return {"synced": synced_count}


def _ensure_policy_knowledge_source_exists() -> None:
    if not frappe.db.exists("AI Workplace Knowledge Source", "policies"):
        source = frappe.new_doc("AI Workplace Knowledge Source")
        source.source_name = "policies"
        source.source_type = "Policy"
        source.description = "System Policy Notifications"
        source.is_active = 1
        source.insert(ignore_permissions=True)
    else:
        frappe.db.set_value("AI Workplace Knowledge Source", "policies", "is_active", 1, update_modified=False)


def _cleanup_legacy_policy_knowledge_sources() -> None:
    """Remove individual Knowledge Source records created previously for System Notifications."""
    if not frappe.db.exists("DocType", "AI Workplace Knowledge Source"):
        return

    legacy_sources = frappe.db.get_all(
        "AI Workplace Knowledge Source",
        filters={"source_type": "Policy", "name": ["!=", "policies"]},
        fields=["name"],
    )
    for s in legacy_sources:
        frappe.db.delete("AI Workplace Knowledge Chunk", {"knowledge_source": s.name})
        frappe.db.delete("AI Workplace Knowledge Source", {"name": s.name})

    frappe.db.commit()
