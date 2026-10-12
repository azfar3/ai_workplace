import unittest
from ai_workplace.response.builder import build_help_response, _translate_service_title, _translate_service_description
from ai_workplace.whatsapp.interactive import (
    build_leave_type_list_message,
)
from ai_workplace.whatsapp.sender import _transform_to_baileys
from ai_workplace.services.language import build_language_saved_message
from ai_workplace.conversation.menu import build_menu


class TestUrduFormatting(unittest.TestCase):
    def test_translation_helpers(self):
        t1 = _translate_service_title("attendance_leave", "Attendance & Leave", "Urdu")
        d1 = _translate_service_description("attendance_leave", "Check in/out, view attendance", "Urdu")
        self.assertIn("حاضری", t1)
        self.assertIn("تفصیلات", d1)

    def test_help_response_urdu_formatting(self):
        items = [
            {"key": "attendance_leave", "title": "Attendance & Leave"},
            {"key": "payroll", "title": "Salary & Payroll"},
        ]
        help_resp = build_help_response({"preferred_language": "Urdu", "person_type": "Employee"}, items)
        self.assertIn("1️⃣", help_resp)
        self.assertIn("حاضری", help_resp)

    def test_menu_interactive_urdu(self):
        menu_out, _ = build_menu({"preferred_language": "Urdu", "person_type": "Employee", "user_category": "Active Employee"})
        self.assertIn(menu_out.interactive["action"]["button"], ("مینو کھولیں", "سروسز دیکھیں"))

    def test_baileys_transformer_urdu_list(self):
        menu_out, _ = build_menu({"preferred_language": "Urdu", "person_type": "Employee", "user_category": "Active Employee"})
        list_target = menu_out.follow_up[0] if getattr(menu_out, "follow_up", None) else menu_out
        payload = {
            "to": "923001234567",
            "type": "interactive",
            "interactive": list_target.interactive,
        }
        baileys_out = _transform_to_baileys(payload)
        msg = baileys_out["message"]
        self.assertIn("1️⃣", msg)
        self.assertIn(" — ", msg)
        self.assertNotIn("1.", msg)

    def test_baileys_transformer_urdu_buttons(self):
        btn_interactive = {
            "type": "button",
            "body": {"text": "براہ کرم انتخاب کریں:"},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "chat_hr", "title": "ایچ آر سے بات کریں"}},
                    {"type": "reply", "reply": {"id": "main_menu", "title": "اصلی مینو"}},
                ]
            }
        }
        btn_payload = {
            "to": "923001234567",
            "type": "interactive",
            "interactive": btn_interactive,
        }
        baileys_btn_out = _transform_to_baileys(btn_payload)
        msg = baileys_btn_out["message"]
        self.assertIn("1️⃣", msg)
        self.assertIn("2️⃣", msg)
        self.assertNotIn("1.", msg)

    def test_leave_type_list_message(self):
        leave_types = [
            {"leave_type": "Casual Leave", "remaining": 10},
            {"leave_type": "Sick Leave", "remaining": 8},
        ]
        lt_msg = build_leave_type_list_message({"preferred_language": "Urdu"}, leave_types, "چھٹی کی قسم منتخب کریں")
        self.assertEqual(lt_msg.interactive["action"]["button"], "چھٹی منتخب کریں")
        self.assertIn("باقی بیلنس: 10 دن", lt_msg.interactive["action"]["sections"][0]["rows"][0]["description"])

    def test_language_saved_message(self):
        lang_saved = build_language_saved_message("Urdu", {"preferred_language": "Urdu", "person_type": "Employee"})
        self.assertIn("ایچ آر", lang_saved)
        self.assertNotIn("HR", lang_saved)


def run():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUrduFormatting)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("Tests failed")

