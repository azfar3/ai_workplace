"""
Staff Support hub — routes to policies, supervisor, confidential concern, HR chat.
"""

from __future__ import annotations

from typing import Any

from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.whatsapp.outbound import OutboundMessage


def build_staff_support_hub(context: dict[str, Any]) -> OutboundMessage:
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = (
            "💙 *ملازمین کی معاونت*\n\n"
            "ہم آپ کی کس طرح مدد کر سکتے ہیں؟\n\n"
            "اگر کام پر کوئی مسئلہ آپ کی کارکردگی متاثر کر رہا ہے تو "
            "یہاں رہنمائی حاصل کریں یا HR سے بات کریں۔"
        )
    elif lang == "Roman Urdu":
        body = (
            "💙 *Staff Support*\n\n"
            "Hum aap ki kis tarah madad kar sakte hain?\n\n"
            "Agar kaam par koi masla aap ki performance affect kar raha hai, "
            "yahan guidance lein ya HR se baat karein."
        )
    else:
        body = (
            "💙 *Staff Support*\n\n"
            "How can we support you?\n\n"
            "If something at work is making it difficult for you to perform your duties, "
            "you can get guidance or speak with HR here.\n\n"
            "Your concern will be handled according to the appropriate HR process."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_staff_hr_guidance", "title": "HR Guidance"},
            {"id": "svc_supervisor_reporting", "title": "Supervisor"},
            {"id": "svc_concerns", "title": "Confidential"},
        ],
    )


def build_staff_support_followup(context: dict[str, Any]) -> OutboundMessage:
    return build_button_message(
        "Need to speak with HR directly?",
        [
            {"id": "svc_contact_hr", "title": "Chat with HR"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )
