import unittest
import frappe
from ai_workplace.ai.indexer import search_knowledge, _clean_query_tokens

class TestPolicyRetrieval(unittest.TestCase):
    def test_dual_job_query_retrieval(self):
        results = search_knowledge("can i work dual job is it allowed?", limit=3, context={"policy_scope": "HO"})
        self.assertTrue(len(results) > 0, "Should return results for dual job query")
        top_doc = results[0]["document"]
        self.assertIn("Employee Handbook", top_doc, "Top result should be Employee Handbook")

    def test_travel_policy_query_retrieval(self):
        results = search_knowledge("what is my travel policy", limit=3, context={"policy_scope": "HO"})
        self.assertTrue(len(results) > 0, "Should return results for travel policy query")
        top_doc = results[0]["document"]
        self.assertIn("Travel Policy", top_doc, "Top result should be Travel Policy")

    def test_roman_urdu_retrieval(self):
        results = search_knowledge("kya mai dusri job kar sakta hu", limit=3, context={"policy_scope": "HO"})
        self.assertTrue(len(results) > 0, "Should return results for Roman Urdu dual job query")
        top_doc = results[0]["document"]
        self.assertIn("Employee Handbook", top_doc, "Top result should be Employee Handbook")

    def test_synonym_expansion(self):
        tokens = _clean_query_tokens("can i work dual job")
        self.assertIn("outside", tokens)
        self.assertIn("employment", tokens)
        self.assertIn("freelancing", tokens)

def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPolicyRetrieval)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        raise Exception(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")

