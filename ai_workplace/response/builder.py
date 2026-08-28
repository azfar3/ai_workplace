"""
ai_workplace/response/builder.py
───────────────────────────────────
Response Builder — Phase 2.

Centralizes response templates for English, Urdu, and Roman Urdu.
Ensures consistent WhatsApp formatting and dynamic menu generation.
"""

from __future__ import annotations

from typing import Any, Sequence

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def build_welcome_menu_response(
    context: dict[str, Any],
    service_items: Sequence[dict[str, Any]],
) -> str:
    """
    Build welcome message and dynamic menu string based on user context and service list.
    """
    lang = context.get("preferred_language", "English")
    full_name = context.get("full_name") or ""
    person_type = context.get("person_type", "Guest")

    if person_type == "Guest" or not full_name:
        greeting = _get_generic_greeting(lang)
    else:
        greeting = _get_personalized_greeting(full_name, lang)

    menu_lines = []
    for idx, item in enumerate(service_items):
        emoji = NUMBER_EMOJIS[idx] if idx < len(NUMBER_EMOJIS) else f"{idx + 1}."
        title = _translate_service_title(item["key"], item["title"], lang)
        menu_lines.append(f"{emoji} {title}")

    menu_text = "\n".join(menu_lines)

    if lang == "Urdu":
        header = f"{greeting}\n\nآپ کی کیا مدد کی جا سکتی ہے؟\n\n{menu_text}"
    elif lang == "Roman Urdu":
        header = f"{greeting}\n\nMain aap ki kya madad kar sakta hoon?\n\n{menu_text}"
    else:
        header = f"{greeting}\n\nHow can I help you?\n\n{menu_text}"

    return header.strip()


def build_invalid_selection_response(
    context: dict[str, Any],
    service_items: Sequence[dict[str, Any]],
) -> str:
    """Build response for invalid menu selection, followed by refreshed menu."""
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        error_msg = "معذرت، میں آپ کا انتخاب نہیں سمجھ سکا۔\n\nبراہ کرم دستیاب اختیارات میں سے منتخب کریں۔"
    elif lang == "Roman Urdu":
        error_msg = "I didn't recognize that option.\n\nPlease choose one of the available options."
    else:
        error_msg = "I didn't recognize that option.\n\nPlease choose one of the available options."

    menu_str = build_welcome_menu_response(context, service_items)
    return f"{error_msg}\n\n{menu_str}"


def build_cancellation_response(context: dict[str, Any]) -> str:
    """Build response when user issues 'cancel' command."""
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        return "عمل منسوخ کر دیا گیا۔ مینو دیکھنے کے لیے 'menu' لکھیے۔"
    elif lang == "Roman Urdu":
        return "Operation cancel ho gaya. Menu dekhne ke liye 'menu' likhein."
    return "Operation cancelled.\n\nType 'menu' to view options."


def build_unauthorized_response(context: dict[str, Any]) -> str:
    """Build response when user requests an unauthorized service."""
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        return "آپ کے پاس اس سروس تک رسائی کی اجازت نہیں ہے۔"
    elif lang == "Roman Urdu":
        return "Aap ko is service tak rasai ki ijazat nahi hai."
    return "You do not have access to this service."


def build_service_placeholder_response(
    service_key: str,
    context: dict[str, Any],
) -> str:
    """Build placeholder response for Phase 2 navigation-only services."""
    lang = context.get("preferred_language", "English")

    placeholders = {
        "hr": {
            "English": "HR service selected.\n\nHR services will be available here.",
            "Urdu": "ایچ آر سروس منتخب کی گئی۔ ایچ آر سروسز جلد دستیاب ہوں گی۔",
            "Roman Urdu": "HR service selected. HR services yahan dastiyab hongi.",
        },
        "policy": {
            "English": "Policy assistance is being prepared.",
            "Urdu": "پالیسی کی معلومات تیار کی جا رہی ہیں۔",
            "Roman Urdu": "Policy assistance tayyar ki ja rahi hai.",
        },
        "travel": {
            "English": "Travel service selected.\n\nTravel services will be available here.",
            "Urdu": "ٹریول سروس منتخب کی گئی۔ ٹریول سروسز جلد دستیاب ہوں گی۔",
            "Roman Urdu": "Travel service selected. Travel services yahan dastiyab hongi.",
        },
        "consultant": {
            "English": "My Work selected.\n\nConsultant services will be available here.",
            "Urdu": "مائی ورک منتخب کیا گیا۔ کنسلٹنٹ سروسز جلد دستیاب ہوں گی۔",
            "Roman Urdu": "My Work select ho gaya. Consultant services yahan dastiyab hongi.",
        },
    }

    svc_dict = placeholders.get(service_key.lower(), {})
    return svc_dict.get(lang, svc_dict.get("English", f"{service_key.title()} service selected."))


def build_help_response(
    context: dict[str, Any],
    service_items: Sequence[dict[str, Any]],
) -> str:
    """Build deterministic help response detailing available menu options."""
    lang = context.get("preferred_language", "English")

    lines = ["You can use the menu to access available workplace services.\n\nReply with:"]
    for idx, item in enumerate(service_items):
        title = _translate_service_title(item["key"], item["title"], lang)
        lines.append(f"{idx + 1} for {title}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Internal Translation Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_personalized_greeting(name: str, lang: str) -> str:
    if lang == "Urdu":
        return f"خوش آمدید {name}! 👋"
    elif lang == "Roman Urdu":
        return f"Khushamdeed {name}! 👋"
    return f"Welcome {name}! 👋"


def _get_generic_greeting(lang: str) -> str:
    if lang == "Urdu":
        return "ہیلو! 👋\n\nخوش آمدید۔"
    elif lang == "Roman Urdu":
        return "Hello! 👋\n\nKhushamdeed."
    return "Hello! 👋\n\nWelcome."


def _translate_service_title(key: str, default_title: str, lang: str) -> str:
    if lang == "Urdu":
        translations = {
            "hr": "مائی ایچ آر",
            "policy": "میری پالیسیاں",
            "travel": "میرا سفر",
            "consultant": "مرا کام",
            "help": "مدد",
        }
        return translations.get(key.lower(), default_title)
    elif lang == "Roman Urdu":
        translations = {
            "hr": "My HR",
            "policy": "My Policies",
            "travel": "My Travel",
            "consultant": "My Work",
            "help": "Help",
        }
        return translations.get(key.lower(), default_title)
    return default_title
