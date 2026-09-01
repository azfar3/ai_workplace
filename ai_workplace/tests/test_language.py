"""
ai_workplace/tests/test_language.py
───────────────────────────────────
Unit tests for Multi-language template support (English, Urdu, Roman Urdu).
"""

import unittest

from ai_workplace.response.builder import (
    build_welcome_menu_response,
    build_cancellation_response,
    build_unauthorized_response,
    build_unregistered_response,
)


class TestLanguageSupport(unittest.TestCase):

    def setUp(self):
        self.services = [
            {"key": "hr", "title": "My HR"},
            {"key": "policy", "title": "Policies & Help"},
            {"key": "travel", "title": "My Travel"},
            {"key": "help", "title": "Help / Change Language"},
        ]

    def test_english_responses(self):
        ctx = {"full_name": "John", "person_type": "Employee", "preferred_language": "English"}
        menu = build_welcome_menu_response(ctx, self.services)
        self.assertIn("Assalam-o-Alaikum", menu)
        self.assertIn("Welcome John to MicroMerger Support", menu)

        cancel = build_cancellation_response(ctx)
        self.assertIn("Operation cancelled.", cancel)

        unauth = build_unauthorized_response(ctx)
        self.assertIn("You do not have access to this service.", unauth)

    def test_urdu_responses(self):
        ctx = {"full_name": "John", "person_type": "Employee", "preferred_language": "Urdu"}
        menu = build_welcome_menu_response(ctx, self.services)
        self.assertIn("Assalam-o-Alaikum", menu)
        self.assertIn("مائی ایچ آر", menu)

        cancel = build_cancellation_response(ctx)
        self.assertIn("عمل منسوخ کر دیا گیا", cancel)

        unreg = build_unregistered_response(ctx)
        self.assertIn("رجسٹرڈ نہیں", unreg)

    def test_roman_urdu_responses(self):
        ctx = {"full_name": "John", "person_type": "Employee", "preferred_language": "Roman Urdu"}
        menu = build_welcome_menu_response(ctx, self.services)
        self.assertIn("Welcome John to MicroMerger Support", menu)

        cancel = build_cancellation_response(ctx)
        self.assertIn("Operation cancel ho gaya", cancel)

