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


# Providers that do NOT support the OpenAI /embeddings endpoint.
# We skip them entirely and rely on the deterministic fallback vector.
_EMBEDDING_UNSUPPORTED_HOSTS = (
    "api.groq.com",
    "groq.com",
    "api.mistral.ai",
    "api.anthropic.com",
)


def _get_embedding_credentials(provider_name: str) -> Tuple[str, str]:
    if not frappe.db.exists("DocType", "AI Workplace Provider"):
        return "", ""

    # Find an active provider whose base URL is a *real* embeddings endpoint
    providers = frappe.get_all(
        "AI Workplace Provider",
        filters={"is_active": 1},
        fields=["name", "api_base_url"],
        order_by="priority asc",
    )
    for p_row in providers:
        base_url = (p_row.get("api_base_url") or "https://api.openai.com/v1").rstrip("/")
        # Skip providers that are known NOT to serve embeddings
        if any(host in base_url for host in _EMBEDDING_UNSUPPORTED_HOSTS):
            continue
        p_doc = frappe.get_doc("AI Workplace Provider", p_row.name)
        try:
            key = p_doc.get_password("api_key") or p_doc.get("api_key") or ""
        except Exception:
            key = p_doc.get("api_key") or ""
        if key:
            return key, base_url

    # No suitable embedding provider found — use deterministic fallback
    return "", ""


def _normalize_vector(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-9:
        return vec
    return [x / norm for x in vec]


def _generate_fallback_vector(text: str, dim: int = 512) -> List[float]:
    """
    512-dimensional hash-projection vector using unigrams + bigrams + 3-grams.

    Improvements over the previous 128-dim version:
    • Higher dimensionality reduces hash collisions significantly.
    • Bigrams capture adjacent-word context ("dual job", "work home").
    • Term-frequency capping (max 3) prevents a single frequent word from
      drowning out semantically important but rarer terms.
    • Character 3-grams still handle morphological similarity.
    """
    vec = [0.0] * dim
    words = re.findall(r"\w+", text.lower())

    # Per-term caps to avoid domination by high-frequency terms
    term_count: dict = {}

    for i, word in enumerate(words):
        if len(word) < 2:
            continue

        # --- Unigram ---
        term_count[word] = term_count.get(word, 0) + 1
        if term_count[word] <= 3:  # TF cap
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            vec[h % dim] += 1.0

        # --- Bigram (current + next word) ---
        if i + 1 < len(words):
            bigram = f"{word}_{words[i + 1]}"
            bh = int(hashlib.md5(bigram.encode("utf-8")).hexdigest(), 16)
            vec[bh % dim] += 0.8

        # --- Character 3-grams ---
        for j in range(len(word) - 2):
            gram = word[j : j + 3]
            gh = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            vec[gh % dim] += 0.3

    return _normalize_vector(vec)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2:
        return 0.0
    # Tolerate dimension mismatches (e.g. old 128-dim stored chunks vs new
    # 512-dim query vectors during a reindex window): compare over shared prefix.
    min_len = min(len(v1), len(v2))
    if min_len == 0:
        return 0.0
    a, b = v1[:min_len], v2[:min_len]
    # Re-normalise both slices so the dot product is a valid cosine estimate
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
    dot = sum(ai * bi for ai, bi in zip(a, b))
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


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

    frappe.db.delete(
        "AI Workplace Knowledge Chunk", 
        {
            "knowledge_source": source_name,
            "document_type": ["!=", "System Notifications"]
        }
    )

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
        # Stable source tracking
        doc.source_type = "Knowledge Source"
        doc.source_id   = source_name
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
        doc.source_date    = source.get("effective_from") or source.get("last_indexed")
        
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
    """
    Section-aware chunker.  Tries to split on Markdown / numeric headings first
    so that each section stays in its own chunk(s).  Falls back to word-count
    sliding-window only when no headings are detected.
    """
    if not content:
        return []

    # ── 1. Try heading-aware split ────────────────────────────────────────────
    # Reuse the same section-aware logic used by policy_notifications so all
    # document types benefit from heading isolation.
    try:
        from ai_workplace.services.policy_notifications import build_section_chunks
        section_chunks = build_section_chunks(content, doc_name)
        if section_chunks and len(section_chunks) > 1:
            # build_section_chunks already returns {text, section, document_name}
            return section_chunks
    except Exception:
        pass  # Fall through to word-count fallback

    # ── 2. Short-document fast path ───────────────────────────────────────────
    words = content.split()
    if len(words) <= chunk_size:
        return [{"text": content, "document_name": doc_name, "section": _extract_section_title(content)}]

    # ── 3. Word-count sliding-window fallback ─────────────────────────────────
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


# ── Stop-word list for BM25 query cleaning ────────────────────────────────────
# These terms appear in almost every chunk in this knowledge base (company name,
# policy boilerplate, English connectives) and produce noisy IDF scores.  They
# are removed from the BM25 token list only — the full original query is still
# used for semantic embedding.
_BM25_STOP_WORDS = frozenset({
    # English function words
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "has",
    "was", "who", "had", "her", "his", "she", "him", "its", "our", "out",
    "one", "two", "any", "will", "from", "this", "that", "with", "they",
    "have", "been", "your", "what", "when", "where", "how", "which", "into",
    "each", "more", "also", "may", "shall", "must", "does", "did", "such",
    "than", "then", "them", "been", "their", "there", "these", "those",
    # Domain-ubiquitous terms (present in virtually every chunk → IDF ≈ 0)
    "micromerger", "policy", "policies", "company", "pvt", "ltd", "staff",
    "employee", "employees", "management", "human", "resources",
})


def _clean_query_tokens(query: str) -> list[str]:
    """Tokenise query for BM25: lowercase, strip punctuation, drop stop-words."""
    # Strip leading/trailing punctuation from each token
    tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", query.lower())
    return [
        t for t in tokens
        if len(t) > 2 and t not in _BM25_STOP_WORDS
    ]


def search_knowledge(query: str, limit: int = 5, employment_type: str = "", context: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """
    Hybrid RAG Search — Merges keyword (BM25) and dense vector semantic scores.
    Formula: final_score = rag_keyword_weight * norm_kw_score + rag_semantic_weight * norm_sem_score
             + freshness_boost (mild, configurable, relevance-first)
    Returns rich metadata and source citations for the LLM to reason over.
    """
    if not query or not frappe.db.exists("DocType", "AI Workplace Knowledge Chunk"):
        return []

    # BM25 uses cleaned, stop-word-free tokens; embedding uses the full raw query
    words = _clean_query_tokens(query)
    query_vector = generate_embedding(query)

    fields = [
        "name", "chunk_text", "knowledge_source", "document_name", "section",
        "content_hash", "embedding_json", "target_employment_type",
        "target_department", "target_location", "policy_version", "effective_date",
        "source_type", "source_id", "source_date",
    ]

    chunks = frappe.get_all(
        "AI Workplace Knowledge Chunk",
        filters={"knowledge_source": ["in", _active_source_names()]},
        fields=fields,
        limit=500,
    )

    if not chunks:
        return []

    # Exclude menu catalog chunks — they contain navigation labels ("job", "work",
    # "home") that score well on policy queries but contain zero policy content.
    chunks = [c for c in chunks if c.get("knowledge_source") != "menu_catalog"]

    user_emp_type = (employment_type or "").strip()
    user_dept = (context or {}).get("department", "") if context else ""
    user_loc  = (context or {}).get("location", "") if context else ""
    today_str = frappe.utils.today()

    # Build the allowed scope set from context.policy_scope
    # Canonical chunk scope values: "All", "HO", "Project"
    # Canonical employee scope values (from resolver): "HO", "Project", "All"
    #
    # Inclusive rule:
    #   employee scope "HO"      → sees chunks scoped "All" or "HO"
    #   employee scope "Project" → sees chunks scoped "All" or "Project"
    #   employee scope "All"     → sees chunks scoped "All" only
    #   (no employee / guest)    → sees only "All" chunks
    _employee_policy_scope = (context or {}).get("policy_scope", "") if context else ""
    if _employee_policy_scope == "HO":
        _allowed_chunk_scopes: set[str] = {"All", "HO", ""}
    elif _employee_policy_scope == "Project":
        _allowed_chunk_scopes = {"All", "Project", ""}
    else:
        # "All" scope employees or guests get universal policies only
        _allowed_chunk_scopes = {"All", ""}

    # Phase C: Pre-filtering via metadata scopes
    filtered_chunks = []
    for chunk in chunks:
        # Effective Date filtering (if set, chunk must be effective already)
        if chunk.effective_date and frappe.utils.getdate(chunk.effective_date) > frappe.utils.getdate(today_str):
            continue

        # Policy Scope filtering — inclusive allowed-scope check
        chunk_scope = (chunk.target_employment_type or "").strip()
        if chunk_scope and chunk_scope not in _allowed_chunk_scopes:
            continue

        # Hard Scoping for department / location (unchanged)
        if chunk.target_department and user_dept and chunk.target_department != user_dept:
            continue
        if chunk.target_location and user_loc and chunk.target_location != user_loc:
            continue

        filtered_chunks.append(chunk)

    if not filtered_chunks:
        return []

    # BM25 Scoring
    N    = len(filtered_chunks)
    avgdl = sum(len((c.chunk_text or "").split()) for c in filtered_chunks) / float(N) if N else 1.0
    k1, b = 1.5, 0.75

    df = {}
    for w in words:
        # Use whole-word check in df to keep IDF consistent with the scoring loop
        df[w] = sum(1 for c in filtered_chunks
                    if any(cw == w or cw.rstrip(".,;:!?'\")") == w
                       for cw in (c.chunk_text or "").lower().split()))

    idf = {}
    for w in words:
        n_qi = df[w]
        idf[w] = math.log(1 + (N - n_qi + 0.5) / (n_qi + 0.5))

    kw_weight  = float(_get_setting("rag_keyword_weight", 0.5) or 0.5)
    sem_weight = float(_get_setting("rag_semantic_weight", 0.5) or 0.5)
    if (kw_weight + sem_weight) <= 0.001:
        kw_weight, sem_weight = 0.5, 0.5

    # Freshness boost — mild (0.05 max) so relevance always dominates
    freshness_weight = float(_get_setting("rag_freshness_weight", 0.05) or 0.05)

    raw_candidates  = []
    max_kw_score    = 0.0001

    # Pre-compute min/max source_date for normalisation
    source_dates = []
    for chunk in filtered_chunks:
        sd = chunk.get("source_date") or chunk.get("effective_date")
        if sd:
            try:
                source_dates.append(frappe.utils.getdate(sd))
            except Exception:
                pass
    min_date = min(source_dates) if source_dates else None
    max_date = max(source_dates) if source_dates else None

    for chunk in filtered_chunks:
        text       = chunk.chunk_text or ""
        text_lower = text.lower()
        chunk_words = text_lower.split()
        doc_len    = len(chunk_words)

        # Okapi BM25 Score — use whole-word boundary matching to avoid
        # substring false positives (e.g. "job" matching inside "subject").
        kw_score = 0.0
        for w in words:
            # Count whole-word occurrences using a simple split-based approach
            freq = sum(1 for cw in chunk_words if cw == w or cw.rstrip(".,;:!?'\")") == w)
            if freq > 0:
                numerator   = freq * (k1 + 1)
                denominator = freq + k1 * (1 - b + b * (doc_len / avgdl))
                kw_score   += idf[w] * (numerator / denominator)

        if kw_score > max_kw_score:
            max_kw_score = kw_score

        # Semantic Vector Score
        sem_score = 0.0
        if chunk.embedding_json:
            try:
                chunk_vec = json.loads(chunk.embedding_json)
                sem_score = cosine_similarity(query_vector, chunk_vec)
            except Exception:
                sem_score = 0.0

        # Freshness score (normalised 0-1, older=0, newest=1)
        freshness_score = 0.0
        if min_date and max_date and min_date != max_date:
            sd = chunk.get("source_date") or chunk.get("effective_date")
            if sd:
                try:
                    chunk_date = frappe.utils.getdate(sd)
                    date_range = (max_date - min_date).days or 1
                    freshness_score = (chunk_date - min_date).days / date_range
                except Exception:
                    freshness_score = 0.0

        raw_candidates.append({
            "chunk":          chunk,
            "kw_score":       float(kw_score),
            "sem_score":      float(sem_score),
            "freshness_score": float(freshness_score),
        })

    # Reranking: Relevance-first, then freshness
    scored = []
    for item in raw_candidates:
        norm_kw  = item["kw_score"] / max_kw_score
        norm_sem = item["sem_score"]
        fresh    = item["freshness_score"]

        final_score = (kw_weight * norm_kw) + (sem_weight * norm_sem) + (freshness_weight * fresh)

        # Require a meaningful combined score — avoids surfacing chunks that
        # only matched a single ubiquitous word after stop-word stripping.
        # A chunk must score > 0.15 combined OR have a keyword score > 0.1
        # (i.e., genuine keyword overlap, not just a faint semantic bleed).
        if final_score > 0.15 or (item["kw_score"] > 0 and norm_kw > 0.1):
            scored.append((final_score, norm_kw, norm_sem, fresh, item["chunk"]))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for final_s, kw_s, sem_s, fresh_s, c in scored[:limit]:
        doc_title = c.document_name or _extract_source_title(c.chunk_text or "") or c.knowledge_source

        # Build source_date string for LLM
        s_date = None
        raw_sd = c.get("source_date") or c.get("effective_date")
        if raw_sd:
            try:
                s_date = str(frappe.utils.getdate(raw_sd))
            except Exception:
                s_date = str(raw_sd)

        results.append({
            "chunk_id":       c.name,
            "text":           c.chunk_text,
            "source":         c.knowledge_source,
            "source_title":   doc_title,
            "source_type":    c.get("source_type") or "Knowledge Source",
            "source_id":      c.get("source_id") or c.knowledge_source,
            "document":       doc_title,
            "section":        c.section or "General",
            "version":        c.policy_version or "1.0",
            "source_date":    s_date,
            "effective_date": str(c.effective_date) if c.effective_date else None,
            "score":          round(final_s, 4),
            "keyword_score":  round(kw_s, 4),
            "semantic_score": round(sem_s, 4),
            "freshness_score": round(fresh_s, 4),
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
    from ai_workplace.services.policy_notifications import sync_policy_notification_to_chunks
    try:
        sync_policy_notification_to_chunks(doc, method)
    except Exception:
        frappe.log_error(title="Policy knowledge reindex failed", message=frappe.get_traceback())
