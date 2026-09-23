"""
Policy Notifications Service — Direct chunking of System Notifications of type 'Policy'
into AI Workplace Knowledge Chunk.

Key design decisions
────────────────────
• Each chunk carries `source_type="System Notification"` + `source_id=<doc.name>` so
  that old chunks can be found and deleted by a *stable* identifier (not the title).
• The `access_level` field stores the legacy `sysnotif:<name>` value for backward
  compatibility with any existing filters.
• Chunking is section-aware: the content is split on markdown/numeric headings first,
  then on word count if sections are still too large.
• The process is idempotent: calling it twice for the same doc produces one chunk set.
• If the policy is unpublished or un-typed, existing chunks are cleaned up.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import frappe
from frappe.utils import strip_html


# ──────────────────────────────────────────────────────────────────────────────
# Text helpers
# ──────────────────────────────────────────────────────────────────────────────

def clean_text_content(html_content: str) -> str:
    """Strip HTML and normalise whitespace."""
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
        frappe.logger("ai_workplace").error(
            f"Failed to parse policy document attachment {file_url}: {exc}"
        )

    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Section-aware chunking
# ──────────────────────────────────────────────────────────────────────────────

# Regex that matches common section headings, e.g.:
#   "## Working Hours"  / "1. Working Hours"  / "Section: Working Hours"
_SECTION_HEADING_RE = re.compile(
    r"^(?:#{1,6}|(?:\d+\.)+|\bSection:?\b)\s+(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

_MAX_CHUNK_WORDS = 300
_OVERLAP_WORDS   = 50


def _split_into_sections(text: str) -> list[dict[str, str]]:
    """
    Split `text` on section headings.
    Returns: [{"title": "...", "body": "..."}]
    If no headings are found, the entire text is one section.
    """
    positions = [(m.start(), m.group(1).strip()) for m in _SECTION_HEADING_RE.finditer(text)]
    if not positions:
        return [{"title": "", "body": text.strip()}]

    sections = []
    for i, (start, title) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[start:end].strip()
        # Remove the heading line itself from body
        first_nl = body.find("\n")
        body = body[first_nl:].strip() if first_nl != -1 else ""
        if body:
            sections.append({"title": title, "body": body})

    # Preamble before first heading
    preamble = text[: positions[0][0]].strip()
    if preamble:
        sections.insert(0, {"title": "", "body": preamble})

    return sections if sections else [{"title": "", "body": text.strip()}]


def _chunk_section(title: str, body: str, doc_name: str) -> list[dict[str, str]]:
    """
    Chunk a single section body.  If it fits in MAX_CHUNK_WORDS, return one chunk.
    Otherwise produce overlapping sub-chunks, each prefixed with the section title.
    """
    words = body.split()
    if len(words) <= _MAX_CHUNK_WORDS:
        text = f"{title}\n{body}".strip() if title else body
        return [{"text": text, "section": title}]

    chunks = []
    step = _MAX_CHUNK_WORDS - _OVERLAP_WORDS
    for i in range(0, len(words), step):
        chunk_words = words[i : i + _MAX_CHUNK_WORDS]
        chunk_body = " ".join(chunk_words)
        text = f"{title}\n{chunk_body}".strip() if title else chunk_body
        if text.strip():
            chunks.append({"text": text, "section": title})
    return chunks


def build_section_chunks(content: str, doc_name: str) -> list[dict[str, str]]:
    """
    Full chunking pipeline: split into sections → chunk each section.
    Returns: [{"text": "...", "section": "...", "document_name": "..."}]
    """
    if not content or not content.strip():
        return []

    sections = _split_into_sections(content)
    chunks = []
    for sec in sections:
        for chunk in _chunk_section(sec["title"], sec["body"], doc_name):
            chunk["document_name"] = doc_name
            chunks.append(chunk)
    return chunks


# ──────────────────────────────────────────────────────────────────────────────
# Main sync function
# ──────────────────────────────────────────────────────────────────────────────

def sync_policy_notification_to_chunks(doc, method=None) -> None:
    """
    Hook-compatible entry point.
    Called on_update and on_insert of System Notifications.

    Algorithm
    ---------
    1.  Validate: must be doctype=System Notifications AND notification_type=Policy AND is_published.
    2.  Extract full content (HTML body + PDF/DOCX attachment).
    3.  Delete ALL existing chunks whose source_id == doc.name   (stable key).
    4.  Re-chunk the content using section-aware chunker.
    5.  Insert new chunks with full metadata.
    6.  Commit.
    """
    if isinstance(doc, str):
        if not frappe.db.exists("System Notifications", doc):
            return
        doc = frappe.get_doc("System Notifications", doc)

    if not hasattr(doc, "doctype") or doc.doctype != "System Notifications":
        return

    is_policy    = (doc.get("notification_type") or "").strip().lower() == "policy"
    is_published = bool(doc.get("is_published"))

    # ── Not a published policy → clean up and exit ─────────────────────────
    if not is_policy or not is_published:
        delete_policy_notification_chunks(doc)
        return

    # ── Extract content ────────────────────────────────────────────────────
    notif_body_html  = doc.get("notifiction") or ""
    body_text        = clean_text_content(notif_body_html)
    attachment_url   = doc.get("policy_document") or ""
    attachment_text  = extract_text_from_file_path_or_url(attachment_url) if attachment_url else ""

    subject = (doc.get("subject") or doc.name).strip()
    version = (doc.get("version") or "1.0").strip()

    # Build combined content (skip the "[Policy: ...]" prefix — it biases retrieval)
    content_parts = []
    if body_text:
        content_parts.append(body_text)
    if attachment_text:
        content_parts.append(f"--- Attachment ---\n{attachment_text}")

    combined_text = "\n\n".join(content_parts).strip()

    if not combined_text:
        delete_policy_notification_chunks(doc)
        return

    # ── Content hash for idempotency check ────────────────────────────────
    content_hash = hashlib.md5(combined_text.encode("utf-8")).hexdigest()
    existing_chunk_count = frappe.db.count(
        "AI Workplace Knowledge Chunk",
        {"source_id": doc.name, "source_type": "System Notification"},
    )
    # Check if content changed since last indexing
    if existing_chunk_count > 0:
        first_chunk = frappe.db.get_value(
            "AI Workplace Knowledge Chunk",
            {"source_id": doc.name, "source_type": "System Notification"},
            "content_hash",
        )
        # If the first chunk's stored doc-level hash matches, nothing changed
        doc_level_hash = hashlib.md5(
            f"{combined_text}|{version}".encode("utf-8")
        ).hexdigest()
        stored_doc_hash = frappe.db.get_value(
            "AI Workplace Knowledge Chunk",
            {"source_id": doc.name, "source_type": "System Notification"},
            "policy_version",  # We repurpose this field temporarily below — no, use a dedicated approach
        )
        # Use access_level to store doc-level hash check marker
        hash_marker = f"sysnotif:{doc.name}|hash:{content_hash}|ver:{version}"
        existing_marker = frappe.db.get_value(
            "AI Workplace Knowledge Chunk",
            {"source_id": doc.name, "source_type": "System Notification"},
            "access_level",
        )
        if existing_marker == hash_marker:
            # Content is identical — no-op (idempotent)
            return

    # ── Delete old chunks ──────────────────────────────────────────────────
    delete_policy_notification_chunks(doc)

    # ── Chunk ──────────────────────────────────────────────────────────────
    raw_chunks = build_section_chunks(combined_text, doc_name=subject)
    if not raw_chunks:
        return

    _ensure_policy_knowledge_source_exists()

    from ai_workplace.ai.indexer import generate_embedding, _get_setting

    emb_model    = _get_setting("embedding_model", "text-embedding-3-small")
    source_date  = (
        doc.get("last_updated_on")
        or doc.get("published_from")
        or frappe.utils.today()
    )
    effective_date = doc.get("published_from") or doc.get("last_updated_on") or frappe.utils.today()

    hash_marker = f"sysnotif:{doc.name}|hash:{content_hash}|ver:{version}"

    # Determine policy scope from System Notification 'type' field
    # Values: '' / 'All' / 'HO only' / 'Project Base'
    notification_scope = _normalize_notification_scope(doc.get("type") or "")

    errors = []
    for idx, chunk_info in enumerate(raw_chunks):
        text     = chunk_info["text"]
        c_hash   = hashlib.md5(text.encode("utf-8")).hexdigest()

        try:
            vec      = generate_embedding(text)
            emb_json = json.dumps(vec) if vec else ""
        except Exception as exc:
            frappe.logger("ai_workplace").error(
                f"Embedding failed for chunk {idx} of {doc.name}: {exc}"
            )
            vec      = []
            emb_json = ""
            errors.append(str(exc))

        try:
            chunk                   = frappe.new_doc("AI Workplace Knowledge Chunk")
            chunk.knowledge_source  = "policies"
            chunk.chunk_index       = idx
            chunk.chunk_text        = text
            chunk.content_hash      = c_hash
            chunk.document_name     = subject
            chunk.document_type     = "System Notifications"
            # Stable source tracking
            chunk.source_type       = "System Notification"
            chunk.source_id         = doc.name
            # Section metadata
            chunk.section           = chunk_info.get("section") or subject
            # Date metadata
            chunk.policy_version    = version
            chunk.effective_date    = effective_date
            chunk.source_date       = source_date
            # Scope filtering — maps to System Notification 'type'
            chunk.target_employment_type = notification_scope
            # Legacy access_level carries idempotency hash marker on first chunk
            chunk.access_level      = hash_marker if idx == 0 else f"sysnotif:{doc.name}"
            # Embedding
            chunk.embedding_model       = emb_model
            chunk.embedding_dimensions  = len(vec) if vec else 128
            chunk.embedding_json        = emb_json

            chunk.insert(ignore_permissions=True)
        except Exception as exc:
            frappe.logger("ai_workplace").error(
                f"Failed to insert knowledge chunk {idx} for {doc.name}: {exc}"
            )
            errors.append(str(exc))

    if errors:
        frappe.log_error(
            title=f"Policy chunk indexing partial failure: {doc.name}",
            message="\n".join(errors),
        )

    frappe.db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Scope normalisation
# ──────────────────────────────────────────────────────────────────────────────

# Maps System Notification 'type' select field values to the canonical scope
# token stored in AI Workplace Knowledge Chunk.target_employment_type.
#
# Search side reads: "", "All", "HO", "Project"
_SCOPE_NORMALISATION: dict[str, str] = {
    "": "All",
    "all": "All",
    "ho only": "HO",
    "project base": "Project",
    "project based": "Project",
    "project": "Project",
    "ho": "HO",
}


def _normalize_notification_scope(raw_type: str) -> str:
    """
    Map the System Notification ``type`` field value to the canonical
    scope token stored on the knowledge chunk.

    >>> _normalize_notification_scope('HO only')  → 'HO'
    >>> _normalize_notification_scope('Project Base')  → 'Project'
    >>> _normalize_notification_scope('All')  → 'All'
    >>> _normalize_notification_scope('')  → 'All'
    """
    return _SCOPE_NORMALISATION.get((raw_type or "").strip().lower(), "All")


# ──────────────────────────────────────────────────────────────────────────────
# Deletion / cleanup
# ──────────────────────────────────────────────────────────────────────────────

def delete_policy_notification_chunks(doc, method=None) -> None:
    """
    Delete all Knowledge Chunks for a System Notifications document.
    Uses `source_id` (primary) with `access_level` as a fallback for older chunks
    that pre-date the source_id field.
    """
    doc_name = doc.get("name") if hasattr(doc, "get") else str(doc)
    if not doc_name:
        return

    # Primary deletion path — stable source_id
    frappe.db.delete(
        "AI Workplace Knowledge Chunk",
        {
            "source_type": "System Notification",
            "source_id":   doc_name,
        },
    )

    # Legacy fallback — chunks created before source_id existed
    frappe.db.delete(
        "AI Workplace Knowledge Chunk",
        {
            "document_type": "System Notifications",
            "access_level":  ["like", f"sysnotif:{doc_name}%"],
        },
    )

    # Also clean by document_name if subject is available (oldest legacy path)
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


# ──────────────────────────────────────────────────────────────────────────────
# Bulk sync / maintenance
# ──────────────────────────────────────────────────────────────────────────────

def sync_all_policy_notifications() -> dict[str, int]:
    """
    Sync all published System Notifications of type 'Policy' and remove legacy sources.
    Safe to call multiple times (idempotent per notification).
    """
    notifications = frappe.db.get_all(
        "System Notifications",
        filters={"notification_type": "Policy", "is_published": 1},
        fields=["name"],
    )

    synced_count = 0
    for n in notifications:
        try:
            doc = frappe.get_doc("System Notifications", n.name)
            sync_policy_notification_to_chunks(doc)
            synced_count += 1
        except Exception:
            frappe.log_error(
                title=f"Policy sync failed: {n.name}",
                message=frappe.get_traceback(),
            )

    _cleanup_legacy_policy_knowledge_sources()
    return {"synced": synced_count}


def _ensure_policy_knowledge_source_exists() -> None:
    if not frappe.db.exists("AI Workplace Knowledge Source", "policies"):
        source             = frappe.new_doc("AI Workplace Knowledge Source")
        source.source_name = "policies"
        source.source_type = "Policy"
        source.description = "System Policy Notifications (auto-indexed)"
        source.is_active   = 1
        source.insert(ignore_permissions=True)
    else:
        frappe.db.set_value(
            "AI Workplace Knowledge Source", "policies", "is_active", 1, update_modified=False
        )


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
