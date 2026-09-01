"""
ai_workplace/tests/test_careers_guide.py
──────────────────────────────────────────
Unit tests for XpertJobs careers guide service.
"""

from __future__ import annotations

import unittest

from ai_workplace.services.careers_guide import (
    XPERTJOBS_URL,
    build_careers_guide_response,
)


class TestCareersGuide(unittest.TestCase):
    def setUp(self):
        self.context_en = {"preferred_language": "English"}
        self.context_ur = {"preferred_language": "Urdu"}
        self.context_ru = {"preferred_language": "Roman Urdu"}

    def test_guest_careers_english(self):
        res = build_careers_guide_response("guest_careers", self.context_en)
        self.assertIn("Careers at MicroMerger", res)
        self.assertIn(XPERTJOBS_URL, res)
        self.assertIn("How to apply", res)
        self.assertIn("does not accept job applications via WhatsApp", res)

    def test_guest_careers_urdu(self):
        res = build_careers_guide_response("guest_careers", self.context_ur)
        self.assertIn("MicroMerger", res)
        self.assertIn(XPERTJOBS_URL, res)
        self.assertIn("درخواست", res)

    def test_guest_job_status_roman_urdu(self):
        res = build_careers_guide_response("guest_job_status", self.context_ru)
        self.assertIn("Application Status", res)
        self.assertIn(XPERTJOBS_URL, res)
        self.assertIn("My Applications", res)
        self.assertIn("Contact HR", res)

    def test_former_careers_english(self):
        res = build_careers_guide_response("former_careers", self.context_en)
        self.assertIn("Career Opportunities", res)
        self.assertIn(XPERTJOBS_URL, res)
        self.assertIn("Former team members", res)

    def test_unknown_key_falls_back_to_guest_careers(self):
        res = build_careers_guide_response("unknown_key", self.context_en)
        self.assertIn("Careers at MicroMerger", res)


if __name__ == "__main__":
    unittest.main()
