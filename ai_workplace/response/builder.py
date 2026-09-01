"""
ai_workplace/response/builder.py
───────────────────────────────────
Response Builder — Phase 2.

Centralizes response templates for English, Urdu, and Roman Urdu.
Aligned with BRD Appendix B reference messages.
"""

from __future__ import annotations

from typing import Any, Sequence

import frappe


NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


def build_unregistered_response(context: dict[str, Any]) -> str:
    """
    BRD Appendix B.2 — guest, inactive, and ambiguous identities.
    No protected menu; must not reveal whether an employee record exists.
    """
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        return (
            "یہ WhatsApp نمبر MicroMerger self-service کے لیے رجسٹرڈ نہیں ہے۔\n\n"
            "سیکیورٹی وجوہات کی بنا پر، اس نمبر پر ملازم کی معلومات فراہم نہیں کی جا سکتیں۔\n\n"
            "براہ کرم HR سے رابطہ کریں تاکہ آپ کا ذاتی/سرکاری موبائل نمبر اپ ڈیٹ کیا جا سکے۔"
        )
    if lang == "Roman Urdu":
        return (
            "Yeh WhatsApp number MicroMerger self-service ke liye registered nahi hai.\n\n"
            "Security ki wajah se, is number par employee ki maloomat faraham nahi ki ja sakti.\n\n"
            "Barah-e-karam HR se rabta karein taake aap ka personal/official mobile number update ho sake."
        )
    return (
        "This WhatsApp number is not registered for MicroMerger self-service.\n\n"
        "For security, employee information cannot be provided on this number.\n\n"
        "Please contact HR to update your registered personal/official mobile number."
    )


def build_welcome_menu_response(
    context: dict[str, Any],
    service_items: Sequence[dict[str, Any]],
) -> str:
    """
    Build welcome message and dynamic menu string (BRD Appendix B.1).
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
        header = (
            f"{greeting}\n\n"
            f"براہ کرم منتخب کریں:\n\n{menu_text}\n\n"
            f"آپ انگریزی، اردو یا Roman Urdu میں اپنا سوال بھی لکھ سکتے ہیں۔"
        )
    elif lang == "Roman Urdu":
        header = (
            f"{greeting}\n\n"
            f"Barah-e-karam intekhab karein:\n\n{menu_text}\n\n"
            f"Aap English, Urdu ya Roman Urdu mein apna sawal bhi likh sakte hain."
        )
    else:
        header = (
            f"{greeting}\n\n"
            f"Please choose:\n\n{menu_text}\n\n"
            f"You can also type your question in English, Urdu or Roman Urdu."
        )

    return header.strip()


def _employee_first_name(context: dict[str, Any]) -> str:
    first = (context.get("first_name") or "").strip()
    if first:
        return first
    full = (context.get("full_name") or "").strip()
    if full:
        return full.split()[0]
    return ""


def build_welcome_header(context: dict[str, Any]) -> str:
    """Build category-specific welcome header text with bold formatting for Active, Former Employee, and Guest."""
    lang = context.get("preferred_language", "English")
    full_name = context.get("full_name") or ""
    person_type = context.get("person_type", "Guest")

    if person_type in ("Employee", "Consultant"):
        first_name = _employee_first_name(context) or full_name
        name_str = f", {first_name}" if first_name else ""
        if lang == "Urdu":
            return (
                f"*السلام علیکم{name_str}!* 👋\n\n"
                "*MicroMerger Staff Support* میں خوش آمدید۔\n\n"
                "ہم آپ کے روزمرہ HR اور آپریشنل کام آسان بنانے کے لیے یہاں ہیں — "
                "حاضری، رخصت، پے رول، سفر، دستاویزات اور کام کی جگہ کی معاونت سمیت۔"
            )
        elif lang == "Roman Urdu":
            return (
                f"*Assalam-o-Alaikum{name_str}!* 👋\n\n"
                "Welcome to *MicroMerger Staff Support*.\n\n"
                "Hum aap ke rozmarrah HR aur operational tasks aasan banane ke liye yahan hain — "
                "attendance, leave, payroll, travel, documents aur workplace support samait."
            )
        return (
            f"*Assalam-o-Alaikum{name_str}!* 👋\n\n"
            "Welcome to *MicroMerger Staff Support*.\n\n"
            "We're here to make your day-to-day HR and operational tasks easier — "
            "including attendance, leave, payroll, travel, documents and workplace support."
        )

    if person_type in ("Former Employee", "Inactive"):
        name_str = f", {full_name}" if full_name else ""
        if lang == "Urdu":
            return (
                f"*السلام علیکم{name_str}!* 👋\n"
                "*MicroMerger AI اسسٹنس* میں خوش آمدید۔\n"
                "ہمارا ریکارڈ ظاہر کرتا ہے کہ آپ پہلے MicroMerger کے ساتھ منسلک تھے۔ آپ سابقہ عملے کی سپورٹ، HR دستاویزات، پے رول کے سوالات اور دیگر معاونت کے لیے اس سروس کا استعمال کر سکتے ہیں۔"
            )
        elif lang == "Roman Urdu":
            return (
                f"*Assalam-o-Alaikum{name_str}!* 👋\n"
                "Welcome to *MicroMerger AI assistance*.\n"
                "Hamara record zahir karta hai ke aap pehle MicroMerger ke sath associated thay. Aap ex staff support, HR documents, payroll queries aur baki madad ke liye yeh service use kar sakte hain."
            )
        return (
            f"*Assalam-o-Alaikum{name_str}!* 👋\n"
            "Welcome to *MicroMerger AI assistance*.\n"
            "Our records show that you were previously associated with MicroMerger. You can use this service for ex staff support, HR documents, payroll-related queries and other assistance."
        )

    # Guest / Unrecognized number
    if lang == "Urdu":
        return (
            "*السلام علیکم!* 👋\n"
            "*MicroMerger* میں خوش آمدید۔\n"
            "آپ کا WhatsApp نمبر فی الحال ہمارے سسٹم میں رجسٹرڈ نہیں ہے۔ آپ اب بھی ہماری عوامی خدمات، کیریئر، کاروباری معلومات اور عمومی تعاون تک رسائی حاصل کر سکتے ہیں۔\n\n"
            "اگر آپ MicroMerger کے ملازم ہیں، تو براہ کرم اپنے HRMIS پروفائل میں اپنا فعال WhatsApp نمبر اپ ڈیٹ کرنے کے لیے HR سے رابطہ کریں۔"
        )
    elif lang == "Roman Urdu":
        return (
            "*Assalam-o-Alaikum!* 👋\n"
            "Welcome to *MicroMerger*.\n"
            "Aap ka WhatsApp number filhal hamare system mein registered nahi hai. Aap ab bhi hamari public services, careers, business information aur general support access kar sakte hain.\n\n"
            "Agar aap MicroMerger ke employee hain, toh barah-e-karam apne HRMIS profile mein apna active WhatsApp number update karwane ke liye HR se rabta karein."
        )
    return (
        "*Assalam-o-Alaikum!* 👋\n"
        "Welcome to *MicroMerger*.\n"
        "Your WhatsApp number is not currently registered in our system. You can still access our public services, careers, business information, and general support.\n\n"
        "If you are a MicroMerger employee, please contact HR to update your active WhatsApp number in your HRMIS profile."
    )


def build_menu_header_text(context: dict[str, Any], include_greeting: bool = False) -> str:
    """Branding/prompt header for main service menu based on user category."""
    lang = context.get("preferred_language", "English")
    person_type = context.get("person_type", "Guest")

    if person_type == "Guest":
        if lang == "Urdu":
            return (
                "MicroMerger Support میں خوش آمدید۔ "
                "ہمیں اس WhatsApp نمبر کے ساتھ کوئی فعال یا سابقہ ملازمت کا ریکارڈ نہیں ملا۔ "
                "براہ کرم منتخب کریں کہ ہم آپ کی کس طرح مدد کر سکتے ہیں۔"
            )
        elif lang == "Roman Urdu":
            return (
                "Welcome to MicroMerger Support. "
                "Hamein is WhatsApp number ke sath koi active ya purana employment record nahi mila. "
                "Barah-e-karam intekhab karein ke hum aap ki kaise madad kar sakte hain."
            )
        return (
            "Welcome to MicroMerger Support. "
            "We could not find an active or previous employment record associated with this WhatsApp number. "
            "Please select how we can assist you."
        )

    if person_type in ("Former Employee", "Inactive"):
        if lang == "Urdu":
            return "خوش آمدید! ہمارا ریکارڈ ظاہر کرتا ہے کہ آپ نے پہلے MicroMerger کے ساتھ کام کیا ہے۔"
        elif lang == "Roman Urdu":
            return "Welcome back. Hamara record zahir karta hai ke aap ne pehle MicroMerger کے ساتھ kaam kiya hai."
        return "Welcome back. Our records show that you previously worked with MicroMerger."

    if include_greeting:
        full_name = context.get("full_name") or ""
        if not full_name:
            greeting = _get_generic_greeting(lang)
        else:
            greeting = _get_personalized_greeting(full_name, lang)

        if lang == "Urdu":
            return f"{greeting}\n\nبراہ کرم سروس منتخب کریں۔"
        if lang == "Roman Urdu":
            return f"{greeting}\n\nBarah-e-karam service intekhab karein."
        return f"{greeting}\n\nPlease choose a service below."

    if lang == "Urdu":
        return (
            "براہ کرم سروس منتخب کریں۔\n\n"
            "*آج ہم آپ کی کیا مدد کر سکتے ہیں؟*"
        )
    if lang == "Roman Urdu":
        return (
            "Barah-e-karam service intekhab karein.\n\n"
            "*Aaj hum aap ki kya madad kar sakte hain?*"
        )
    return (
        "Please choose a service below.\n\n"
        "*How can we help you today?*"
    )




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
    """Build placeholder/information response for selected service or submenu item."""
    lang = context.get("preferred_language", "English")

    if frappe.db and frappe.db.exists("WhatsApp Menu Item", service_key):
        item = frappe.get_doc("WhatsApp Menu Item", service_key)
        title = item.title
        if lang == "Urdu" and item.title_urdu:
            title = item.title_urdu
        elif lang == "Roman Urdu" and item.title_roman_urdu:
            title = item.title_roman_urdu

        desc = item.description or ""
        if desc:
            if lang == "Urdu":
                return f"*{title}*\n\n{desc}\n\nمین مینو پر واپس جانے کے لیے 'menu' لکھیے۔"
            elif lang == "Roman Urdu":
                return f"*{title}*\n\n{desc}\n\nMain menu par wapas jaane ke liye 'menu' likhein."
            return f"*{title}*\n\n{desc}\n\nType 'menu' to return to the main menu."

        if lang == "Urdu":
            return f"*{title}* منتخب کی گئی۔ یہ سروس جلد فعال ہو جائے گی۔\n\nمین مینو پر واپس جانے کے لیے 'menu' لکھیے۔"
        elif lang == "Roman Urdu":
            return f"*{title}* select hua. Yeh service jald faal ho jayegi.\n\nMain menu par wapas jaane ke liye 'menu' likhein."
        return f"*{title}* selected.\n\nThis service will be available soon.\n\nType 'menu' to return to the main menu."

    placeholders = {
        "hr": {
            "English": "HR service selected.\n\nHR services will be available here.",
            "Urdu": "ایچ آر سروس منتخب کی گئی۔ ایچ آر سروسز جلد دستیاب ہوں گی۔",
            "Roman Urdu": "HR service selected. HR services yahan dastiyab hongi.",
        },
        "policy": {
            "English": "Policies & Help selected.\n\nPolicy assistance is being prepared.",
            "Urdu": "پالیسیاں اور مدد منتخب کی گئیں۔ پالیسی معلومات تیار کی جا رہی ہیں۔",
            "Roman Urdu": "Policies & Help selected. Policy assistance tayyar ki ja rahi hai.",
        },
        "travel": {
            "English": "Travel service selected.\n\nTravel services will be available here.",
            "Urdu": "ٹریول سروس منتخب کی گئی۔ ٹریول سروسز جلد دستیاب ہوں گی۔",
            "Roman Urdu": "Travel service selected. Travel services yahan dastiyab hongi.",
        },
    }

    svc_dict = placeholders.get(service_key.lower(), {})
    return svc_dict.get(lang, svc_dict.get("English", f"*{service_key.replace('_', ' ').title()}* selected.\n\nType 'menu' to return to the main menu."))



def build_help_response(
    context: dict[str, Any],
    service_items: Sequence[dict[str, Any]],
) -> str:
    """Build deterministic help response detailing available menu options."""
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        lines = ["آپ مینو سے دستیاب سروسز استعمال کر سکتے ہیں۔\n\nجواب دیں:"]
    elif lang == "Roman Urdu":
        lines = ["Aap menu se dastiyab services istemal kar sakte hain.\n\nReply karein:"]
    else:
        lines = ["You can use the menu to access available workplace services.\n\nReply with:"]

    for idx, item in enumerate(service_items):
        title = _translate_service_title(item["key"], item["title"], lang)
        if lang == "Urdu":
            lines.append(f"{idx + 1} — {title}")
        else:
            lines.append(f"{idx + 1} for {title}")

    if lang == "English":
        lines.append("\nType 'menu' to return to the main menu.")
    elif lang == "Roman Urdu":
        lines.append("\nMain menu ke liye 'menu' likhein.")
    else:
        lines.append("\nمینو کے لیے 'menu' لکھیے۔")

    return "\n".join(lines)


def _get_personalized_greeting(name: str, lang: str) -> str:
    if lang == "Urdu":
        return f"Assalam-o-Alaikum.\n{name}، MicroMerger Support میں خوش آمدید۔"
    if lang == "Roman Urdu":
        return f"Assalam-o-Alaikum.\nWelcome {name} to MicroMerger Support."
    return f"Assalam-o-Alaikum.\nWelcome {name} to MicroMerger Support."


def _get_generic_greeting(lang: str) -> str:
    if lang == "Urdu":
        return "Assalam-o-Alaikum.\nMicroMerger Support میں خوش آمدید۔"
    if lang == "Roman Urdu":
        return "Assalam-o-Alaikum.\nMicroMerger Support mein khush aamdeed."
    return "Assalam-o-Alaikum.\nWelcome to MicroMerger Support."



def _translate_service_title(key: str, default_title: str, lang: str) -> str:
    if key.lower() == "main_menu":
        if lang == "Urdu":
            return "🔙 اصلی مینو"
        return "🔙 Main Menu"
    if lang == "Urdu":
        translations = {
            "hr": "مائی ایچ آر",
            "policy": "پالیسیاں اور مدد",
            "travel": "میرا سفر",
            "help": "مدد / زبان",
            "deliverables": "ڈیلیوریبلز",
            "main_menu": "🔙 اصلی مینو",
        }
        return translations.get(key.lower(), default_title)
    if lang == "Roman Urdu":
        translations = {
            "hr": "My HR",
            "policy": "Policies & Help",
            "travel": "My Travel",
            "help": "Help / Language",
            "deliverables": "Deliverables",
            "main_menu": "🔙 Main Menu",
        }
        return translations.get(key.lower(), default_title)
    return default_title
