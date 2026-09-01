"""
Tests for Hybrid RAG & Dense Semantic Retrieval in ai_workplace.
"""

import unittest
import frappe
from ai_workplace.ai.indexer import (
    cosine_similarity,
    generate_embedding,
    reindex_source,
    search_knowledge,
)


class TestHybridRAG(unittest.TestCase):
    def test_embedding_generation(self):
        vec1 = generate_embedding("Annual leave policy guidelines")
        self.assertIsInstance(vec1, list)
        self.assertGreater(len(vec1), 0)

    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0)

    def test_hybrid_search(self):
        # Insert mock knowledge chunk for testing
        if frappe.db.exists("AI Workplace Knowledge Source", "policies"):
            reindex_source("policies")
            results = search_knowledge("annual leave entitlement", limit=3)
            self.assertIsInstance(results, list)
            if results:
                first = results[0]
                self.assertIn("score", first)
                self.assertIn("keyword_score", first)
                self.assertIn("semantic_score", first)

    def test_roman_urdu_semantic_retrieval(self):
        results = search_knowledge("meri annual chutti kitni hai?", limit=3)
        self.assertIsInstance(results, list)
