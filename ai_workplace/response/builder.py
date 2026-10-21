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


def _clean_urdu_string(text: str) -> str:
    if not text:
        return ""
    import re
    replacements = [
        (r'\bHRMIS\b', 'ایچ آر ایم آئی ایس'),
        (r'\bHR\b', 'ایچ آر'),
        (r'\bAI\b', 'پالیسی اسسٹنٹ'),
        (r'\bDSA\b', 'الاؤنس'),
        (r'\bPIN\b', 'پن کوڈ'),
        (r'\bExcel\b', 'ایکسل'),
        (r'\bPDF\b', 'پی ڈی ایف'),
        (r'\bWhatsApp\b', 'واٹس ایپ'),
        (r'\bMicroMerger\b', 'مائیکرو مرجر'),
    ]
    cleaned = text
    for pat, rep in replacements:
        cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'پالیسی اسسٹنٹ\s+پالیسی اسسٹنٹ', 'پالیسی اسسٹنٹ', cleaned)
    cleaned = re.sub(r'ایچ آر\s+ایچ آر', 'ایچ آر', cleaned)
    return cleaned.strip()


def build_unregistered_response(context: dict[str, Any]) -> str:
    """
    BRD Appendix B.2 — guest, inactive, and ambiguous identities.
    No protected menu; must not reveal whether an employee record exists.
    """
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        return (
            "یہ واٹس ایپ نمبر مائیکرو مرجر سیلف سروس کے لیے رجسٹرڈ نہیں ہے۔\n\n"
            "سیکیورٹی وجوہات کی بنا پر، اس نمبر پر ملازم کی معلومات فراہم نہیں کی جا سکتیں۔\n\n"
            "براہ کرم ایچ آر سے رابطہ کریں تاکہ آپ کا ذاتی یا دفتری موبائل نمبر اپ ڈیٹ کیا جا سکے۔"
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
        title = _translate_service_title(item["key"], item["title"], lang)
        menu_lines.append(f"{idx + 1}. {title}")

    menu_text = "\n".join(menu_lines)

    if lang == "Urdu":
        header = (
            f"{greeting}\n\n"
            f"براہ کرم منتخب کریں:\n\n{menu_text}\n\n"
            f"آپ اردو، Roman Urdu یا انگلش میں اپنا سوال بھی لکھ سکتے ہیں۔"
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
        name_str = f", {full_name}" if full_name else ""
        if lang == "Urdu":
            return (
                f"*السلام علیکم{name_str}!* 👋\n\n"
                "*مائیکرو مرجر ملازمین معاونت* میں خوش آمدید۔\n\n"
                "ہم آپ کے روزمرہ ایچ آر اور دفتری کام آسان بنانے کے لیے یہاں ہیں — "
                "حاضری، رخصت، تنخواہ، سفر، دستاویزات اور ملازمین کی معاونت سمیت۔"
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
                "*مائیکرو مرجر اسسٹنس* میں خوش آمدید۔\n"
                "ہمارا ریکارڈ ظاہر کرتا ہے کہ آپ پہلے مائیکرو مرجر کے ساتھ منسلک تھے۔ آپ سابقہ عملے کی سپورٹ، ایچ آر دستاویزات، پے رول کے سوالات اور دیگر معاونت کے لیے اس سروس کا استعمال کر سکتے ہیں۔"
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
            "*مائیکرو مرجر* میں خوش آمدید۔\n"
            "آپ کا واٹس ایپ نمبر فی الحال ہمارے سسٹم میں رجسٹرڈ نہیں ہے۔ آپ اب بھی ہماری عوامی خدمات، کیریئر، کاروباری معلومات اور عمومی تعاون تک رسائی حاصل کر سکتے ہیں۔\n\n"
            "اگر آپ مائیکرو مرجر کے ملازم ہیں، تو براہ کرم اپنے ایچ آر ایم آئی ایس پروفائل میں اپنا فعال واٹس ایپ نمبر اپ ڈیٹ کرنے کے لیے ایچ آر سے رابطہ کریں۔"
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
                "مائیکرو مرجر سپورٹ میں خوش آمدید۔ "
                "ہمیں اس واٹس ایپ نمبر کے ساتھ کوئی فعال یا سابقہ ملازمت کا ریکارڈ نہیں ملا۔ "
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
            return "خوش آمدید! ہمارا ریکارڈ ظاہر کرتا ہے کہ آپ نے پہلے مائیکرو مرجر کے ساتھ کام کیا ہے۔"
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

    from ai_workplace.services.response_helpers import label_automated_response

    menu_str = build_welcome_menu_response(context, service_items)
    return label_automated_response(f"{error_msg}\n\n{menu_str}")


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
        lines = ["آپ مینو سے دستیاب سروسز استعمال کر سکتے ہیں۔\n\nبراہ کرم منتخب کریں:"]
    elif lang == "Roman Urdu":
        lines = ["Aap menu se dastiyab services istemal kar sakte hain.\n\nReply karein:"]
    else:
        lines = ["You can use the menu to access available workplace services.\n\nReply with:"]

    for idx, item in enumerate(service_items):
        title = _translate_service_title(item["key"], item["title"], lang)
        if lang == "Urdu":
            emoji = NUMBER_EMOJIS[idx] if idx < len(NUMBER_EMOJIS) else f"{idx + 1}۔"
            lines.append(f"{emoji} {title}")
        else:
            lines.append(f"{idx + 1} for {title}")

    if lang == "English":
        lines.append("\nType 'menu' to return to the main menu.")
    elif lang == "Roman Urdu":
        lines.append("\nMain menu ke liye 'menu' likhein.")
    else:
        lines.append("\nمین مینو کے لیے 'menu' لکھیے۔")

    return "\n".join(lines)


def _get_personalized_greeting(name: str, lang: str) -> str:
    if lang == "Urdu":
        return f"السلام علیکم۔\n{name}، مائیکرو مرجر سپورٹ میں خوش آمدید۔"
    if lang == "Roman Urdu":
        return f"Assalam-o-Alaikum.\nWelcome {name} to MicroMerger Support."
    return f"Assalam-o-Alaikum.\nWelcome {name} to MicroMerger Support."


def _get_generic_greeting(lang: str) -> str:
    if lang == "Urdu":
        return "السلام علیکم۔\nمائیکرو مرجر سپورٹ میں خوش آمدید۔"
    if lang == "Roman Urdu":
        return "Assalam-o-Alaikum.\nMicroMerger Support mein khush aamdeed."
    return "Assalam-o-Alaikum.\nWelcome to MicroMerger Support."



def _translate_service_title(
    key: str,
    default_title: str,
    lang: str,
    title_urdu: str = "",
    title_roman_urdu: str = "",
) -> str:
    key_clean = (key or "").strip().lower()
    if key_clean in ("main_menu", "back_to_main", "svc_main_menu"):
        if lang == "Urdu":
            return "🏠 اصلی مینو"
        return "🏠 Main Menu"

    if lang == "Urdu":
        if title_urdu and title_urdu != default_title:
            return _clean_urdu_string(title_urdu)
        try:
            from ai_workplace.services.registry import get_service_info
            info = get_service_info(key)
            if info and info.get("title_urdu") and info["title_urdu"] != default_title:
                return _clean_urdu_string(info["title_urdu"])
        except Exception:
            pass

        translations = {
            "attendance_leave": "🕒 حاضری اور رخصت",
            "payroll": "💰 تنخواہ اور پے رول",
            "travel": "🚗 سفر اور الاؤنس",
            "documents": "📄 دستاویزات اور معاہدہ",
            "hr": "👤 میری پروفائل اور دستاویزات",
            "staff_support": "💙 ملازمین کی معاونت",
            "policies": "🤖 پالیسی اسسٹنٹ",
            "deliverables": "📦 ڈیلیوریبلز",
            "contact_hr": "💬 ایچ آر سے بات کریں",
            "help": "مدد اور زبان",
            "att_today": "📅 آج کی حاضری",
            "att_checkin": "✅ چیک ان",
            "att_checkout": "🚪 چیک آؤٹ",
            "att_monthly": "🗓️ ماہانہ حاضری",
            "att_missing": "⚠️ گمشدہ حاضری",
            "leave_balance": "📊 رخصت کا بیلنس",
            "leave_apply": "📝 رخصت کی درخواست",
            "leave_requests": "📋 میری رخصت کی درخواستیں",
            "pay_download_slip": "📥 سیلری سلپ",
            "pay_tax_deduction": "🧾 ٹیکس سرٹیفکیٹ",
            "pay_experience_letter": "📄 تجربہ سرٹیفکیٹ",
            "pay_bank_letter": "🏦 بینک لیٹر",
            "trv_apply": "➕ سفری منظوری کی درخواست",
            "trv_approved": "✅ منظور شدہ سفر",
            "trv_upcoming": "🔜 آنے والا سفر",
            "trv_claim_status": "🔄 کلیم کی صورتحال",
            "trv_vehicle_info": "🚙 گاڑی اور ڈرائیور",
            "trv_sop": "📖 سفر اور الاؤنس پالیسی",
            "trv_problem": "🚨 سفری معاونت",
            "doc_contract": "📃 موجودہ معاہدہ",
            "doc_salary_slip": "📥 سیلری سلپ",
            "doc_tax_cert": "🧾 ٹیکس سرٹیفکیٹ",
            "doc_experience_letter": "📄 تجربہ سرٹیفکیٹ",
            "doc_bank_letter": "🏦 بینک لیٹر",
            "doc_my_requests": "📋 میری دستاویزات کی درخواستیں",
            "my_day": "☀️ میرا دن",
            "my_profile": "👤 میری پروفائل",
            "supervisor_reporting": "👨‍💼 سپروائزر اور رپورٹنگ",
            "update_profile": "🛠️ اپنی تفصیلات اپ ڈیٹ",
            "prof_my_requests": "📋 میری درخواستیں",
            "hr_pin_help": "🔐 پن کوڈ مدد",
            "staff_hr_guidance": "🤖 پالیسی اسسٹنٹ",
            "staff_supervisor": "👨‍💼 سپروائزر سپورٹ",
            "concerns": "🔒 شکایت اور خفیہ خدشات",
            "staff_contact_hr": "💬 ایچ آر سے بات کریں",
            "dlv_add": "➕ ڈیلیوریبل شامل کریں",
            "dlv_submit": "📤 منظوری کے لیے بھیجیں",
            "dlv_status": "📋 میرے ڈیلیوریبلز",
            "former_letter": "📄 تجربہ اور سروس لیٹر",
            "former_payslip": "🧾 پے سلپ اور ٹیکس دستاویزات",
            "former_verification": "🔍 روزگار کی تصدیق",
            "former_concern": "🛡️ شکایت درج کریں",
            "former_careers": "💼 ملازمت کے مواقع",
            "guest_careers": "💼 مائیکرو مرجر میں کیریئر",
            "guest_job_status": "📝 جاب کی درخواست کی صورتحال",
            "guest_verification": "🔍 روزگار کی تصدیق",
            "guest_vendor": "🤝 وینڈر سپورٹ",
            "guest_concern": "🛡️ شکایت درج کریں",
            "guest_number_changed": "🔐 میرا نمبر تبدیل ہو گیا ہے",
            "pay_slip_1m": "📄 1 مہینہ",
            "pay_slip_3m": "📄 3 ماہ",
            "pay_slip_6m": "📄 6 ماہ",
            "pay_slip_latest": "📄 تازہ ترین پے سلپ",
            "pay_bank_faysal": "🏦 فیصل بینک",
            "pay_bank_scb": "🏦 اسٹینڈرڈ چارٹرڈ",
            "att_monthly_last7": "📋 7 دن",
            "att_monthly_download": "📥 ایکسل ڈاؤن لوڈ",
            "tax_cert_current": "🧾 موجودہ مالی سال",
            "tax_cert_previous": "🧾 پچھلا مالی سال",
            "tax_cert_latest": "🧾 حالیہ ٹیکس سرٹیفکیٹ",
        }
        res = translations.get(key_clean, title_urdu or default_title)
        return _clean_urdu_string(res)

    if lang == "Roman Urdu":
        if title_roman_urdu and title_roman_urdu != default_title:
            return title_roman_urdu
        try:
            from ai_workplace.services.registry import get_service_info
            info = get_service_info(key)
            if info and info.get("title_roman_urdu") and info["title_roman_urdu"] != default_title:
                return info["title_roman_urdu"]
        except Exception:
            pass

    return default_title


def _translate_service_description(
    key: str,
    default_desc: str,
    lang: str,
    desc_urdu: str = "",
    desc_roman_urdu: str = "",
) -> str:
    key_clean = (key or "").strip().lower()
    if lang == "Urdu":
        if desc_urdu and desc_urdu != default_desc:
            return _clean_urdu_string(desc_urdu)
        try:
            from ai_workplace.services.registry import get_service_info
            info = get_service_info(key)
            if info and info.get("description_urdu") and info["description_urdu"] != default_desc:
                return _clean_urdu_string(info["description_urdu"])
        except Exception:
            pass

        desc_translations = {
            "attendance_leave": "حاضری، چیک ان، چیک آؤٹ اور رخصت کی تفصیلات",
            "payroll": "سیلری سلپ، بینک لیٹر اور ٹیکس سرٹیفکیٹ",
            "travel": "سفری منظوری، الاؤنس اور کلیم کی تفصیلات",
            "documents": "ملازمت کا معاہدہ، سرٹیفکیٹ اور دفتری دستاویزات",
            "hr": "ذاتی پروفائل، رپورٹنگ مینیجر اور دفتری ریکارڈ",
            "staff_support": "سپروائزر معاونت، پالیسی گائیڈنس اور ایچ آر رابطہ",
            "policies": "مائیکرو مرجر ایچ آر اور دفتری پالیسیوں کے جوابات",
            "deliverables": "پروجیکٹ ڈیلیوریبلز شامل کریں یا جمع کروائیں",
            "contact_hr": "ایچ آر نمائندے سے فوری رابطہ یا سوال",
            "help": "مدد، رہنمائی اور زبان کی ترتیبات",
            "att_today": "آج کے کام کے اوقات اور حاضریاں",
            "att_checkin": "آج کی حاضری کے لیے چیک ان درج کریں",
            "att_checkout": "آج کی روانگی کے لیے چیک آؤٹ درج کریں",
            "att_monthly": "موجودہ مہینے کی حاضری کا خلاصہ",
            "att_missing": "گمشدہ چیک ان یا چیک آؤٹ کی درخواست",
            "leave_balance": "دستیاب رخصتوں کی تعداد چیک کریں",
            "leave_apply": "نئی رخصت کے لیے درخواست دیں",
            "leave_requests": "جمع کروائی گئی رخصتوں کی صورتحال",
            "pay_download_slip": "حالیہ یا پچھلے مہینوں کی سیلری سلپ",
            "pay_tax_deduction": "سالانہ انکم ٹیکس کٹوتی سرٹیفکیٹ",
            "pay_experience_letter": "تجربہ کا سرٹیفکیٹ حاصل کریں",
            "pay_bank_letter": "بینک اکاؤنٹ کے لیے لیٹر",
            "trv_apply": "دفتری سفر کے لیے پیشگی منظوری",
            "trv_approved": "منظور شدہ سفری منصوبے دیکھیں",
            "trv_upcoming": "آنے والے طے شدہ دورے",
            "trv_claim_status": "سفری اخراجات اور الاؤنس کلیم",
            "trv_vehicle_info": "مختص کردہ گاڑی اور ڈرائیور کی معلومات",
            "trv_sop": "سرکاری دوروں کے الاؤنس اور قوانین",
            "trv_problem": "سفر کے دوران کسی مسئلے پر فوری مدد",
            "doc_contract": "ملازمت کے فعال معاہدے کی تفصیل",
            "doc_salary_slip": "سیلری سلپ ڈاؤن لوڈ کریں",
            "doc_tax_cert": "ٹیکس کٹوتی دستاویز ڈاؤن لوڈ کریں",
            "doc_experience_letter": "تجربہ اور سروس کا لیٹر حاصل کریں",
            "doc_bank_letter": "بینک تصدیقی خط حاصل کریں",
            "doc_my_requests": "دستاویزات کی جاری درخواستوں کی تفصیل",
            "my_day": "آج کی مصروفیات اور بنیادی تفصیلات",
            "my_profile": "ملازمت کا ڈیٹا اور رابطہ معلومات",
            "supervisor_reporting": "رپورٹنگ مینیجر اور ٹیم کی معلومات",
            "update_profile": "ذاتی معلومات میں تبدیلی کی درخواست",
            "prof_my_requests": "آپ کی تمام بھیجی گئی درخواستیں",
            "hr_pin_help": "سپورٹ پن کوڈ ری سیٹ یا مدد",
            "staff_hr_guidance": "پالیسی اسسٹنٹ سے کمپنی قواعد جانیں",
            "staff_supervisor": "سپروائزر سے رہنمائی اور معاونت",
            "concerns": "خفیہ طور پر تحفظات یا شکایت درج کروائیں",
            "staff_contact_hr": "ایچ آر ٹیم سے براہ راست بات چیت",
            "dlv_add": "نیا پروجیکٹ ٹاسک یا ڈیلیوریبل شامل کریں",
            "dlv_submit": "مکمل ٹاسک سپروائزر کو منظوری کے لیے بھیجیں",
            "dlv_status": "اپنے ڈیلیوریبلز کی منظوری کی صورتحال",
            "former_letter": "سابقہ سروس یا تجربہ کا لیٹر",
            "former_payslip": "سابقہ پے سلپ اور فائنل ٹیکس دستاویزات",
            "former_verification": "روزگار اور مدت ملازمت کی تصدیق",
            "former_concern": "سابقہ ملازمین کی شکایات یا استفسار",
            "former_careers": "دوبارہ شمولیت یا نئی ملازمت کے مواقع",
            "guest_careers": "مائیکرو مرجر میں خالی آسامیوں کی معلومات",
            "guest_job_status": "ملازمت کی درخواست کی تازہ ترین صورتحال",
            "guest_verification": "ملازم کی ملازمت کی سرکاری تصدیق",
            "guest_vendor": "وینڈر بلنگ اور خریداری معاونت",
            "guest_concern": "عمومی یا بیرونی تحفظات اور شکایات",
            "guest_number_changed": "رجسٹرڈ واٹس ایپ نمبر کی تبدیلی کی درخواست",
            "pay_slip_1m": "گزشتہ 1 ماہ کی پے سلپ",
            "pay_slip_3m": "گزشتہ 3 ماہ کی پے سلپ",
            "pay_slip_6m": "گزشتہ 6 ماہ کی پے سلپ",
            "pay_slip_latest": "حالیہ مہینے کی پے سلپ",
            "pay_bank_faysal": "فیصل بینک کے لیے تصدیقی خط",
            "pay_bank_scb": "اسٹینڈرڈ چارٹرڈ کے لیے تصدیقی خط",
            "att_monthly_last7": "گزشتہ 7 دن کی حاضری",
            "att_monthly_download": "پورے مہینے کی ایکسل شیٹ حاصل کریں",
            "tax_cert_current": "موجودہ مالی سال کا ٹیکس سرٹیفکیٹ",
            "tax_cert_previous": "گزشتہ مالی سال کا ٹیکس سرٹیفکیٹ",
            "tax_cert_latest": "حالیہ ٹیکس سرٹیفکیٹ",
        }
        res = desc_translations.get(key_clean, desc_urdu or default_desc)
        return _clean_urdu_string(res)

    if lang == "Roman Urdu":
        if desc_roman_urdu and desc_roman_urdu != default_desc:
            return desc_roman_urdu
        try:
            from ai_workplace.services.registry import get_service_info
            info = get_service_info(key)
            if info and info.get("description_roman_urdu") and info["description_roman_urdu"] != default_desc:
                return info["description_roman_urdu"]
        except Exception:
            pass

    return default_desc
