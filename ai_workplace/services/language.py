"""
ai_workplace/services/language.py
──────────────────────────────────
Language selection — BRD Section 14.2 / BR-17.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe

from ai_workplace.whatsapp.outbound import OutboundMessage


SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {"code": "en", "canonical": "English", "button_title": "English", "button_id": "lang_en"},
    {"code": "ur", "canonical": "Urdu", "button_title": "Urdu", "button_id": "lang_ur"},
    {
        "code": "roman_urdu",
        "canonical": "Roman Urdu",
        "button_title": "Roman Urdu",
        "button_id": "lang_roman",
    },
]

_LANG_ALIASES: dict[str, str] = {}
for _lang in SUPPORTED_LANGUAGES:
    _LANG_ALIASES[_lang["button_id"]] = _lang["canonical"]
    _LANG_ALIASES[_lang["canonical"].lower()] = _lang["canonical"]
    _LANG_ALIASES[_lang["code"]] = _lang["canonical"]

# Explicit aliases including numbered list choices (1. English, 2. Urdu, 3. Roman Urdu)
_ADDITIONAL_ALIASES: dict[str, str] = {
    "1": "English",
    "1.": "English",
    "1۔": "English",
    "1️⃣": "English",
    "۱": "English",
    "eng": "English",
    "english": "English",
    "angrezi": "English",
    "2": "Urdu",
    "2.": "Urdu",
    "2۔": "Urdu",
    "2️⃣": "Urdu",
    "۲": "Urdu",
    "urdu": "Urdu",
    "اردو": "Urdu",
    "3": "Roman Urdu",
    "3.": "Roman Urdu",
    "3۔": "Roman Urdu",
    "3️⃣": "Roman Urdu",
    "۳": "Roman Urdu",
    "roman": "Roman Urdu",
    "roman urdu": "Roman Urdu",
    "roman_urdu": "Roman Urdu",
}
_LANG_ALIASES.update(_ADDITIONAL_ALIASES)


def parse_language_selection(user_input: str) -> Optional[str]:
    """
    Parse language choice from button id, menu number (1, 2, 3), or free text.
    Returns canonical language name (English / Urdu / Roman Urdu) or None.
    """
    if not user_input:
        return None
    clean = user_input.strip().lower()
    if clean in _LANG_ALIASES:
        return _LANG_ALIASES[clean]

    clean_stripped = clean.rstrip(".").rstrip("۔").strip()
    if clean_stripped in _LANG_ALIASES:
        return _LANG_ALIASES[clean_stripped]

    normalized = clean.replace("_", " ")
    if normalized in _LANG_ALIASES:
        return _LANG_ALIASES[normalized]

    normalized_stripped = clean_stripped.replace("_", " ")
    if normalized_stripped in _LANG_ALIASES:
        return _LANG_ALIASES[normalized_stripped]

    # Handle digit extraction if user typed e.g. "option 1" or "#1"
    digit_trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    digit_clean = clean.translate(digit_trans)
    import re
    match = re.search(r"\b([1-3])\b", digit_clean)
    if match:
        digit = match.group(1)
        return {"1": "English", "2": "Urdu", "3": "Roman Urdu"}.get(digit)

    return None


def persist_language(
    *,
    whatsapp_identity: str,
    language: str,
    conversation: Optional[Any] = None,
) -> None:
    """Save preferred language to WhatsApp Identity and active conversation."""
    code = canonical_to_code(language)
    if whatsapp_identity and frappe.db.exists("WhatsApp Identity", whatsapp_identity):
        frappe.db.set_value(
            "WhatsApp Identity",
            whatsapp_identity,
            "preferred_language",
            code,
        )
    if conversation is not None:
        conversation.preferred_language = language
        conversation.flags.ignore_links = True
        conversation.save(ignore_permissions=True)
    frappe.db.commit()


def canonical_to_code(language: str) -> str:
    for lang in SUPPORTED_LANGUAGES:
        if lang["canonical"] == language:
            return lang["code"]
    return "en"


def auto_detect_language(text: str) -> str:
    """Auto-detect language based on characters and keywords."""
    if not text:
        return "English"
    clean = text.lower()
    
    # Check for Arabic/Urdu script block
    urdu_chars = [chr(i) for i in range(0x0600, 0x06FF)]
    if any(c in clean for c in urdu_chars):
        return "Urdu"
        
    # Check for common Roman Urdu words
    roman_keywords = {"kese", "kya", "hai", "hain", "karna", "nahi", "bhi", "tha", "thi", "liye", "mein", "mera", "meri", "hum", "kia", "ko", "se", "kaise"}
    words = set(clean.split())
    if any(kw in words for kw in roman_keywords):
        return "Roman Urdu"
        
    return "English"



def build_language_selection_message(
    context: dict[str, Any],
    welcome_text: Optional[str] = None,
) -> OutboundMessage:
    """Build interactive reply-button message for language selection."""
    lang = context.get("preferred_language", "English")
    prompt = _language_prompt_text(lang)
    body = f"{welcome_text}\n\n{prompt}" if welcome_text else prompt

    buttons = [
        {
            "type": "reply",
            "reply": {"id": item["button_id"], "title": item["button_title"]},
        }
        for item in SUPPORTED_LANGUAGES
    ]

    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": buttons},
    }

    person_type = context.get("person_type", "Guest")
    image_url = context.get("image_url")
    if person_type in ("Employee", "Consultant", "Former Employee", "Inactive") and image_url:
        interactive["header"] = {
            "type": "image",
            "image": {"link": image_url},
        }

    return OutboundMessage(body_text=body, interactive=interactive)



def build_language_saved_message(language: str, context: dict[str, Any]) -> str:
    """Confirmation after language change — employee-first, no profile nudges."""
    person_type = context.get("person_type", "Guest")
    if person_type in ("Employee", "Consultant"):
        if language == "Urdu":
            return (
                "✅ اردو منتخب کر لی گئی۔\n\n"
                "*آج ہم آپ کی کیا مدد کر سکتے ہیں؟*\n\n"
                "نیچے سے سروس منتخب کریں۔ آپ \"تنخواہ\"، \"رخصت\"، \"حاضری\"، \"سفر\" یا \"ایچ آر\" بھی لکھ سکتے ہیں۔"
            )
        if language == "Roman Urdu":
            return (
                "✅ Roman Urdu select ho gayi.\n\n"
                "*Aaj hum aap ki kya madad kar sakte hain?*\n\n"
                "Neeche se service choose karein. Aap \"salary slip\", \"leave\", \"attendance\", \"travel\" ya \"HR\" bhi likh sakte hain."
            )
        return (
            "✅ English selected.\n\n"
            "*How can we help you today?*\n\n"
            "Choose a service below. You can also type common requests such as "
            "\"salary slip\", \"leave\", \"attendance\", \"travel\" or \"HR\"."
        )

    if language == "Urdu":
        return "✅ زبان اردو منتخب کر لی گئی ہے۔"
    if language == "Roman Urdu":
        return f"✅ Zaban {language} select ho gayi hai."
    return f"✅ Language set to {language}."


def _language_prompt_text(lang: str) -> str:
    if lang == "Urdu":
        return "براہ کرم اپنی پسندیدہ زبان منتخب کریں:"
    if lang == "Roman Urdu":
        return "Barah-e-karam apni pasandeeda zuban intekhab karein:"
    return "Please choose your preferred language:"
