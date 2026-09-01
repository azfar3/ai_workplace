"""
ai_workplace/tests/test_deliverables.py
────────────────────────────────────────
Unit tests for deliverable WhatsApp service.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.deliverables import (
    _format_submit_error,
    _is_draft_deliverable,
    _resolve_pick,
    _resolve_submit_workflow_action,
    _submit_deliverable_for_approval,
    build_deliverable_status_outbound,
    build_deliverable_status_response,
    handle_deliverable_add_attachment,
    handle_deliverable_add_message,
    handle_submit_for_approval_request,
    is_awaiting_deliverable_attachment,
    is_submit_for_approval_trigger,
    start_add_deliverable,
    start_submit_deliverable,
    start_submit_saved_deliverable,
)
from ai_workplace.whatsapp.interactive import build_deliverable_post_save_buttons


def _conv(**kwargs):
    conv = MagicMock()
    conv.employee = kwargs.get("employee", "EMP-DLV-01")
    conv.draft_payload = kwargs.get("draft_payload")
    conv.current_intent = kwargs.get("current_intent", "deliverable_add")
    return conv


def _deliverable_context():
    return {
        "employee": "EMP-DLV-01",
        "user": "deliverable@example.com",
        "staff_category": "project_deliverable",
        "allowed_services": ["hr", "deliverables", "policies", "concerns", "contact_hr"],
        "preferred_language": "English",
    }


def _permanent_context():
    return {
        "employee": "EMP-001",
        "user": "john@example.com",
        "staff_category": "permanent",
        "allowed_services": ["hr", "attendance_leave", "payroll"],
        "preferred_language": "English",
    }


class TestDeliverablesService(unittest.TestCase):

    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_start_add_denied_for_permanent_staff(self, mock_update):
        outbound = start_add_deliverable(_conv(), _permanent_context())
        self.assertIn("Contract (Deliverable)", outbound.body_text)
        mock_update.assert_not_called()

    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_start_add_begins_flow_for_deliverable_staff(self, mock_update):
        outbound = start_add_deliverable(_conv(), _deliverable_context())
        self.assertIn("Add Deliverable", outbound.body_text)
        mock_update.assert_called_once()
        kwargs = mock_update.call_args.kwargs
        self.assertEqual(kwargs["state"], ConversationState.PROCESSING)
        self.assertEqual(kwargs["current_intent"], "deliverable_add")

    @patch("ai_workplace.services.deliverables._list_draft_deliverables", return_value=[])
    def test_start_submit_without_drafts(self, _mock_list):
        outbound = start_submit_deliverable(_conv(), _deliverable_context())
        self.assertIn("no draft deliverables", outbound.body_text.lower())

    @patch("ai_workplace.services.deliverables._begin_submit_confirm")
    @patch("ai_workplace.services.deliverables._list_draft_deliverables")
    def test_start_submit_single_draft_goes_to_confirm(self, mock_list, mock_confirm):
        mock_list.return_value = [
            {
                "name": "CD-001",
                "from_date": "2026-09-01",
                "to_date": "2026-09-30",
                "total_amount": 50000,
                "workflow_state": "Draft",
                "status": "Draft",
                "docstatus": 0,
            }
        ]
        mock_confirm.return_value = MagicMock(body_text="confirm")
        outbound = start_submit_deliverable(_conv(), _deliverable_context())
        mock_confirm.assert_called_once()
        self.assertEqual(outbound.body_text, "confirm")

    @patch("ai_workplace.services.deliverables._list_draft_deliverables")
    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_start_submit_shows_interactive_draft_list(self, mock_update, mock_list):
        mock_list.return_value = [
            {
                "name": "CD-001",
                "from_date": "2026-09-01",
                "to_date": "2026-09-30",
                "total_amount": 50000,
                "workflow_state": "Draft",
                "status": "Draft",
                "docstatus": 0,
            },
            {
                "name": "CD-002",
                "from_date": "2026-10-01",
                "to_date": "2026-10-31",
                "total_amount": 60000,
                "workflow_state": "Draft",
                "status": "Draft",
                "docstatus": 0,
            },
        ]
        outbound = start_submit_deliverable(_conv(), _deliverable_context())
        self.assertTrue(outbound.is_interactive())
        self.assertEqual(outbound.interactive["type"], "list")
        rows = outbound.interactive["action"]["sections"][0]["rows"]
        self.assertEqual(rows[0]["id"], "dlv_pick_0")
        mock_update.assert_called_once()

    @patch("ai_workplace.services.deliverables._list_draft_deliverables")
    def test_status_shows_submit_button_when_drafts_exist(self, mock_list):
        mock_list.return_value = [{"name": "CD-001", "workflow_state": "Draft", "status": "Draft", "docstatus": 0}]
        with patch("ai_workplace.services.deliverables.frappe.get_all") as mock_get_all:
            mock_get_all.return_value = [
                {
                    "name": "CD-001",
                    "from_date": "2026-09-01",
                    "to_date": "2026-09-30",
                    "total_amount": 50000,
                    "workflow_state": "Draft",
                    "status": "Draft",
                    "modified": "2026-09-15",
                }
            ]
            outbound = build_deliverable_status_outbound(_deliverable_context())
        self.assertIn("My Deliverables", outbound.body_text)
        self.assertTrue(outbound.follow_up)
        self.assertEqual(
            outbound.follow_up[0].interactive["action"]["buttons"][0]["reply"]["id"],
            "dlv_submit",
        )

    def test_is_submit_for_approval_trigger(self):
        self.assertTrue(is_submit_for_approval_trigger("dlv_submit"))
        self.assertTrue(is_submit_for_approval_trigger("svc_dlv_submit"))
        self.assertTrue(is_submit_for_approval_trigger("📤 Submit for Approv…"))
        self.assertTrue(
            is_submit_for_approval_trigger(
                "You have draft deliverables ready to submit:"
            )
        )
        self.assertFalse(is_submit_for_approval_trigger("menu"))

    @patch("ai_workplace.services.deliverables.start_submit_deliverable")
    def test_handle_submit_for_approval_request_uses_standard_flow(self, mock_start):
        mock_start.return_value = MagicMock(body_text="pick draft")
        outbound = handle_submit_for_approval_request(_conv(), _deliverable_context())
        mock_start.assert_called_once()
        self.assertEqual(outbound.body_text, "pick draft")

    @patch("ai_workplace.services.deliverables.start_submit_saved_deliverable")
    def test_handle_submit_for_approval_request_uses_saved_doc(self, mock_saved):
        mock_saved.return_value = MagicMock(body_text="saved submit")
        conv = _conv(draft_payload=json.dumps({"saved_doc": "CD-001"}))
        outbound = handle_submit_for_approval_request(conv, _deliverable_context())
        mock_saved.assert_called_once()
        self.assertEqual(outbound.body_text, "saved submit")

    def test_is_draft_deliverable(self):
        self.assertTrue(_is_draft_deliverable({"docstatus": 0, "workflow_state": "Draft"}))
        self.assertTrue(_is_draft_deliverable({"docstatus": 0, "status": "Draft"}))
        self.assertFalse(_is_draft_deliverable({"docstatus": 0, "workflow_state": "Sent For Approval"}))

    def test_resolve_pick_supports_interactive_id(self):
        options = [{"name": "CD-001"}, {"name": "CD-002"}]
        self.assertEqual(_resolve_pick("dlv_pick_1", options)["name"], "CD-002")

    @patch("ai_workplace.services.deliverables.frappe.get_all")
    def test_status_lists_records(self, mock_get_all):
        mock_get_all.return_value = [
            {
                "name": "EMP-DLV-01-Sep-2026-1",
                "from_date": "2026-09-01",
                "to_date": "2026-09-30",
                "total_amount": 50000,
                "workflow_state": "Draft",
                "status": "Draft",
                "modified": "2026-09-15",
            }
        ]
        text = build_deliverable_status_response(_deliverable_context())
        self.assertIn("My Deliverables", text)
        self.assertIn("EMP-DLV-01-Sep-2026-1", text)
        self.assertIn("Draft", text)

    def test_status_denied_for_permanent_staff(self):
        text = build_deliverable_status_response(_permanent_context())
        self.assertIn("Contract (Deliverable)", text)

    @patch("ai_workplace.services.deliverables._save_draft")
    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_add_flow_parses_from_date(self, _mock_update, mock_save):
        draft = {"step": "awaiting_from_date", "employee": "EMP-DLV-01", "lines": []}
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_message(conv, "2026-09-01", _deliverable_context())
        self.assertIn("To Date", outbound.body_text)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["step"], "awaiting_to_date")
        self.assertEqual(saved["from_date"], "2026-09-01")

    @patch("ai_workplace.services.deliverables._save_draft")
    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_add_flow_amount_prompts_for_attachment(self, _mock_update, mock_save):
        draft = {
            "step": "awaiting_line_amount",
            "employee": "EMP-DLV-01",
            "lines": [],
            "pending_line": {"deliverable": "Monthly report"},
        }
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_message(conv, "50000", _deliverable_context())
        self.assertIn("attachment", outbound.body_text.lower())
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["step"], "awaiting_line_attachment")
        self.assertEqual(saved["pending_line"]["amount"], 50000)

    @patch("ai_workplace.services.deliverables._save_draft")
    def test_add_attachment_accepts_supported_file(self, mock_save):
        draft = {
            "step": "awaiting_line_attachment",
            "employee": "EMP-DLV-01",
            "lines": [],
            "pending_line": {"deliverable": "Monthly report", "amount": 50000},
        }
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_attachment(
            conv,
            _deliverable_context(),
            "/files/report.pdf",
            filename="report.pdf",
        )
        self.assertIn("Attachment saved", outbound.body_text)
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["step"], "awaiting_more_lines")
        self.assertEqual(len(saved["lines"]), 1)
        self.assertEqual(saved["lines"][0]["attachment"], "/files/report.pdf")

    def test_add_attachment_rejects_unsupported_file(self):
        draft = {
            "step": "awaiting_line_attachment",
            "employee": "EMP-DLV-01",
            "lines": [],
            "pending_line": {"deliverable": "Monthly report", "amount": 50000},
        }
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_attachment(
            conv,
            _deliverable_context(),
            "/files/report.exe",
            filename="report.exe",
        )
        self.assertIn("Unsupported file type", outbound.body_text)

    def test_is_awaiting_deliverable_attachment(self):
        conv = _conv(
            current_intent="deliverable_add",
            draft_payload=json.dumps({"step": "awaiting_line_attachment"}),
        )
        self.assertTrue(is_awaiting_deliverable_attachment(conv))

    @patch("ai_workplace.services.deliverables._create_consultant_deliverable", return_value="CD-001")
    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_add_confirm_offers_submit_after_save(self, mock_update, _mock_create):
        draft = {
            "step": "awaiting_confirm",
            "employee": "EMP-DLV-01",
            "from_date": "2026-09-01",
            "to_date": "2026-09-30",
            "lines": [
                {
                    "deliverable": "Report writing",
                    "amount": 50000,
                    "attachment": "/files/report.pdf",
                    "attachment_filename": "report.pdf",
                }
            ],
        }
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_message(conv, "dlv_save", _deliverable_context())
        self.assertIn("Deliverable Saved", outbound.body_text)
        self.assertTrue(outbound.is_interactive())
        buttons = outbound.interactive["action"]["buttons"]
        self.assertEqual(buttons[0]["reply"]["id"], "dlv_submit_now")
        self.assertEqual(buttons[1]["reply"]["id"], "svc_main_menu")
        saved_payload = json.loads(mock_update.call_args.kwargs["draft_payload"])
        self.assertEqual(saved_payload["saved_doc"], "CD-001")

    @patch("ai_workplace.services.deliverables._begin_submit_confirm")
    def test_start_submit_saved_deliverable_uses_saved_doc(self, mock_begin):
        conv = _conv(draft_payload=json.dumps({"saved_doc": "CD-001"}))
        start_submit_saved_deliverable(conv, _deliverable_context())
        mock_begin.assert_called_once_with(conv, _deliverable_context(), "CD-001")

    def test_post_save_buttons_include_submit_and_menu(self):
        outbound = build_deliverable_post_save_buttons("Saved")
        self.assertTrue(outbound.is_interactive())
        ids = [btn["reply"]["id"] for btn in outbound.interactive["action"]["buttons"]]
        self.assertEqual(ids, ["dlv_submit_now", "svc_main_menu"])

    def test_format_submit_error_uses_exception_class_when_message_empty(self):
        self.assertEqual(_format_submit_error(PermissionError()), "PermissionError")

    @patch("frappe.model.workflow.get_transitions")
    def test_resolve_submit_workflow_action_prefers_exact_action(self, mock_transitions):
        mock_transitions.return_value = [
            {"action": "Send for Approval"},
            {"action": "Approve"},
        ]
        doc = MagicMock()
        self.assertEqual(_resolve_submit_workflow_action(doc), "Send for Approval")

    @patch("frappe.model.workflow.apply_workflow")
    @patch("ai_workplace.services.deliverables._resolve_submit_workflow_action", return_value="Send for Approval")
    @patch("ai_workplace.services.deliverables.frappe.get_doc")
    @patch("ai_workplace.services.deliverables.frappe.set_user")
    @patch("ai_workplace.services.deliverables.frappe.db.commit")
    def test_submit_deliverable_uses_admin_workflow(
        self,
        _mock_commit,
        mock_set_user,
        mock_get_doc,
        _mock_action,
        mock_apply_workflow,
    ):
        doc = MagicMock()
        doc.employee = "EMP-DLV-01"
        doc.docstatus = 0
        doc.workflow_state = "Draft"
        doc.status = "Draft"
        doc.deliverables = [MagicMock()]
        mock_get_doc.return_value = doc

        _submit_deliverable_for_approval("CD-001", {"employee": "EMP-DLV-01"})
        mock_set_user.assert_any_call("Administrator")
        mock_apply_workflow.assert_called_once_with(doc, "Send for Approval")

    @patch("ai_workplace.services.deliverables._create_consultant_deliverable", return_value="CD-001")
    @patch("ai_workplace.services.deliverables._save_draft")
    @patch("ai_workplace.services.deliverables.update_conversation")
    def test_add_confirm_creates_draft(self, mock_update, _mock_save, _mock_create):
        draft = {
            "step": "awaiting_confirm",
            "employee": "EMP-DLV-01",
            "from_date": "2026-09-01",
            "to_date": "2026-09-30",
            "lines": [
                {
                    "deliverable": "Report writing",
                    "amount": 50000,
                    "attachment": "/files/report.pdf",
                    "attachment_filename": "report.pdf",
                }
            ],
        }
        conv = _conv(draft_payload=json.dumps(draft))
        outbound = handle_deliverable_add_message(conv, "dlv_save", _deliverable_context())
        self.assertIn("Deliverable Saved", outbound.body_text)
        self.assertIn("CD-001", outbound.body_text)
        mock_update.assert_called()