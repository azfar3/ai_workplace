"""
Employee-first WhatsApp UX — welcome, language, menus, keyword routing, profile wording.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_workplace.response.builder import build_welcome_header, build_menu_header_text
from ai_workplace.services.language import build_language_saved_message
from ai_workplace.services.keyword_router import match_keyword_service
from ai_workplace.services.registry import ACTIVE_EMPLOYEE_QUICK_ACTION_KEYS
from ai_workplace.services.profile_completion import build_profile_completion_hub
from ai_workplace.conversation.orchestrator import SERVICE_ALIASES, _resolve_service_key


class TestEmployeeFirstWelcome(unittest.TestCase):
    def test_active_employee_welcome_staff_support_branding(self):
        ctx = {
            "person_type": "Employee",
            "first_name": "Ahmed",
            "preferred_language": "English",
        }
        header = build_welcome_header(ctx)
        self.assertIn("Assalam-o-Alaikum, Ahmed", header)
        self.assertIn("MicroMerger Staff Support", header)
        self.assertNotIn("AI Assistant", header)
        self.assertNotIn("profile", header.lower())

    def test_menu_header_how_can_we_help(self):
        ctx = {"person_type": "Employee", "preferred_language": "English"}
        text = build_menu_header_text(ctx)
        self.assertIn("How can we help you today", text)

    def test_language_saved_no_profile_completeness(self):
        ctx = {"person_type": "Employee", "preferred_language": "English"}
        msg = build_language_saved_message("English", ctx)
        self.assertIn("How can we help", msg)
        self.assertNotIn("%", msg)
        self.assertNotIn("Profile Completion", msg)


class TestKeywordRouter(unittest.TestCase):
    def test_salary_routes_to_payroll(self):
        self.assertEqual(match_keyword_service("I need my salary slip"), "payroll")

    def test_leave_routes_to_attendance(self):
        self.assertEqual(match_keyword_service("apply leave please"), "attendance_leave")

    def test_hr_chat_routes_to_contact(self):
        self.assertEqual(match_keyword_service("chat with hr"), "contact_hr")

    def test_short_text_no_match(self):
        self.assertIsNone(match_keyword_service("hi"))


class TestQuickActions(unittest.TestCase):
    def test_pinned_quick_action_keys(self):
        self.assertEqual(
            ACTIVE_EMPLOYEE_QUICK_ACTION_KEYS,
            ("attendance_leave", "payroll", "contact_hr"),
        )


class TestProfileHubEmployeeFirst(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_no_completeness_percentage(self, mock_gaps):
        mock_gaps.return_value = {
            "completeness_score": 44,
            "employee_name": "Test User",
            "all_gaps": [
                {
                    "key": "bank",
                    "label": "Review Bank Details",
                    "update_mode": "ticket",
                    "flow_key": "prof_bank_update",
                },
            ],
        }
        outbound = build_profile_completion_hub(
            {"employee": "EMP-001", "preferred_language": "English"}
        )
        body = outbound.body_text or ""
        self.assertIn("My Details & Documents", body)
        self.assertNotIn("44%", body)
        self.assertNotIn("Profile Completion Hub", body)


class TestServiceAliases(unittest.TestCase):
    def test_document_aliases(self):
        for alias, target in (
            ("doc_salary_slip", "pay_download_slip"),
            ("doc_my_requests", "prof_my_requests"),
            ("staff_hr_guidance", "pol_view_policies"),
        ):
            self.assertEqual(SERVICE_ALIASES[alias], target)
            self.assertEqual(_resolve_service_key(alias), target)


if __name__ == "__main__":
    unittest.main()
