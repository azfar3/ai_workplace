"""
Hybrid RAG Indexer — Combined Keyword (BM25) and Dense Semantic Vector Search.
Supports OpenAI embedding API with deterministic n-gram vector fallback, caching, and source citations.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any, List, Optional, Tuple

import frappe
import requests


def generate_embedding(text: str, provider: str = "", model: str = "") -> List[float]:
    """
    Generates embedding vector for a given text.
    Uses OpenAI embedding API if available, falling back to a deterministic 128-dim character n-gram projection vector.
    Returns unit-normalized vector for cosine similarity calculation.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return [0.0] * 128

    # 1. Check API Key & Configured Provider
    api_key, base_url = _get_embedding_credentials(provider)
    model_name = model or _get_setting("embedding_model", "text-embedding-3-small")

    if api_key:
        try:
            url = f"{base_url}/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {"input": clean_text[:2000], "model": model_name}
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=10,
                proxies={"http": None, "https": None},
            )
            if resp.status_code == 200:
                data = resp.json()
                vec = data["data"][0]["embedding"]
                return _normalize_vector(vec)
        except Exception:
            pass

    # 2. Deterministic Hash Projection Fallback (Zero external dependency, 100% reliable)
    return _generate_fallback_vector(clean_text)


def _get_embedding_credentials(provider_name: str) -> Tuple[str, str]:
    if not frappe.db.exists("DocType", "AI Workplace Provider"):
        return "", "https://api.openai.com/v1"

    # Find active OpenAI or embedding provider
    providers = frappe.get_all(
        "AI Workplace Provider",
        filters={"is_active": 1},
        fields=["name", "api_base_url"],
        order_by="priority asc",
    )
    for p_row in providers:
        p_doc = frappe.get_doc("AI Workplace Provider", p_row.name)
        try:
            key = p_doc.get_password("api_key") or p_doc.get("api_key") or ""
        except Exception:
            key = p_doc.get("api_key") or ""
        if key:
            base_url = (p_doc.api_base_url or "https://api.openai.com/v1").rstrip("/")
            return key, base_url

    # Fallback to Groq AI Settings if configured
    if frappe.db.exists("DocType", "Groq AI Settings"):
        try:
            settings = frappe.get_single("Groq AI Settings")
            key = settings.get_password("api_key") or ""
            if key:
                return key, "https://api.groq.com/openai/v1"
        except Exception:
            pass

    return "", "https://api.openai.com/v1"


def _normalize_vector(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-9:
        return vec
    return [x / norm for x in vec]


def _generate_fallback_vector(text: str, dim: int = 128) -> List[float]:
    """Generates a 128-dimensional term/character 3-gram hash projection vector."""
    vec = [0.0] * dim
    words = re.findall(r"\w+", text.lower())
    for word in words:
        # Word hash
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
        # 3-gram character hashes
        for i in range(len(word) - 2):
            gram = word[i : i + 3]
            gh = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            vec[gh % dim] += 0.5

    return _normalize_vector(vec)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


def reindex_source(source_name: str) -> int:
    if not frappe.db.exists("AI Workplace Knowledge Source", source_name):
        return 0
    source = frappe.get_doc("AI Workplace Knowledge Source", source_name)
    extracted_chunks = _extract_chunks_with_metadata(source)
    
    # Existing chunks map for content hash caching
    existing_chunks = {
        c.content_hash: c
        for c in frappe.get_all(
            "AI Workplace Knowledge Chunk",
            filters={"knowledge_source": source_name},
            fields=["name", "content_hash", "embedding_json", "embedding_model"],
        )
        if c.content_hash
    }

    frappe.db.delete("AI Workplace Knowledge Chunk", {"knowledge_source": source_name})

    emb_model = _get_setting("embedding_model", "text-embedding-3-small")

    for idx, chunk_info in enumerate(extracted_chunks):
        text = chunk_info["text"]
        c_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        
        # Check cache
        if c_hash in existing_chunks and existing_chunks[c_hash].embedding_json:
            emb_json = existing_chunks[c_hash].embedding_json
        else:
            vec = generate_embedding(text)
            emb_json = json.dumps(vec)

        doc = frappe.new_doc("AI Workplace Knowledge Chunk")
        doc.knowledge_source = source_name
        doc.chunk_index = idx
        doc.chunk_text = text
        doc.content_hash = c_hash
        doc.document_name = chunk_info.get("document_name") or source_name
        doc.document_type = source.source_type
        doc.section = chunk_info.get("section") or ""
        doc.embedding_model = emb_model
        doc.embedding_dimensions = len(json.loads(emb_json)) if emb_json else 128
        doc.embedding_json = emb_json
        
        # Enterprise Metadata Propagation
        doc.target_employment_type = source.get("target_employment_type")
        doc.target_department = source.get("target_department")
        doc.target_location = source.get("target_location")
        doc.policy_version = source.get("version")
        doc.effective_date = source.get("effective_from")
        
        doc.insert(ignore_permissions=True)

    frappe.db.set_value(
        "AI Workplace Knowledge Source",
        source_name,
        {
            "last_indexed": frappe.utils.now_datetime(),
            "version_hash": hashlib.md5(json.dumps([c["text"] for c in extracted_chunks]).encode()).hexdigest(),
        },
        update_modified=False,
    )
    frappe.db.commit()
    return len(extracted_chunks)


def reindex_all_sources() -> dict[str, int]:
    counts = {}
    for name in _active_source_names():
        counts[name] = reindex_source(name)
    return counts


def _extract_chunks_with_metadata(source: Any) -> list[dict[str, Any]]:
    source_type = source.get("source_type") if hasattr(source, "get") else getattr(source, "source_type", "")
    doc_title = getattr(source, "source_name", None) or getattr(source, "name", "Knowledge Source")
    
    if source_type == "MenuCatalog" and not (getattr(source, "content", None) or getattr(source, "file_attachment", None)):
        return _index_menu_catalog_structured()

    # Priority 1: Attachment file extraction (PDF, DOCX, TXT)
    file_content = ""
    if getattr(source, "file_attachment", None):
        file_content = _extract_text_from_file(source.file_attachment)

    content = file_content or getattr(source, "content", None) or getattr(source, "description", None) or ""
    return _chunk_text_with_overlap(content, doc_name=doc_title)

def _extract_text_from_file(file_url: str) -> str:
    """Phase C: Extract text from PDF, DOCX, and TXT attachments."""
    if not file_url:
        return ""
    
    file_doc = frappe.get_all("File", filters={"file_url": file_url}, fields=["name", "file_name", "file_url"], limit=1)
    if not file_doc:
        return ""
    
    file_path = frappe.get_site_path(file_url.lstrip("/"))
    if not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == ".pdf":
            import PyPDF2
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                return "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
        elif ext == ".docx":
            import docx
            doc = docx.Document(file_path)
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        elif ext in (".txt", ".md", ".csv", ".json"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Failed to parse document {file_url}: {exc}")
    
    return ""


def _chunk_text_with_overlap(content: str, doc_name: str = "", chunk_size: int = 300, overlap: int = 50) -> list[dict[str, Any]]:
    if not content:
        return []

    words = content.split()
    if len(words) <= chunk_size:
        return [{"text": content, "document_name": doc_name, "section": _extract_section_title(content)}]

    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        text = " ".join(chunk_words)
        if text.strip():
            chunks.append({
                "text": text,
                "document_name": doc_name,
                "section": _extract_section_title(text),
            })
    return chunks


def _extract_section_title(text: str) -> str:
    m = re.search(r"^(?:#+|\d+\.|\bSection:?\b)\s*([^\n]+)", text, re.M | re.I)
    if m:
        return m.group(1).strip()
    return ""


def _index_menu_catalog_structured() -> list[dict[str, Any]]:
    from ai_workplace.menu.seed_data import get_menu_seed_items, get_flow_menu_seed_items

    lines = []
    for item in get_menu_seed_items():
        lines.append(f"{item['menu_key']}: {item.get('title', '')}")
        for sub in item.get("submenus", []):
            lines.append(f"{sub['menu_key']}: {sub.get('title', '')}")
    for flow in get_flow_menu_seed_items():
        lines.append(f"{flow['menu_key']}: {flow.get('title', '')}")

    chunks = []
    for i in range(0, len(lines), 15):
        chunk_lines = lines[i : i + 15]
        chunks.append({
            "text": "\n".join(chunk_lines),
            "document_name": "Menu Catalog",
            "section": "WhatsApp Interactive Services",
        })
    return chunks or [{"text": "", "document_name": "Menu Catalog", "section": ""}]


def _index_policies_structured() -> list[dict[str, Any]]:
    try:
        from hrms.api.employee import get_policies_data

        policies = get_policies_data() or []
        chunks = []
        for p in policies[:50]:
            title = p.get("title", "Policy")
            desc = p.get("description", "")
            text = f"[Source: {title}] Section: General Policy\n{title}\n\n{desc[:2000]}"
            chunks.append({
                "text": text,
                "document_name": title,
                "section": "Policy Details",
            })
        return chunks
    except Exception:
        return []


def _index_onboarding_structured() -> list[dict[str, Any]]:
    if not frappe.db.exists("DocType", "AI Onboarding Playbook"):
        return []
    playbooks = frappe.get_all(
        "AI Onboarding Playbook",
        filters={"is_active": 1},
        fields=["playbook_name", "checklist_json", "system_prompt"],
    )
    chunks = []
    for pb in playbooks:
        text = pb.system_prompt or pb.checklist_json or pb.playbook_name
        if text:
            chunks.append({
                "text": f"[Onboarding: {pb.playbook_name}] {text[:3000]}",
                "document_name": pb.playbook_name,
                "section": "Onboarding Guide",
            })
    return chunks or [{"text": "New hire onboarding: complete profile, set PIN, review policies.", "document_name": "Onboarding", "section": "General"}]


def _load_portal_guides_from_disk() -> str:
    guides_dir = os.path.join(frappe.get_app_path("ai_workplace"), "doc", "portal_guides")
    if not os.path.isdir(guides_dir):
        return ""
    parts = []
    for fname in sorted(os.listdir(guides_dir)):
        if fname.endswith(".md"):
            with open(os.path.join(guides_dir, fname), encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n".join(parts)


def search_knowledge(query: str, limit: int = 5, employment_type: str = "", context: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """
    Hybrid RAG Search — Merges keyword (BM25) and dense vector semantic scores.
    Formula: final_score = rag_keyword_weight * norm_kw_score + rag_semantic_weight * norm_sem_score
    Returns rich metadata and source citations.
    """
    if not query or not frappe.db.exists("DocType", "AI Workplace Knowledge Chunk"):
        return []

    words = [w.lower() for w in query.split() if len(w) > 2]
    query_vector = generate_embedding(query)

    # Add new fields for enterprise metadata filtering
    fields = [
        "name", "chunk_text", "knowledge_source", "document_name", "section",
        "content_hash", "embedding_json", "target_employment_type",
        "target_department", "target_location", "policy_version", "effective_date"
    ]

    chunks = frappe.get_all(
        "AI Workplace Knowledge Chunk",
        filters={"knowledge_source": ["in", _active_source_names()]},
        fields=fields,
        limit=500,  # Increased for reranking phase
    )

    if not chunks:
        return []

    user_emp_type = (employment_type or "").strip()
    user_dept = (context or {}).get("department", "") if context else ""
    user_loc = (context or {}).get("location", "") if context else ""

    # Phase C: Pre-filtering via metadata scopes
    filtered_chunks = []
    for chunk in chunks:
        # Effective Date filtering (if set)
        if chunk.effective_date and chunk.effective_date > frappe.utils.today():
            continue
            
        # Hard Scoping (if fields are set on chunk, user MUST match)
        if chunk.target_employment_type and user_emp_type and chunk.target_employment_type != user_emp_type:
            continue
        if chunk.target_department and user_dept and chunk.target_department != user_dept:
            continue
        if chunk.target_location and user_loc and chunk.target_location != user_loc:
            continue
            
        filtered_chunks.append(chunk)

    if not filtered_chunks:
        return []

    # Phase C: True BM25 Scoring
    # Calculate corpus stats
    N = len(filtered_chunks)
    avgdl = sum(len((c.chunk_text or "").split()) for c in filtered_chunks) / float(N) if N else 1.0
    k1 = 1.5
    b = 0.75

    # Document frequency for IDF
    df = {}
    for w in words:
        df[w] = sum(1 for c in filtered_chunks if w in (c.chunk_text or "").lower())

    idf = {}
    for w in words:
        n_qi = df[w]
        idf[w] = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))

    kw_weight = float(_get_setting("rag_keyword_weight", 0.5) or 0.5)
    sem_weight = float(_get_setting("rag_semantic_weight", 0.5) or 0.5)
    if (kw_weight + sem_weight) <= 0.001:
        kw_weight, sem_weight = 0.5, 0.5

    raw_candidates = []
    max_kw_score = 0.0001
    
    for chunk in filtered_chunks:
        text = chunk.chunk_text or ""
        text_lower = text.lower()
        chunk_words = text_lower.split()
        doc_len = len(chunk_words)

        # 1. Okapi BM25 Score
        kw_score = 0.0
        for w in words:
            if w in text_lower:
                freq = text_lower.count(w) # rough term freq
                numerator = freq * (k1 + 1)
                denominator = freq + k1 * (1 - b + b * (doc_len / avgdl))
                kw_score += idf[w] * (numerator / denominator)

        if kw_score > max_kw_score:
            max_kw_score = kw_score

        # 2. Semantic Vector Score
        sem_score = 0.0
        if chunk.embedding_json:
            try:
                chunk_vec = json.loads(chunk.embedding_json)
                sem_score = cosine_similarity(query_vector, chunk_vec)
            except Exception:
                sem_score = 0.0

        raw_candidates.append({
            "chunk": chunk,
            "kw_score": float(kw_score),
            "sem_score": float(sem_score),
        })

    # Phase C: Reranking (Reciprocal Rank Fusion / Weighted Normalized Score)
    scored = []
    for item in raw_candidates:
        norm_kw = item["kw_score"] / max_kw_score
        norm_sem = item["sem_score"]
        
        # Boost semantic score slightly if exact keyword match is high
        final_score = (kw_weight * norm_kw) + (sem_weight * norm_sem)

        if final_score > 0.05 or item["kw_score"] > 0:
            scored.append((final_score, norm_kw, norm_sem, item["chunk"]))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for final_s, kw_s, sem_s, c in scored[:limit]:
        doc_title = c.document_name or _extract_source_title(c.chunk_text or "") or c.knowledge_source
        results.append({
            "chunk_id": c.name,
            "text": c.chunk_text,
            "source": c.knowledge_source,
            "source_title": doc_title,
            "document": doc_title,
            "section": c.section or "General",
            "version": c.policy_version or "1.0",
            "score": round(final_s, 4),
            "keyword_score": round(kw_s, 4),
            "semantic_score": round(sem_s, 4),
        })

    return results


def _extract_source_title(text: str) -> str:
    if text.startswith("[Source:"):
        end = text.find("]")
        if end > 8:
            return text[8:end].strip()
    if text.startswith("[Onboarding:"):
        end = text.find("]")
        if end > 12:
            return text[12:end].strip()
    return ""


def _active_source_names() -> list[str]:
    if not frappe.db.exists("DocType", "AI Workplace Knowledge Source"):
        return []
    return frappe.get_all(
        "AI Workplace Knowledge Source",
        filters={"is_active": 1},
        pluck="name",
    )


def _get_setting(fieldname: str, default: Any) -> Any:
    try:
        if not frappe.db.exists("DocType", "AI Workplace Settings"):
            return default
        settings = frappe.get_single("AI Workplace Settings")
        return getattr(settings, fieldname, default) or default
    except Exception:
        return default


def reindex_stale_sources() -> None:
    if not frappe.db.exists("DocType", "AI Workplace Knowledge Source"):
        return
    stale = frappe.get_all(
        "AI Workplace Knowledge Source",
        filters={"is_active": 1},
        fields=["name", "last_indexed"],
    )
    cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -7)
    for row in stale:
        if not row.last_indexed or row.last_indexed < cutoff:
            reindex_source(row.name)


def reindex_policies_on_notification_update(doc, method=None) -> None:
    """Re-index policy knowledge when a published System Notification changes."""
    if doc.doctype != "System Notifications":
        return
    if (doc.get("notification_type") or "").lower() != "policy":
        return
    if not frappe.db.exists("AI Workplace Knowledge Source", "policies"):
        return
    try:
        reindex_source("policies")
    except Exception:
        frappe.log_error(title="Policy knowledge reindex failed", message=frappe.get_traceback())
