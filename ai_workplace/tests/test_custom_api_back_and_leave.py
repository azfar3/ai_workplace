"""
ai_workplace/tests/test_custom_api_back_and_leave.py
────────────────────────────────────────────────────
Unit tests verifying:
1. Leave balance calculation using mm_app.overrides.hr.leave_application.get_leave_balance_on
2. Custom Baileys API interactive consolidation and back to parent menu routing in all cases
"""

import unittest
from unittest.mock import patch, MagicMock
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.services.response_helpers import wrap_with_parent_menu
from ai_workplace.whatsapp.sender import _consolidate_custom_api_interactive, _transform_to_baileys
from ai_workplace.whatsapp.payload_parser import parse_webhook_payload


class TestLeaveBalanceWithMMApp(unittest.TestCase):
    @patch("frappe.db.exists", return_value=True)
    @patch("frappe.db.get_all")
    def test_get_leave_balance_data_uses_mm_app(self, mock_get_all, mock_exists):
        from ai_workplace.services.attendance_leave import get_leave_balance_data

        # 1. Allocation: Annual Leave (20 days allocated)
        mock_get_all.side_effect = [
            [{"leave_type": "Annual Leave", "total_leaves_allocated": 20.0, "from_date": "2026-07-01", "to_date": "2027-06-30"}],
            # Applications in tenure: 4 approved
            [{"name": "LAP-1", "total_leave_days": 4.0, "status": "Approved", "docstatus": 1, "from_date": "2026-08-01", "to_date": "2026-08-04"}],
            # No unallocated leaves
            [],
        ]

        with patch("mm_app.overrides.hr.leave_application.get_leave_balance_on") as mock_mm_bal:
            mock_mm_bal.return_value = 16.0

            res = get_leave_balance_data("EMP-001", ref_date="2026-10-19")

            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["leave_type"], "Annual Leave")
            self.assertEqual(res[0]["allocated"], "20.0")
            self.assertEqual(res[0]["taken"], "4.0")
            self.assertEqual(res[0]["remaining"], "16.0")
            self.assertEqual(res[0]["remaining_leaves"], 16.0)

            # Assert mock was called with employee EMP-001 and Annual Leave
            mock_mm_bal.assert_called()
            call_kwargs = mock_mm_bal.call_args[1]
            self.assertEqual(call_kwargs["employee"], "EMP-001")
            self.assertEqual(call_kwargs["leave_type"], "Annual Leave")
            self.assertEqual(call_kwargs["date"], "2026-10-19")


class TestCustomAPIBackAndParentMenu(unittest.TestCase):
    def setUp(self):
        self.context = {
            "employee": "EMP-001",
            "preferred_language": "English",
        }

    def test_consolidate_custom_api_interactive_merges_single_return_button(self):
        outbound = wrap_with_parent_menu("📊 Your Leave Summary...", self.context, "attendance_leave")
        self.assertEqual(len(outbound.follow_up), 1)
        self.assertFalse(outbound.is_interactive())

        _consolidate_custom_api_interactive(outbound)

        self.assertEqual(len(outbound.follow_up), 0)
        self.assertTrue(outbound.is_interactive())
        self.assertIn("📊 Your Leave Summary...", outbound.interactive["body"]["text"])
        self.assertIn("open the previous menu", outbound.interactive["body"]["text"])

    @patch("frappe.cache")
    def test_transform_to_baileys_numbers_from_one_and_maps_aliases(self, mock_cache):
        cache_dict = {}
        mock_cache_inst = MagicMock()
        mock_cache_inst.set_value.side_effect = lambda k, v, **kw: cache_dict.update({k: v})
        mock_cache_inst.get_value.side_effect = lambda k: cache_dict.get(k)
        mock_cache.return_value = mock_cache_inst

        outbound = wrap_with_parent_menu("Test Body", self.context, "attendance_leave")
        _consolidate_custom_api_interactive(outbound)

        baileys_payload = _transform_to_baileys(
            {
                "to": "+923001234567",
                "type": "interactive",
                "interactive": outbound.interactive,
            }
        )

        # Message must contain option 1
        self.assertIn("1. Attendance & Leave", baileys_payload["message"])

        # Cache must map 1, Back, 0, wapas, and title
        stored = cache_dict.get("custom_wa_menu_923001234567", {}).get("map", {})
        self.assertEqual(stored.get("1"), "svc_attendance_leave")
        self.assertEqual(stored.get("1."), "svc_attendance_leave")
        self.assertEqual(stored.get("back"), "svc_attendance_leave")
        self.assertEqual(stored.get("Back"), "svc_attendance_leave")
        self.assertEqual(stored.get("0"), "svc_attendance_leave")
        self.assertEqual(stored.get("wapas"), "svc_attendance_leave")
        self.assertEqual(stored.get("attendance & leave"), "svc_attendance_leave")

    @patch("frappe.cache")
    def test_payload_parser_resolves_menu_and_back_options(self, mock_cache):
        cache_store = {
            "custom_wa_menu_923001234567": {
                "map": {
                    "1": "svc_attendance_leave",
                    "back": "svc_attendance_leave",
                    "0": "svc_attendance_leave",
                    "attendance & leave": "svc_attendance_leave",
                }
            }
        }
        mock_cache_inst = MagicMock()
        mock_cache_inst.get_value.side_effect = lambda k: cache_store.get(k)
        mock_cache_inst.delete_value.side_effect = lambda k: cache_store.pop(k, None)
        mock_cache.return_value = mock_cache_inst

        # Test sending "1"
        res1 = parse_webhook_payload({"number": "923001234567", "message": "1"})
        self.assertEqual(res1["text"], "svc_attendance_leave")

        # Test sending "back"
        cache_store["custom_wa_menu_923001234567"] = {
            "map": {"back": "svc_attendance_leave", "0": "svc_attendance_leave"}
        }
        res2 = parse_webhook_payload({"number": "923001234567@s.whatsapp.net", "message": "back"})
        self.assertEqual(res2["text"], "svc_attendance_leave")

        # Test sending "0"
        cache_store["custom_wa_menu_923001234567"] = {
            "map": {"back": "svc_attendance_leave", "0": "svc_attendance_leave"}
        }
        res3 = parse_webhook_payload({"number": "+923001234567", "message": "0"})
        self.assertEqual(res3["text"], "svc_attendance_leave")
