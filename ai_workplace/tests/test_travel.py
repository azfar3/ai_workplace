"""
ai_workplace/tests/test_travel.py
───────────────────────────────────
Unit tests for Travel & Claims self-service handlers.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.services.travel import (
    build_approved_travel_response,
    build_claim_status_response,
    build_travel_sop_outbound,
    build_upcoming_travel_response,
    build_vehicle_info_response,
    find_travel_sop_policy,
    handle_travel_authorization_message,
    start_travel_authorization,
    start_travel_problem_report,
)


class TestTravelServices(unittest.TestCase):
    def setUp(self):
        self.context_en = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "English",
        }
        self.context_ur = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "Urdu",
        }

    @patch("ai_workplace.services.travel.get_approved_travel_requests")
    def test_build_approved_travel_response(self, mock_get):
        mock_get.return_value = [
            {
                "name": "TAR-001",
                "purpose_of_travel": "Field visit Islamabad",
                "posting_date": "2026-08-01",
                "project": "ComNet - HR",
                "legs": [
                    {
                        "from_date": "2026-08-10",
                        "to_date": "2026-08-11",
                        "source": "Karachi",
                        "destination": "Islamabad",
                        "mode_of_travel": "By Air",
                        "vehicle_type": "",
                    }
                ],
            }
        ]

        res = build_approved_travel_response(self.context_en)
        self.assertIn("Approved Travel", res)
        self.assertIn("Field visit Islamabad", res)
        self.assertIn("Karachi", res)
        self.assertIn("Islamabad", res)

    @patch("ai_workplace.services.travel.get_approved_travel_requests")
    def test_build_approved_travel_empty_urdu(self, mock_get):
        mock_get.return_value = []
        res = build_approved_travel_response(self.context_ur)
        self.assertIn("منظور شدہ سفر", res)

    @patch("ai_workplace.services.travel.get_upcoming_travel_trips")
    def test_build_upcoming_travel_response(self, mock_get):
        mock_get.return_value = [
            {
                "request_name": "TAR-002",
                "purpose_of_travel": "Client meeting",
                "workflow_state": "Approved",
                "from_date": "2026-09-05",
                "to_date": "2026-09-06",
                "source": "Lahore",
                "destination": "Multan",
                "mode_of_travel": "By Road",
                "vehicle_type": "Company Car",
            }
        ]

        res = build_upcoming_travel_response(self.context_en)
        self.assertIn("Upcoming Travel", res)
        self.assertIn("Lahore", res)
        self.assertIn("Company Car", res)

    @patch("ai_workplace.services.travel.get_travel_expense_claims")
    def test_build_claim_status_response(self, mock_get):
        mock_get.return_value = [
            {
                "name": "Ali Ahmed-08-2026-0001",
                "posting_date": "2026-08-15",
                "purpose_of_travel": "Islamabad visit",
                "display_status": "Approved",
                "grand_total": 12500,
            }
        ]

        res = build_claim_status_response(self.context_en)
        self.assertIn("Travel Claim Status", res)
        self.assertIn("Approved", res)
        self.assertIn("12500", res)

    @patch("ai_workplace.services.travel.get_employee_vehicle_info")
    def test_build_vehicle_info_response(self, mock_get):
        mock_get.return_value = {
            "type_of_commute": "Own Car",
            "vehicle_number": "ABC-123",
            "vehicle_details": "Toyota Corolla White",
            "pass_number": "P-99",
            "upcoming_vehicle_types": ["By Road"],
        }

        res = build_vehicle_info_response(self.context_en)
        self.assertIn("Vehicle / Commute Info", res)
        self.assertIn("Own Car", res)
        self.assertIn("ABC-123", res)

    @patch("ai_workplace.services.travel.wrap_with_menu_again")
    @patch("ai_workplace.services.travel.find_travel_sop_policy")
    def test_build_travel_sop_outbound_not_found(self, mock_find, mock_wrap):
        mock_find.return_value = None
        mock_wrap.return_value = MagicMock(body_text="not found")
        outbound = build_travel_sop_outbound(self.context_en)
        self.assertEqual(outbound.body_text, "not found")

    @patch("ai_workplace.services.travel.wrap_with_menu_again")
    @patch("ai_workplace.services.travel.load_policy_pdf_bytes")
    @patch("ai_workplace.services.travel.find_travel_sop_policy")
    def test_build_travel_sop_outbound_with_pdf(self, mock_find, mock_load, mock_wrap):
        mock_find.return_value = {
            "subject": "Travel & DSA Policy",
            "policy_document": "/files/travel.pdf",
            "version": "2.1",
        }
        mock_load.return_value = (b"%PDF-1.4", "Travel_SOP.pdf")
        mock_wrap.return_value = MagicMock(body_text="menu")

        outbound = build_travel_sop_outbound(self.context_en)
        self.assertTrue(outbound.has_document())
        self.assertIn("Travel & DSA Policy", outbound.document_caption)
        self.assertEqual(outbound.follow_up, [mock_wrap.return_value])

    @patch("ai_workplace.services.concern_report.start_concern_report")
    def test_start_travel_problem_report(self, mock_start):
        mock_start.return_value = MagicMock(
            body_text="Step 1 — Select Incident Type:",
            interactive={"body": {"text": "Step 1 — Select Incident Type:"}},
        )
        conv = MagicMock()
        outbound = start_travel_problem_report(conv, self.context_en)
        self.assertIn("Travel Problem Report", outbound.body_text)
        self.assertIn("Step 1", outbound.body_text)

    @patch("frappe.get_all")
    def test_find_travel_sop_policy_prefers_travel_subject(self, mock_get_all):
        mock_get_all.return_value = [
            {"name": "SN-1", "subject": "Code of Conduct", "policy_document": "/files/coc.pdf"},
            {"name": "SN-2", "subject": "Travel & DSA Policy", "policy_document": "/files/travel.pdf"},
        ]
        result = find_travel_sop_policy()
        self.assertEqual(result["name"], "SN-2")

    @patch("frappe.db.exists")
    @patch("ai_workplace.services.travel.update_conversation")
    def test_start_travel_authorization(self, mock_update, mock_exists):
        mock_exists.return_value = True
        conv = MagicMock()
        conv.employee = "EMP-001"
        outbound = start_travel_authorization(conv, self.context_en)
        self.assertIn("Request Travel Authorisation", outbound.body_text)
        self.assertIn("Step 1 of 5", outbound.body_text)
        mock_update.assert_called_once()

    @patch("ai_workplace.services.travel._create_travel_authorisation")
    @patch("ai_workplace.services.travel.update_conversation")
    def test_handle_travel_authorization_flow(self, mock_update, mock_create):
        mock_create.return_value = "TAR-TEST-0001"
        conv = MagicMock()

        # Step 1: Purpose
        conv.draft_payload = '{"step": "awaiting_purpose", "employee": "EMP-001"}'
        out1 = handle_travel_authorization_message(conv, "Field Monitoring in Islamabad", self.context_en)
        self.assertIn("Select *Mode of Travel*", out1.body_text)

        # Step 2: Mode
        conv.draft_payload = '{"step": "awaiting_mode", "employee": "EMP-001", "purpose": "Field Monitoring"}'
        out2 = handle_travel_authorization_message(conv, "Car", self.context_en)
        self.assertIn("From Date", out2.body_text)

        # Step 3: From Date
        conv.draft_payload = '{"step": "awaiting_from_date", "employee": "EMP-001", "purpose": "Field Monitoring", "mode": "Car / Vehicle"}'
        out3 = handle_travel_authorization_message(conv, "2026-09-10", self.context_en)
        self.assertIn("To Date", out3.body_text)

        # Step 4: To Date
        conv.draft_payload = '{"step": "awaiting_to_date", "employee": "EMP-001", "purpose": "Field Monitoring", "mode": "Car / Vehicle", "from_date": "2026-09-10"}'
        out4 = handle_travel_authorization_message(conv, "2026-09-12", self.context_en)
        self.assertIn("Source & Destination", out4.body_text)

        # Step 5: Route
        conv.draft_payload = '{"step": "awaiting_route", "employee": "EMP-001", "purpose": "Field Monitoring", "mode": "Car / Vehicle", "from_date": "2026-09-10", "to_date": "2026-09-12"}'
        out5 = handle_travel_authorization_message(conv, "Lahore to Islamabad", self.context_en)
        self.assertIn("Travel Authorisation Summary", out5.body_text)

        # Step 6: Confirmation
        conv.draft_payload = '{"step": "awaiting_confirm", "employee": "EMP-001", "purpose": "Field Monitoring", "mode": "Car / Vehicle", "from_date": "2026-09-10", "to_date": "2026-09-12", "source": "Lahore", "destination": "Islamabad"}'
        out6 = handle_travel_authorization_message(conv, "yes", self.context_en)
        self.assertIn("Travel Authorisation Submitted", out6.body_text)
        self.assertIn("TAR-TEST-0001", out6.body_text)


if __name__ == "__main__":
    unittest.main()

