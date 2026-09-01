"""
Integration tests for WhatsApp profile menu flows (CNIC, contact, bank, education, work history).
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.profile_completion import (
    build_my_requests_response,
    build_profile_completion_hub,
    handle_profile_flow_message,
    handle_profile_gap_action,
    start_profile_flow,
)


def _conv(draft: dict | None = None, intent: str | None = None):
    c = MagicMock()
    c.name = "CONV-MENU-001"
    c.draft_payload = json.dumps(draft) if draft else None
    c.current_intent = intent
    c.current_state = ConversationState.PROCESSING
    return c


def _ctx(employee: str = "EMP-TEST-001"):
    return {"employee": employee, "erp_user": "Administrator", "preferred_language": "English"}


class TestProfileMenuFlows(unittest.TestCase):
    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_contact_flow_submits_epcr(self, mock_submit, mock_update):
        mock_submit.return_value = MagicMock(body_text="✅ Request submitted: *EPCR-001*")
        conv = _conv(
            {
                "flow": "prof_contact_update",
                "step": "emergency",
                "data": {"cell_number": "0323323323", "prefered_email": "a@web.com"},
            },
            "prof_contact_update",
        )
        out = handle_profile_flow_message(conv, "03211234567", _ctx())
        mock_submit.assert_called_once_with(conv, _ctx(), "Contact Change", {
            "cell_number": "0323323323",
            "prefered_email": "a@web.com",
            "emergency_phone_number": "03211234567",
        })
        self.assertIn("EPCR", out.body_text)

    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_cnic_flow_submits_epcr(self, mock_submit, mock_update):
        mock_submit.return_value = MagicMock(body_text="✅ Request submitted: *EPCR-002*")
        conv = _conv(
            {
                "flow": "prof_cnic_add",
                "step": "expiry_date",
                "data": {
                    "cnic": "3405408765645",
                    "cnic_scan_front": "/files/front.jpg",
                    "cnic_scan_back": "/files/back.jpg",
                    "date_of_issue": "2020-01-01",
                },
            },
            "prof_cnic_add",
        )
        handle_profile_flow_message(conv, "2030-01-01", _ctx())
        args = mock_submit.call_args[0]
        self.assertEqual(args[2], "CNIC Change")
        self.assertEqual(args[3]["valid_upto"], "2030-01-01")

    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_profile_ticket")
    def test_bank_flow_submits_epcr(self, mock_submit, mock_update):
        mock_submit.return_value = MagicMock(body_text="submitted")
        conv = _conv(
            {
                "flow": "prof_bank_update",
                "step": "iban",
                "data": {
                    "bank_name": "HBL",
                    "bank_account_title": "Test User",
                    "bank_ac_no": "1234567890",
                },
            },
            "prof_bank_update",
        )
        handle_profile_flow_message(conv, "PK36SCBL0000001123456702", _ctx())
        self.assertEqual(mock_submit.call_args[0][2], "Bank Change")

    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_ticket")
    def test_education_flow_submits_epcr(self, mock_submit, mock_update):
        mock_submit.return_value = MagicMock(body_text="✅ Request submitted: *EPCR-003*")
        conv = _conv(
            {
                "flow": "prof_education_ticket",
                "step": "confirm",
                "data": {
                    "qualification": "Bachelors",
                    "institution": "NUST",
                    "year": "2020",
                    "attachment": "/files/degree.pdf",
                },
            },
            "prof_education_ticket",
        )
        handle_profile_flow_message(conv, "yes", _ctx())
        mock_submit.assert_called_once()
        self.assertEqual(mock_submit.call_args[0][2], "Education")

    @patch("ai_workplace.services.profile_completion.update_conversation")
    @patch("ai_workplace.services.profile_completion._submit_ticket")
    def test_work_history_flow_submits_epcr(self, mock_submit, mock_update):
        mock_submit.return_value = MagicMock(body_text="✅ Request submitted: *EPCR-004*")
        conv = _conv(
            {
                "flow": "prof_work_history_ticket",
                "step": "confirm",
                "data": {
                    "company": "ABC Corp",
                    "designation": "Engineer",
                    "dates": "2020-2022",
                    "attachment": "/files/letter.pdf",
                },
            },
            "prof_work_history_ticket",
        )
        handle_profile_flow_message(conv, "yes", _ctx())
        mock_submit.assert_called_once()
        self.assertEqual(mock_submit.call_args[0][2], "Work History")

    @patch("ai_workplace.services.profile_completion.start_profile_flow")
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_gap_routes_contact(self, mock_gaps, mock_start):
        mock_gaps.return_value = {
            "all_gaps": [{
                "key": "contact",
                "label": "Complete contact details",
                "update_mode": "ticket",
                "flow_key": "prof_contact_update",
            }],
        }
        mock_start.return_value = MagicMock(body_text="Enter mobile")
        conv = _conv()
        handle_profile_gap_action(conv, _ctx(), "contact")
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][2], "prof_contact_update")

    @patch("ai_workplace.services.profile_completion.start_profile_flow")
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_gap_routes_cnic(self, mock_gaps, mock_start):
        mock_gaps.return_value = {
            "all_gaps": [{
                "key": "cnic",
                "label": "Add CNIC number",
                "update_mode": "ticket",
                "flow_key": "prof_cnic_add",
            }],
        }
        mock_start.return_value = MagicMock(body_text="Enter CNIC")
        handle_profile_gap_action(_conv(), _ctx(), "cnic")
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][2], "prof_cnic_add")

    @patch("ai_workplace.services.profile_completion.start_profile_flow")
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_gap_routes_education(self, mock_gaps, mock_start):
        mock_gaps.return_value = {
            "all_gaps": [{
                "key": "education",
                "label": "Add education record",
                "update_mode": "ticket",
                "flow_key": "prof_education_ticket",
            }],
        }
        mock_start.return_value = MagicMock(body_text="Enter qualification")
        handle_profile_gap_action(_conv(), _ctx(), "education")
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][2], "prof_education_ticket")

    @patch("ai_workplace.services.profile_completion.start_profile_flow")
    @patch("ai_workplace.services.profile_completion.get_employee_profile_gaps")
    def test_hub_gap_routes_work_history(self, mock_gaps, mock_start):
        mock_gaps.return_value = {
            "all_gaps": [{
                "key": "work_history",
                "label": "Add work history",
                "update_mode": "ticket",
                "flow_key": "prof_work_history_ticket",
            }],
        }
        mock_start.return_value = MagicMock(body_text="Enter company")
        handle_profile_gap_action(_conv(), _ctx(), "work_history")
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args[0][2], "prof_work_history_ticket")

    @patch("ai_workplace.services.profile_completion.update_conversation")
    def test_flow_starts_include_approval_note(self, mock_update):
        for flow_key in (
            "prof_contact_update",
            "prof_cnic_add",
            "prof_bank_update",
            "prof_education_ticket",
            "prof_work_history_ticket",
        ):
            out = start_profile_flow(_conv(), _ctx(), flow_key)
            self.assertIn("HR for approval", out.body_text, msg=flow_key)

    @patch("ai_workplace.api.profile.get_pending_profile_requests")
    def test_my_requests_menu(self, mock_pending):
        mock_pending.return_value = [
            {"name": "EPCR-001", "request_type": "Contact Change", "status": "Submitted"},
        ]
        out = build_my_requests_response(_ctx())
        self.assertIn("EPCR-001", out.body_text)
        self.assertIn("Contact Change", out.body_text)


class TestProfileEPCRSubmitIntegration(unittest.TestCase):
    """Requires site DB — skipped in CI without employee fixture."""

    @patch("ai_workplace.api.profile.frappe.db.commit")
    @patch("ai_workplace.api.profile.frappe.new_doc")
    def test_whatsapp_submit_builds_epcr_doc(self, mock_new_doc, mock_commit):
        from ai_workplace.api.profile import submit_whatsapp_profile_change_request

        doc = MagicMock()
        doc.name = "EPCR-TEST-001"
        doc.status = "Submitted"
        mock_new_doc.return_value = doc

        result = submit_whatsapp_profile_change_request(
            "EMP-TEST-001",
            "Contact Change",
            [{"field": "contact_change", "proposed_json": json.dumps({"cell_number": "03001234567"})}],
            context={"employee": "EMP-TEST-001", "erp_user": "Administrator"},
        )
        self.assertEqual(result["name"], "EPCR-TEST-001")
        doc.append.assert_called_once()
        doc.insert.assert_called_once_with(ignore_permissions=True)


if __name__ == "__main__":
    unittest.main()
