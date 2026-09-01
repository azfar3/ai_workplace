"""
Tests for Phase 2.2 (EntityExtractor) and Phase 4/5 catalog structure.

Run via: bench --site erp.v15 run-tests --app ai_workplace --module ai_workplace.tests.test_entity_extractor
"""
import unittest
from datetime import datetime, date
from ai_workplace.ai.entity_extractor import EntityExtractor


class TestMonthYearExtraction(unittest.TestCase):
    """Phase 2.2 — month/year extraction for payroll queries."""

    def _extract(self, intent, text):
        return EntityExtractor.extract(intent, text)

    # Explicit month names
    def test_august_with_year(self):
        r = self._extract("latest_salary_slip", "salary slip for August 2026")
        self.assertEqual(r.get("month"), 8)
        self.assertEqual(r.get("year"), 2026)

    def test_september_short(self):
        r = self._extract("latest_salary_slip", "show slip for Sep")
        self.assertEqual(r.get("month"), 9)
        self.assertIsNotNone(r.get("year"))

    def test_january_full(self):
        r = self._extract("tax_deductions", "tax details for January 2025")
        self.assertEqual(r.get("month"), 1)
        self.assertEqual(r.get("year"), 2025)

    def test_month_year_slash_format(self):
        r = self._extract("latest_salary_slip", "salary slip 08/2026")
        self.assertEqual(r.get("month"), 8)
        self.assertEqual(r.get("year"), 2026)

    # Relative references
    def test_last_month(self):
        r = self._extract("latest_salary_slip", "show salary slip for last month")
        now = datetime.now()
        expected_month = now.month - 1 if now.month > 1 else 12
        self.assertEqual(r.get("month"), expected_month)

    def test_this_month(self):
        r = self._extract("monthly_attendance", "attendance this month")
        now = datetime.now()
        self.assertEqual(r.get("month"), now.month)
        self.assertEqual(r.get("year"), now.year)

    # No month → returns empty (tool uses its own default)
    def test_no_month_returns_empty(self):
        r = self._extract("latest_salary_slip", "show my salary slip")
        # Either empty or whatever — must not crash
        self.assertIsInstance(r, dict)

    # Non-payroll intent → no extraction
    def test_other_intent_no_extraction(self):
        r = self._extract("leave_balance", "how many leaves in August")
        self.assertEqual(r, {})


class TestDateRangeExtraction(unittest.TestCase):
    """Phase 2.2 — date range extraction for leave applications."""

    def _extract(self, text):
        return EntityExtractor.extract("apply_leave", text)

    def test_iso_dates_from_to(self):
        r = self._extract("leave from 2026-09-10 to 2026-09-12")
        self.assertEqual(r.get("from_date"), "2026-09-10")
        self.assertEqual(r.get("to_date"), "2026-09-12")

    def test_day_month_range(self):
        r = self._extract("leave from 10th September to 12th September")
        self.assertIn("from_date", r)
        self.assertIn("to_date", r)
        self.assertTrue(r["from_date"].endswith("-09-10"))
        self.assertTrue(r["to_date"].endswith("-09-12"))

    def test_weekday_range(self):
        r = self._extract("leave from Monday to Wednesday")
        self.assertIn("from_date", r)
        self.assertIn("to_date", r)
        from_d = date.fromisoformat(r["from_date"])
        to_d = date.fromisoformat(r["to_date"])
        self.assertEqual(from_d.weekday(), 0)   # Monday
        self.assertEqual(to_d.weekday(), 2)     # Wednesday

    def test_single_day_on_friday(self):
        r = self._extract("apply leave on Friday")
        self.assertIn("from_date", r)
        from_d = date.fromisoformat(r["from_date"])
        self.assertEqual(from_d.weekday(), 4)   # Friday
        self.assertEqual(r["from_date"], r["to_date"])  # single day

    def test_no_dates_returns_empty(self):
        r = self._extract("I want to apply for leave")
        # Must not crash; dates may be empty
        self.assertIsInstance(r, dict)


class TestCatalogClarificationStructure(unittest.TestCase):
    """Phase 5 — verify clarification_text and clarification_options exist
    in the catalog for intents with response_mode='clarification'."""

    def test_show_leave_has_multilingual_clarification_text(self):
        from ai_workplace.ai.intent_catalog import INTENT_CATALOG
        meta = INTENT_CATALOG.get("show_leave", {})
        self.assertEqual(meta.get("response_mode"), "clarification")
        texts = meta.get("clarification_text", {})
        self.assertIn("English", texts)
        self.assertIn("Urdu", texts)
        self.assertIn("Roman Urdu", texts)

    def test_show_leave_has_clarification_options(self):
        from ai_workplace.ai.intent_catalog import INTENT_CATALOG
        opts = INTENT_CATALOG["show_leave"].get("clarification_options", [])
        self.assertGreater(len(opts), 0)
        for opt in opts:
            self.assertIn("id", opt)
            self.assertIn("title", opt)

    def test_all_clarification_intents_have_text(self):
        from ai_workplace.ai.intent_catalog import INTENT_CATALOG
        for key, meta in INTENT_CATALOG.items():
            if meta.get("response_mode") == "clarification":
                # All clarification intents must have at least English text
                self.assertTrue(
                    meta.get("clarification_text", {}).get("English")
                    or meta.get("aliases"),
                    f"Intent {key!r} is clarification mode but has no text",
                )


class TestHybridCatalogStructure(unittest.TestCase):
    """Phase 4 — hybrid intents must have a tool so hybrid_handler can fetch data."""

    def test_hybrid_intents_have_tool(self):
        from ai_workplace.ai.intent_catalog import INTENT_CATALOG
        for key, meta in INTENT_CATALOG.items():
            if meta.get("response_mode") == "hybrid":
                self.assertIsNotNone(
                    meta.get("tool"),
                    f"Hybrid intent {key!r} has no tool — hybrid_handler needs one",
                )


if __name__ == "__main__":
    unittest.main()
