"""
Tests for WhatsApp location attendance service.
"""

from __future__ import annotations

import json
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.attendance_location import (
    get_today_checkin_state,
    validate_geofence,
    validate_live_location_share,
    validate_pending_request,
)


class TestValidatePendingRequest(unittest.TestCase):
    def test_valid_within_ttl(self):
        draft = {"pending_started_at": str(frappe.utils.now_datetime())}
        ok, msg = validate_pending_request(draft)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    @patch("ai_workplace.services.attendance_location.get_whatsapp_attendance_settings")
    def test_expired_request(self, mock_settings):
        mock_settings.return_value = {"pending_ttl_minutes": 10}
        old = frappe.utils.now_datetime() - timedelta(minutes=15)
        draft = {"pending_started_at": str(old)}
        ok, msg = validate_pending_request(draft)
        self.assertFalse(ok)
        self.assertIn("expired", msg.lower())


class TestValidateGeofence(unittest.TestCase):
    def test_no_mobile_attendance_skips_geofence(self):
        result = validate_geofence(33.6900, 73.0600, None)
        self.assertTrue(result["inside"])
        self.assertEqual(result["geofence_result"], "Not Required")

    def test_inside_geofence(self):
        ma = {
            "geofence_is_must": 1,
            "lat": "33.6844",
            "lang": "73.0479",
            "radius": 200,
            "name1": "Islamabad Office",
        }
        result = validate_geofence(33.68445, 73.04795, ma)
        self.assertTrue(result["inside"])
        self.assertEqual(result["geofence_result"], "Inside")

    def test_outside_geofence(self):
        ma = {
            "geofence_is_must": 1,
            "lat": "33.6844",
            "lang": "73.0479",
            "radius": 50,
            "name1": "Islamabad Office",
        }
        result = validate_geofence(33.6900, 73.0600, ma)
        self.assertFalse(result["inside"])
        self.assertEqual(result["geofence_result"], "Outside")

    def test_geofence_not_required(self):
        ma = {"geofence_is_must": 0, "name1": "Field"}
        result = validate_geofence(33.0, 73.0, ma)
        self.assertTrue(result["inside"])
        self.assertEqual(result["geofence_result"], "Not Required")


class TestPayloadParserLocation(unittest.TestCase):
    def test_parse_location_message(self):
        from ai_workplace.whatsapp.payload_parser import _parse_message

        msg = {
            "type": "location",
            "from": "923001234567",
            "id": "wamid.test123",
            "timestamp": "1234567890",
            "context": {"from": "15550001111", "id": "wamid.context123"},
            "location": {
                "latitude": 33.6844,
                "longitude": 73.0479,
                "name": "Islamabad Office",
                "address": "Test Address",
            },
        }
        value = {"metadata": {"phone_number_id": "123"}, "contacts": [{"wa_id": "923001234567"}]}
        parsed = _parse_message(msg, value)
        self.assertEqual(parsed["message_type"], "location")
        self.assertEqual(parsed["latitude"], 33.6844)
        self.assertEqual(parsed["longitude"], 73.0479)
        self.assertEqual(parsed["location_name"], "Islamabad Office")
        self.assertEqual(parsed["context_message_id"], "wamid.context123")


class TestAttendanceEligibility(unittest.TestCase):
    @patch("ai_workplace.services.attendance_location.get_whatsapp_attendance_settings")
    @patch("ai_workplace.services.attendance_location.frappe.db.get_value")
    def test_not_eligible_no_attendance(self, mock_get_value, mock_settings):
        mock_settings.return_value = {"enabled": True}
        mock_get_value.return_value = frappe._dict(
            name="EMP-1",
            status="Active",
            no_attendance=1,
            user_id="user@test.com",
            mobile_attendance=None,
            employee_name="Test",
        )
        from ai_workplace.services.attendance_location import get_attendance_eligibility

        result = get_attendance_eligibility("EMP-1", user_id="user@test.com")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["mode"], "No Attendance Required")

    @patch("ai_workplace.services.attendance_location.employee_can_mark_checkin")
    @patch("ai_workplace.services.attendance_location.get_whatsapp_attendance_settings")
    @patch("ai_workplace.services.attendance_location.frappe.db.get_value")
    def test_eligible_with_checkin_permission_no_mobile_attendance(
        self, mock_get_value, mock_settings, mock_can_checkin
    ):
        mock_settings.return_value = {"enabled": True}
        mock_get_value.return_value = frappe._dict(
            name="EMP-1",
            status="Active",
            no_attendance=0,
            user_id="user@test.com",
            mobile_attendance=None,
            employee_name="Test",
        )
        mock_can_checkin.return_value = True
        from ai_workplace.services.attendance_location import get_attendance_eligibility

        result = get_attendance_eligibility("EMP-1", user_id="user@test.com")
        self.assertTrue(result["eligible"])
        self.assertIsNone(result["mobile_attendance"])

    @patch("ai_workplace.services.attendance_location.employee_can_mark_checkin")
    @patch("ai_workplace.services.attendance_location.get_whatsapp_attendance_settings")
    @patch("ai_workplace.services.attendance_location.frappe.db.get_value")
    def test_not_eligible_without_checkin_permission(
        self, mock_get_value, mock_settings, mock_can_checkin
    ):
        mock_settings.return_value = {"enabled": True}
        mock_get_value.return_value = frappe._dict(
            name="EMP-1",
            status="Active",
            no_attendance=0,
            user_id="user@test.com",
            mobile_attendance=None,
            employee_name="Test",
        )
        mock_can_checkin.return_value = False
        from ai_workplace.services.attendance_location import get_attendance_eligibility

        result = get_attendance_eligibility("EMP-1", user_id="user@test.com")
        self.assertFalse(result["eligible"])
        self.assertIn("permission", result["reason"].lower())


class TestValidateLiveLocationShare(unittest.TestCase):
    def test_rejects_named_place(self):
        draft = {"location_request_message_id": "wamid.req1"}
        ok, msg = validate_live_location_share(
            {"location_name": "Office", "location_address": ""},
            draft,
            "wamid.req1",
        )
        self.assertFalse(ok)
        self.assertIn("current location", msg.lower())

    def test_rejects_wrong_reply_context(self):
        draft = {"location_request_message_id": "wamid.req1"}
        ok, msg = validate_live_location_share(
            {"location_name": "", "location_address": ""},
            draft,
            "wamid.other",
        )
        self.assertFalse(ok)
        self.assertIn("reply", msg.lower())

    def test_accepts_bare_coordinates_with_matching_context(self):
        draft = {"location_request_message_id": "wamid.req1"}
        ok, msg = validate_live_location_share(
            {"location_name": "", "location_address": ""},
            draft,
            "wamid.req1",
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "")


class TestStartLocationRequest(unittest.TestCase):
    @patch("ai_workplace.services.attendance_location.update_conversation")
    @patch("ai_workplace.services.attendance_location.get_attendance_eligibility")
    @patch("ai_workplace.services.attendance_location.get_today_checkin_state")
    def test_start_checkin(self, mock_state, mock_elig, mock_update):
        mock_elig.return_value = {"eligible": True}
        mock_state.return_value = {"checked_in_open": False, "checked_out_today": False, "has_in_today": False}
        from ai_workplace.services.attendance_location import start_location_request

        conv = MagicMock()
        out = start_location_request(conv, {"employee": "EMP-1"}, "IN")
        self.assertIn("location", out.body_text.lower())
        self.assertTrue(out.is_location_request())
        mock_update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
