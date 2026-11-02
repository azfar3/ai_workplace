"""Isolated guidance tests: no Frappe site or outbound network required."""
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.conversation_guidance import eligible, load_memory, quiet_now
from ai_workplace.whatsapp.outbound import OutboundMessage


class Doc(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value

    def db_set(self, values, **kwargs):
        self.update(values)


class TestGuidance(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 12)
        self.frappe = MagicMock()
        self.frappe.utils.now_datetime.return_value = self.now
        self.frappe.utils.get_datetime.side_effect = lambda v: datetime.fromisoformat(v) if isinstance(v, str) else v
        self.cfg = {"guided_conversations_enabled": 1, "conversation_followups_enabled": 1,
                    "conversation_followup_minutes": 60, "followup_quiet_start": 20, "followup_quiet_end": 9}
        self.frappe.get_single.return_value = self.cfg
        path = Path(__file__).parents[1] / "services" / "conversation_guidance.py"
        spec = importlib.util.spec_from_file_location("isolated_guidance_service", path)
        self.service = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"frappe": self.frappe}):
            spec.loader.exec_module(self.service)
        self.conv = Doc(name="C1", meta=SimpleNamespace(has_field=lambda _: True),
                        wa_id="923001234567", employee="E1", erp_user="user@example.com",
                        conversation_status="Active", current_state="PROCESSING",
                        current_intent="leave_apply", preferred_language="English",
                        draft_payload=json.dumps({"step": "awaiting_from_date", "leave_type": "Annual", "reason": "private"}),
                        expires_at=self.now + timedelta(minutes=60), whatsapp_identity="I1")
        self.context = {"employee": "E1", "user": "user@example.com", "preferred_language": "English"}

    def memory(self):
        return load_memory(self.conv.guidance_memory)

    def track_leave(self):
        self.service.finish_turn(self.conv, self.context, OutboundMessage(body_text="Start date?"))

    def test_malformed_memory(self):
        for value in ("bad", "[]", "null", "123"):
            self.assertEqual(load_memory(value), {})

    def test_quiet_hours_cross_midnight(self):
        for hour, expected in [(0, True), (8, True), (9, False), (19, False), (20, True)]:
            self.assertEqual(quiet_now(self.now.replace(hour=hour), 20, 9), expected)
        self.assertFalse(quiet_now(self.now, 0, 0))
        self.assertTrue(quiet_now(self.now, 9, 17))

    def test_leave_tracks_without_copying_private_reason(self):
        self.track_leave()
        self.assertEqual(self.memory()["details"], {"leave_type": "Annual"})
        self.assertNotIn("private", self.conv.guidance_memory)
        self.assertEqual(self.conv.followup_status, "Pending")
        self.assertGreater(self.conv.expires_at, self.conv.followup_due_at)

    def test_web_never_schedules_whatsapp(self):
        self.conv.wa_id = "WEB-user@example.com"
        self.track_leave()
        self.assertIsNone(self.conv.followup_status)

    def test_disabled_reminders_still_remember_details(self):
        self.cfg["conversation_followups_enabled"] = 0
        self.track_leave()
        self.assertEqual(self.memory()["status"], "awaiting_user")
        self.assertIsNone(self.conv.followup_status)

    def test_disabled_guidance_is_inert(self):
        self.cfg["guided_conversations_enabled"] = 0
        self.track_leave()
        self.assertIsNone(self.conv.guidance_memory)

    def test_inbound_cancels_pending_delivery(self):
        self.track_leave()
        self.service.begin_turn(self.conv, "2026-11-04", self.context)
        self.assertEqual(self.conv.followup_status, "Cancelled")
        self.assertIsNone(self.conv.followup_due_at)

    def test_inbound_also_revokes_claimed_delivery(self):
        self.track_leave()
        self.conv.followup_status = "Claimed"
        self.service.begin_turn(self.conv, "2026-11-04", self.context)
        self.assertEqual(self.conv.followup_status, "Cancelled")

    def test_yes_and_no_reach_existing_leave_confirmation(self):
        self.track_leave()
        for text in ("yes", "no", "leave_submit", "leave_cancel"):
            rewritten, response = self.service.begin_turn(self.conv, text, self.context)
            self.assertEqual(rewritten, text)
            self.assertIsNone(response)

    def test_continue_only_repeats_question(self):
        self.track_leave()
        text, response = self.service.begin_turn(self.conv, "guide_continue", self.context)
        self.assertEqual(text, "guide_continue")
        self.assertIn("start date", response.body_text)
        self.assertEqual(self.conv.current_intent, "leave_apply")

    def test_dismiss_prevents_future_schedule(self):
        self.track_leave()
        self.service.begin_turn(self.conv, "guide_dismiss", self.context)
        self.track_leave()
        self.assertTrue(self.memory()["opted_out"])
        self.assertEqual(self.conv.followup_status, "Cancelled")

    def test_completed_leave_cancels_reminder(self):
        self.track_leave()
        self.conv.current_intent = None
        self.conv.current_state = "AWAITING_SELECTION"
        self.service.finish_turn(self.conv, self.context, OutboundMessage(body_text="Submitted"))
        self.assertEqual(self.memory()["status"], "completed")
        self.assertEqual(self.conv.followup_status, "Cancelled")

    def test_human_chat_has_priority(self):
        self.track_leave()
        self.conv.active_hr_chat_session = "HR1"
        _, response = self.service.begin_turn(self.conv, "guide_continue", self.context)
        self.assertIsNone(response)
        self.assertEqual(self.memory()["status"], "suspended")

    def test_explicit_later_allows_one_more_reminder(self):
        self.track_leave()
        memory = self.memory()
        memory["reminder_sent"] = True
        self.conv.guidance_memory = json.dumps(memory)
        self.service.begin_turn(self.conv, "guide_later", self.context)
        self.assertFalse(self.memory()["reminder_sent"])
        self.assertEqual(self.conv.followup_status, "Pending")

    def test_passive_progress_does_not_send_second_reminder(self):
        self.track_leave()
        memory = self.memory()
        memory["reminder_sent"] = True
        self.conv.guidance_memory = json.dumps(memory)
        self.conv.followup_status = "Sent"
        self.track_leave()
        self.assertEqual(self.conv.followup_status, "Sent")

    def test_policy_without_evidence_has_no_prompt(self):
        for raw in ([], {}, {"error": "unavailable"}, [{"score": 1}]):
            out = OutboundMessage(body_text="No information found.")
            self.service.guide_policy(self.conv, self.context, out, "employee_leave_policy", raw)
            self.assertEqual(out.body_text, "No information found.")
        self.assertIsNone(self.conv.guidance_memory)

    def test_supported_policy_gets_one_question(self):
        out = OutboundMessage(body_text="Approved policy information.", follow_up=[OutboundMessage(body_text="generic")])
        self.service.guide_policy(self.conv, self.context, out, "employee_leave_policy", [{"text": "policy"}])
        self.assertEqual(out.body_text.count("?"), 1)
        self.assertEqual(out.follow_up, [])
        self.assertEqual(self.memory()["intent"], "employee_leave_policy")

    def test_synthesis_question_is_not_duplicated(self):
        out = OutboundMessage(body_text="Which policy section do you need?")
        self.service.guide_policy(self.conv, self.context, out, "employee_leave_policy", [{"text": "policy"}])
        self.assertEqual(out.body_text.count("?"), 1)

    def test_worker_rejects_unsafe_or_stale_delivery(self):
        self.track_leave()
        memory = self.memory()
        due = self.now + timedelta(hours=1)
        self.assertTrue(eligible(self.conv, memory, due))
        self.assertFalse(eligible(self.conv, memory, self.now))
        self.assertFalse(eligible(self.conv, memory, self.now + timedelta(hours=23)))
        for field, value in [("employee", "E2"), ("erp_user", "other@example.com"),
                             ("conversation_status", "Expired"), ("active_hr_chat_session", "HR1"),
                             ("current_intent", None), ("current_state", "WAITING_FOR_SUPPORT_PIN")]:
            conv = dict(self.conv)
            conv[field] = value
            self.assertFalse(eligible(conv, memory, due), field)

    def test_claimed_job_is_not_sent_twice(self):
        self.conv.followup_status = "Claimed"
        self.frappe.get_doc.return_value = self.conv
        self.service._send_one("C1", self.cfg)
        self.frappe.db.get_value.assert_not_called()
        self.frappe.db.commit.assert_called_once()

    def test_no_assigned_policy_does_not_offer_guidance(self):
        out = OutboundMessage(body_text="No policy assigned.")
        self.service.guide_policy(self.conv, self.context, out, "employee_leave_policy", {"has_leave_policy": False})
        self.assertEqual(out.body_text, "No policy assigned.")
        self.assertIsNone(self.conv.guidance_memory)

    def test_new_identity_does_not_resume_old_memory(self):
        self.track_leave()
        self.context["employee"] = "E2"
        _, response = self.service.begin_turn(self.conv, "guide_continue", self.context)
        self.assertIsNone(response)
        self.assertEqual(self.memory(), {})

    def test_media_activity_after_last_question_revokes_delivery(self):
        self.track_leave()
        self.conv.last_activity_at = self.now + timedelta(minutes=15)
        self.assertFalse(eligible(self.conv, self.memory(), self.now + timedelta(hours=1)))

    def test_successful_delivery_is_logged_and_not_retried(self):
        self.track_leave()
        self.frappe.utils.now_datetime.return_value = self.now + timedelta(hours=1)
        self.frappe.get_doc.return_value = self.conv
        identity = SimpleNamespace(status="Active", employee="E1", erp_user="user@example.com", normalized_phone="+923001234567")
        employee = SimpleNamespace(status="Active", user_id="user@example.com")
        def get_value(doctype, name, field, **kwargs):
            if doctype == "Employee":
                return employee
            if doctype == "User":
                return 1
            if doctype == "WhatsApp Identity":
                return "account-1" if field == "receiver_name" else identity
            return self.conv.followup_status
        self.frappe.db.get_value.side_effect = get_value
        send = MagicMock(return_value={"success": True, "message_id": "M1"})
        log = MagicMock()
        modules = {
            "ai_workplace.services.hr_chat": SimpleNamespace(get_active_session_for_identity=lambda **kwargs: None),
            "ai_workplace.whatsapp.interactive": SimpleNamespace(build_button_message=lambda body, buttons: OutboundMessage(body_text=body)),
            "ai_workplace.whatsapp.sender": SimpleNamespace(send_message=send),
            "ai_workplace.api.whatsapp_webhook": SimpleNamespace(_create_message_log=log),
        }
        with patch.dict("sys.modules", modules):
            self.service._send_one("C1", self.cfg)
            self.service._send_one("C1", self.cfg)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["session_name"], "account-1")
        self.assertTrue(self.memory()["reminder_sent"])
        log.assert_called_once()
        self.assertEqual(log.call_args.kwargs["status"], "Sent")

    def test_worker_stays_quiet(self):
        self.frappe.utils.now_datetime.return_value = self.now.replace(hour=22)
        self.service.send_due_followups()
        self.frappe.get_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
