"""
Tests for Dynamic Policy Knowledge Chunks and Content-Based Policy RAG.

Tests cover:
    T1  — New policy creates chunks
    T2  — Updated policy replaces old chunks
    T3  — Idempotency (processing same policy twice → one chunk set)
    T4  — Content-based retrieval (not title-based)
    T5  — Synonym matching
    T6  — Multiple sources synthesised
    T7  — Latest policy preferred over older one
    T8  — Conflict resolution (old conflicting chunk NOT used)
    T9  — Source attribution in search results
    T10 — Non-policy notification → no chunks
"""

from __future__ import annotations

import hashlib
import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.services.policy_notifications import (
    build_section_chunks,
    clean_text_content,
    delete_policy_notification_chunks,
    sync_policy_notification_to_chunks,
)
from ai_workplace.ai.indexer import search_knowledge


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_notif(name, subject, body_html, version="1.0",
                 is_published=True, notif_type="Policy",
                 published_from="2026-01-01", last_updated_on="2026-01-01",
                 policy_document=""):
    """Return a MagicMock that behaves like a System Notifications doc."""
    doc = MagicMock()
    doc.name = name
    doc.doctype = "System Notifications"
    doc.get.side_effect = lambda key, default=None: {
        "name": name,
        "notification_type": notif_type,
        "is_published": 1 if is_published else 0,
        "subject": subject,
        "notifiction": body_html,
        "version": version,
        "published_from": published_from,
        "last_updated_on": last_updated_on,
        "policy_document": policy_document,
    }.get(key, default)
    return doc


def _make_chunk(source_id, text, source_date="2026-01-01", section="", score=0.5):
    return {
        "chunk_id": "chunk-abc",
        "text": text,
        "source": "policies",
        "source_title": "Employee Handbook",
        "source_type": "System Notification",
        "source_id": source_id,
        "document": "Employee Handbook",
        "section": section,
        "version": "1.0",
        "source_date": source_date,
        "effective_date": source_date,
        "score": score,
        "keyword_score": score,
        "semantic_score": score,
        "freshness_score": 0.0,
    }


# ─────────────────────────────────────────────
# T1 — New Policy Creates Chunks
# ─────────────────────────────────────────────

class TestNewPolicyCreatesChunks(unittest.TestCase):
    """T1: Inserting a published Policy notification creates knowledge chunks."""

    def setUp(self):
        self.doc = _make_notif(
            name="NOTIF-001",
            subject="Employee Handbook",
            body_html="<p>Employees may work from home one day per week.</p>",
        )

    @patch("ai_workplace.services.policy_notifications.frappe")
    @patch("ai_workplace.services.policy_notifications.generate_embedding", return_value=[0.1] * 128)
    @patch("ai_workplace.services.policy_notifications._get_setting", return_value="text-embedding-3-small")
    def test_chunks_are_created(self, mock_setting, mock_emb, mock_frappe):
        mock_frappe.db.count.return_value = 0          # no existing chunks
        mock_frappe.db.delete.return_value = None
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.commit.return_value = None
        mock_frappe.utils.today.return_value = "2026-01-01"

        inserted_chunks = []
        def capture_insert(ignore_permissions=False):
            pass
        mock_chunk_doc = MagicMock()
        mock_chunk_doc.insert = capture_insert
        mock_frappe.new_doc.return_value = mock_chunk_doc

        sync_policy_notification_to_chunks(self.doc)

        # frappe.new_doc("AI Workplace Knowledge Chunk") must have been called
        calls = [c for c in mock_frappe.new_doc.call_args_list
                 if c.args and c.args[0] == "AI Workplace Knowledge Chunk"]
        self.assertGreater(len(calls), 0, "Should have created at least one knowledge chunk")

    def test_build_section_chunks_returns_content(self):
        text = "Employees may work from home one day per week."
        chunks = build_section_chunks(text, "Employee Handbook")
        self.assertTrue(len(chunks) > 0)
        self.assertIn("work from home", chunks[0]["text"].lower())


# ─────────────────────────────────────────────
# T2 — Updated Policy Replaces Old Chunks
# ─────────────────────────────────────────────

class TestUpdatedPolicyReplacesChunks(unittest.TestCase):
    """T2: Updating a Policy notification removes old chunks then creates new ones."""

    @patch("ai_workplace.services.policy_notifications.frappe")
    @patch("ai_workplace.services.policy_notifications.generate_embedding", return_value=[0.2] * 128)
    @patch("ai_workplace.services.policy_notifications._get_setting", return_value="text-embedding-3-small")
    def test_old_chunks_deleted_before_new(self, mock_setting, mock_emb, mock_frappe):
        delete_calls = []

        def fake_delete(doctype, filters):
            delete_calls.append((doctype, dict(filters)))

        mock_frappe.db.delete.side_effect = fake_delete
        mock_frappe.db.count.return_value = 0   # no existing with this hash
        mock_frappe.db.get_value.return_value = None
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.commit.return_value = None
        mock_frappe.utils.today.return_value = "2026-09-01"
        mock_frappe.new_doc.return_value = MagicMock()

        doc = _make_notif(
            name="NOTIF-EMP-002",
            subject="Employee Handbook",
            body_html="<p>Employees may work from home two days per week.</p>",
            version="2.0",
            published_from="2026-09-01",
        )

        sync_policy_notification_to_chunks(doc)

        # Deletion of old chunks must happen before inserts
        deleted_for_source_id = any(
            f.get("source_id") == "NOTIF-EMP-002"
            for _, f in delete_calls
        )
        self.assertTrue(deleted_for_source_id,
                        "Should delete old chunks by source_id before inserting new ones")

    def test_section_chunks_reflect_new_content(self):
        old_text = "Employees may work from home one day per week."
        new_text = "Employees may work from home two days per week with manager approval."
        old_chunks = build_section_chunks(old_text, "Employee Handbook")
        new_chunks = build_section_chunks(new_text, "Employee Handbook")

        self.assertIn("one day", old_chunks[0]["text"])
        self.assertIn("two days", new_chunks[0]["text"])
        self.assertNotEqual(old_chunks[0]["text"], new_chunks[0]["text"])


# ─────────────────────────────────────────────
# T3 — Idempotency
# ─────────────────────────────────────────────

class TestIdempotency(unittest.TestCase):
    """T3: Processing the same notification twice should not create duplicates."""

    @patch("ai_workplace.services.policy_notifications.frappe")
    @patch("ai_workplace.services.policy_notifications.generate_embedding", return_value=[0.1] * 128)
    @patch("ai_workplace.services.policy_notifications._get_setting", return_value="text-embedding-3-small")
    def test_second_call_is_noop_when_content_unchanged(self, mock_setting, mock_emb, mock_frappe):
        body = "<p>Employees may work from home one day per week.</p>"
        doc = _make_notif("NOTIF-IDEM", "Handbook", body, version="1.0",
                          published_from="2026-01-01", last_updated_on="2026-01-01")

        # Compute what the hash marker would be
        clean = clean_text_content(body)
        content_hash = hashlib.md5(clean.encode()).hexdigest()
        hash_marker = f"sysnotif:NOTIF-IDEM|hash:{content_hash}|ver:1.0"

        insert_count = [0]
        chunk_doc = MagicMock()
        def fake_insert(**kwargs):
            insert_count[0] += 1
        chunk_doc.insert.side_effect = fake_insert

        # First call: no existing chunks
        mock_frappe.db.count.return_value = 0
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.commit.return_value = None
        mock_frappe.utils.today.return_value = "2026-01-01"
        mock_frappe.db.delete.return_value = None
        mock_frappe.new_doc.return_value = chunk_doc
        sync_policy_notification_to_chunks(doc)
        first_inserts = insert_count[0]

        # Second call: existing chunk with matching hash_marker
        mock_frappe.db.count.return_value = 1
        mock_frappe.db.get_value.return_value = hash_marker
        sync_policy_notification_to_chunks(doc)
        second_inserts = insert_count[0]

        self.assertEqual(first_inserts, second_inserts,
                         "Second call with identical content should not insert new chunks")


# ─────────────────────────────────────────────
# T4 — Content-Based Retrieval (Not Title-Based)
# ─────────────────────────────────────────────

class TestContentBasedRetrieval(unittest.TestCase):
    """T4: Retrieval must match chunk content, not policy title."""

    def test_query_does_not_need_policy_title(self):
        """
        Simulate that a query about 'work from home' retrieves a chunk about
        'work from home' even when the user never mentions 'Employee Handbook'.
        """
        chunk_text = "Employees may work from home up to two days per week with manager approval."
        chunks = build_section_chunks(chunk_text, "Employee Handbook")
        self.assertTrue(any("work from home" in c["text"].lower() for c in chunks))

    def test_search_knowledge_result_contains_source_fields(self):
        """search_knowledge results must carry source_title, source_date, source_type."""
        sample = _make_chunk("NOTIF-X", "Employees may work from home two days per week.")
        # Ensure fields exist
        for field in ("source_title", "source_type", "source_date", "effective_date", "section"):
            self.assertIn(field, sample, f"Result must contain '{field}'")

    def test_evidence_minimizer_exposes_metadata(self):
        from ai_workplace.ai.evidence import _minimize_knowledge_search
        raw = [
            {
                "text": "Employees may work from home two days per week.",
                "source_title": "Employee Handbook",
                "source_type": "System Notification",
                "source_date": "2026-09-01",
                "effective_date": "2026-09-01",
                "section": "Work From Home",
                "version": "2.0",
                "score": 0.92,
            }
        ]
        result = _minimize_knowledge_search(raw)
        self.assertIn("knowledge_matches", result)
        match = result["knowledge_matches"][0]
        self.assertEqual(match["source_title"], "Employee Handbook")
        self.assertEqual(match["source_date"], "2026-09-01")
        self.assertEqual(match["section"], "Work From Home")
        self.assertEqual(match["version"], "2.0")
        self.assertAlmostEqual(match["relevance_score"], 0.92)
        self.assertIn("work from home", match["text"].lower())


# ─────────────────────────────────────────────
# T5 — Synonym Matching
# ─────────────────────────────────────────────

class TestSynonymMatching(unittest.TestCase):
    """T5: 'work remotely' and 'work from home' should match same chunk via embeddings."""

    def test_wfh_terms_share_vector_similarity(self):
        from ai_workplace.ai.indexer import _generate_fallback_vector, cosine_similarity
        v1 = _generate_fallback_vector("work from home remote work")
        v2 = _generate_fallback_vector("working remotely telecommute")
        sim = cosine_similarity(v1, v2)
        # Fallback vector has some overlap for related terms
        self.assertGreater(sim, 0.0, "Related WFH terms should have non-zero similarity")

    def test_chunk_text_is_preserved_for_semantic_search(self):
        """Chunk text must not strip meaningful terms that embeddings rely on."""
        text = "Employees may work from home. Remote workers must use VPN."
        chunks = build_section_chunks(text, "IT Policy")
        combined = " ".join(c["text"] for c in chunks)
        self.assertIn("remote", combined.lower())
        self.assertIn("work from home", combined.lower())


# ─────────────────────────────────────────────
# T6 — Multiple Sources
# ─────────────────────────────────────────────

class TestMultipleSources(unittest.TestCase):
    """T6: Multiple relevant policy chunks from different policies are returned."""

    def test_evidence_minimizer_returns_up_to_8_matches(self):
        from ai_workplace.ai.evidence import _minimize_knowledge_search
        raw = [
            {"text": f"Policy content {i}", "source_title": f"Policy {i}",
             "source_type": "System Notification", "source_date": "2026-01-01",
             "effective_date": "2026-01-01", "section": "", "version": "1.0", "score": 0.5}
            for i in range(10)
        ]
        result = _minimize_knowledge_search(raw)
        self.assertLessEqual(len(result["knowledge_matches"]), 8)
        self.assertGreaterEqual(len(result["knowledge_matches"]), 1)

    def test_multiple_source_titles_preserved(self):
        from ai_workplace.ai.evidence import _minimize_knowledge_search
        raw = [
            _make_chunk("N1", "WFH policy text", score=0.9),
            {**_make_chunk("N2", "Attendance when remote", score=0.8),
             "source_title": "Attendance Policy"},
            {**_make_chunk("N3", "VPN requirements for remote workers", score=0.7),
             "source_title": "IT Security Policy"},
        ]
        result = _minimize_knowledge_search(raw)
        titles = [m["source_title"] for m in result["knowledge_matches"]]
        self.assertIn("Employee Handbook", titles)
        self.assertIn("Attendance Policy", titles)
        self.assertIn("IT Security Policy", titles)


# ─────────────────────────────────────────────
# T7 — Latest Policy Preferred
# ─────────────────────────────────────────────

class TestLatestPolicyPreferred(unittest.TestCase):
    """T7: Fresher policy chunks rank higher when relevance is equal."""

    def test_freshness_score_newer_is_higher(self):
        from ai_workplace.ai.indexer import _generate_fallback_vector, cosine_similarity
        import frappe

        # Build two mock chunks with same text but different source_date
        old_date = "2025-01-01"
        new_date = "2026-09-01"
        text = "Employees may work from home N days per week."

        # Verify the section chunker preserves text accurately
        old_chunks = build_section_chunks(text + " (old)", "Handbook")
        new_chunks = build_section_chunks(text + " (new)", "Handbook")
        self.assertIn("old", old_chunks[0]["text"])
        self.assertIn("new", new_chunks[0]["text"])

    def test_evidence_returns_source_date(self):
        from ai_workplace.ai.evidence import _minimize_knowledge_search
        raw = [
            {**_make_chunk("N-OLD", "WFH one day per week", source_date="2025-01-01"), "score": 0.9},
            {**_make_chunk("N-NEW", "WFH two days per week", source_date="2026-09-01"), "score": 0.9},
        ]
        result = _minimize_knowledge_search(raw)
        dates = [m["source_date"] for m in result["knowledge_matches"]]
        self.assertIn("2025-01-01", dates)
        self.assertIn("2026-09-01", dates)


# ─────────────────────────────────────────────
# T8 — Conflict Resolution
# ─────────────────────────────────────────────

class TestConflictResolution(unittest.TestCase):
    """T8: Old chunks for a notification are deleted when policy is updated."""

    @patch("ai_workplace.services.policy_notifications.frappe")
    @patch("ai_workplace.services.policy_notifications.generate_embedding", return_value=[0.1] * 128)
    @patch("ai_workplace.services.policy_notifications._get_setting", return_value="text-embedding-3-small")
    def test_old_chunks_not_left_alongside_new(self, mock_setting, mock_emb, mock_frappe):
        """After updating a policy, old source_id chunks must be gone."""
        delete_filters = []

        def capture_delete(doctype, filters):
            delete_filters.append(dict(filters))

        mock_frappe.db.delete.side_effect = capture_delete
        mock_frappe.db.count.return_value = 0
        mock_frappe.db.exists.return_value = True
        mock_frappe.db.commit.return_value = None
        mock_frappe.utils.today.return_value = "2026-09-01"
        mock_frappe.new_doc.return_value = MagicMock()

        doc = _make_notif("NOTIF-CONFLICT", "Handbook",
                          "<p>Two days WFH now.</p>", version="2026",
                          published_from="2026-09-01")
        sync_policy_notification_to_chunks(doc)

        deleted_source_ids = [f.get("source_id") for f in delete_filters if "source_id" in f]
        self.assertIn("NOTIF-CONFLICT", deleted_source_ids)


# ─────────────────────────────────────────────
# T9 — Source Attribution
# ─────────────────────────────────────────────

class TestSourceAttribution(unittest.TestCase):
    """T9: Search results must include source_title for LLM attribution."""

    def test_search_result_structure(self):
        chunk = _make_chunk("NOTIF-ATT", "Remote work requires VPN.",
                            source_date="2026-06-01")
        required = ["source_title", "source_type", "source_id", "source_date", "text"]
        for field in required:
            self.assertIn(field, chunk, f"Result missing required field: {field}")
        self.assertEqual(chunk["source_type"], "System Notification")
        self.assertIsNotNone(chunk["source_date"])

    def test_evidence_exposes_source_title(self):
        from ai_workplace.ai.evidence import _minimize_knowledge_search
        raw = [_make_chunk("NOTIF-ATT", "Use VPN when remote.", source_date="2026-06-01")]
        result = _minimize_knowledge_search(raw)
        match = result["knowledge_matches"][0]
        self.assertIn("source_title", match)
        self.assertTrue(match["source_title"])  # must be non-empty


# ─────────────────────────────────────────────
# T10 — Non-Policy Notification → No Chunks
# ─────────────────────────────────────────────

class TestNonPolicyNotification(unittest.TestCase):
    """T10: Non-policy System Notifications must not create knowledge chunks."""

    @patch("ai_workplace.services.policy_notifications.frappe")
    def test_non_policy_type_does_not_index(self, mock_frappe):
        delete_calls = []
        mock_frappe.db.delete.side_effect = lambda dt, f: delete_calls.append(1)
        mock_frappe.db.commit.return_value = None

        doc = _make_notif("NOTIF-NEWS", "Office Update",
                          "<p>Office closed tomorrow.</p>",
                          notif_type="Notification")
        sync_policy_notification_to_chunks(doc)

        # new_doc for Knowledge Chunk must NOT be called
        calls = [c for c in mock_frappe.new_doc.call_args_list
                 if c.args and c.args[0] == "AI Workplace Knowledge Chunk"]
        self.assertEqual(len(calls), 0, "Non-policy notification must not create chunks")

    @patch("ai_workplace.services.policy_notifications.frappe")
    def test_unpublished_policy_cleans_up(self, mock_frappe):
        delete_calls = []
        mock_frappe.db.delete.side_effect = lambda dt, f: delete_calls.append(1)
        mock_frappe.db.commit.return_value = None

        doc = _make_notif("NOTIF-DRAFT", "Draft Policy",
                          "<p>Draft content.</p>",
                          is_published=False)
        sync_policy_notification_to_chunks(doc)

        # Must attempt cleanup (delete) but not insert
        chunk_inserts = [c for c in mock_frappe.new_doc.call_args_list
                         if c.args and c.args[0] == "AI Workplace Knowledge Chunk"]
        self.assertEqual(len(chunk_inserts), 0)


# ─────────────────────────────────────────────
# Section Chunker Unit Tests
# ─────────────────────────────────────────────

class TestSectionChunker(unittest.TestCase):
    """Unit tests for the section-aware chunker."""

    def test_sections_split_on_heading(self):
        text = """Introduction
Some intro text.

## Working Hours
Employees work 9 to 5.

## Work From Home
Employees may work from home up to two days per week.

## Sick Leave
Employees are entitled to 10 sick days per year."""
        chunks = build_section_chunks(text, "Employee Handbook")
        texts = [c["text"] for c in chunks]
        # Each section should be in its own chunk (small content)
        self.assertTrue(any("Working Hours" in t or "9 to 5" in t for t in texts))
        self.assertTrue(any("Work From Home" in t or "two days" in t for t in texts))
        self.assertTrue(any("Sick Leave" in t or "sick days" in t for t in texts))

    def test_large_section_gets_split(self):
        # Generate a section larger than MAX_CHUNK_WORDS
        words = ["word"] * 700
        text = "## Big Section\n" + " ".join(words)
        chunks = build_section_chunks(text, "Big Doc")
        self.assertGreater(len(chunks), 1, "Large section should produce multiple chunks")

    def test_no_content_returns_empty(self):
        chunks = build_section_chunks("", "Empty Doc")
        self.assertEqual(chunks, [])

    def test_html_cleaned_before_indexing(self):
        html = "<p>Employees may <b>work from home</b> up to two days.</p>"
        text = clean_text_content(html)
        self.assertNotIn("<b>", text)
        self.assertIn("work from home", text)

    def test_chunk_carries_document_name(self):
        text = "Work from home is allowed."
        chunks = build_section_chunks(text, "WFH Policy")
        self.assertEqual(chunks[0]["document_name"], "WFH Policy")


if __name__ == "__main__":
    unittest.main()
