"""
ai_workplace/tests/test_language_selection.py
──────────────────────────────────────────────
Tests for language selection service and interactive buttons.
"""

import unittest

from ai_workplace.services.language import (
    parse_language_selection,
    build_language_selection_message,
    canonical_to_code,
)
from ai_workplace.whatsapp.outbound import OutboundMessage


class TestLanguageSelection(unittest.TestCase):

    def test_parse_button_ids(self):
        self.assertEqual(parse_language_selection("lang_en"), "English")
        self.assertEqual(parse_language_selection("lang_ur"), "Urdu")
        self.assertEqual(parse_language_selection("lang_roman"), "Roman Urdu")

    def test_parse_text_aliases(self):
        self.assertEqual(parse_language_selection("English"), "English")
        self.assertEqual(parse_language_selection("urdu"), "Urdu")
        self.assertEqual(parse_language_selection("roman urdu"), "Roman Urdu")

    def test_build_language_buttons(self):
        ctx = {"preferred_language": "English"}
        out = build_language_selection_message(ctx)
        self.assertIsInstance(out, OutboundMessage)
        self.assertTrue(out.is_interactive())
        self.assertEqual(out.interactive["type"], "button")
        buttons = out.interactive["action"]["buttons"]
        self.assertEqual(len(buttons), 3)
        self.assertEqual(buttons[0]["reply"]["id"], "lang_en")

    def test_canonical_to_code(self):
        self.assertEqual(canonical_to_code("English"), "en")
        self.assertEqual(canonical_to_code("Urdu"), "ur")
        self.assertEqual(canonical_to_code("Roman Urdu"), "roman_urdu")
