"""
Unit tests for profile completion hub and flow routing.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.services.profile_gaps import gap_flow_key, GAP_FLOW_MAP
from ai_workplace.services.profile_completion import build_profile_completion_hub


class TestGapFlowMapping(unittest.TestCase):
    def test_cnic_maps_to_flow(self):
        self.assertEqual(gap_flow_key("cnic"), "prof_cnic_add")
        self.assertEqual(gap_flow_key("bank"), "prof_bank_update")
        self.assertEqual(gap_flow_key("education"), "prof_education_ticket")

    def test_all_map_entries_valid(self):
        for key, flow in GAP_FLOW_MAP.items():
            self.assertTrue(flow.startswith("prof_"), f"{key} -> {flow}")


class TestProfileCompletionHub(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_buttons_use_flow_keys(self, mock_gaps):
        mock_gaps.return_value = {
            "completeness_score": 60,
            "employee_name": "Test User",
            "all_gaps": [
                {
                    "key": "cnic",
                    "label": "Add CNIC number",
                    "update_mode": "ticket",
                    "flow_key": "prof_cnic_add",
                },
                {
                    "key": "education",
                    "label": "Add education",
                    "update_mode": "ticket",
                    "flow_key": "prof_education_ticket",
                },
            ],
        }
        outbound = build_profile_completion_hub({"employee": "EMP-001", "preferred_language": "English"})
        body = outbound.body_text or ""
        self.assertIn("My Details & Documents", body)
        self.assertNotIn("%", body)
        interactive = outbound.interactive or {}
        buttons = interactive.get("action", {}).get("buttons", [])
        ids = [b.get("reply", {}).get("id") for b in buttons]
        self.assertIn("svc_prof_cnic_add", ids)
        self.assertIn("svc_prof_education_ticket", ids)
        self.assertIn("svc_prof_my_requests", ids)


if __name__ == "__main__":
    unittest.main()
