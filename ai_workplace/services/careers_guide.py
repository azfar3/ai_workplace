"""
ai_workplace/services/careers_guide.py
────────────────────────────────────────
XpertJobs portal guide for guest and former-employee job menus:
- guest_careers: Browse and apply for openings
- guest_job_status: Track application status
- former_careers: Career opportunities for former employees
"""

from __future__ import annotations

from typing import Any

XPERTJOBS_URL = "https://xpertjobs.pk/"

CAREERS_MENU_KEYS = frozenset({"guest_careers", "guest_job_status", "former_careers"})


def build_careers_guide_response(service_key: str, context: dict[str, Any]) -> str:
    """Build multilingual XpertJobs portal instructions for a careers menu key."""
    lang = context.get("preferred_language", "English")
    key = (service_key or "").strip().lower()

    if key == "guest_careers":
        return _guest_careers(lang)
    if key == "guest_job_status":
        return _guest_job_status(lang)
    if key == "former_careers":
        return _former_careers(lang)

    return _guest_careers(lang)


def _guest_careers(lang: str) -> str:
    if lang == "Urdu":
        return (
            "💼 *MicroMerger میں کیریئر*\n\n"
            "ملازمت کے لیے درخواست دینے کے لیے https://xpertjobs.pk/ پر جائیں:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*درخواست دینے کا طریقہ:*\n"
            f"1. {XPERTJOBS_URL} پر جائیں اور کھلی پوزیشنز دیکھیں\n"
            "2. اکاؤنٹ بنائیں یا سائن ان کریں\n"
            "3. مطلوبہ رول کے لیے آن لائن درخواست جمع کروائیں\n\n"
            "MicroMerger WhatsApp پر ملازمت کی درخواست قبول نہیں کرتا۔"
        )
    if lang == "Roman Urdu":
        return (
            "💼 *Careers at MicroMerger*\n\n"
            "Job ke liye apply karne ke liye https://xpertjobs.pk/ par jaein:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*Apply kaise karein:*\n"
            f"1. Portal {XPERTJOBS_URL} par ja kar open positions dekhein\n"
            "2. Account banayein ya sign in karein\n"
            "3. Manpasand role ke liye online application submit karein\n\n"
            "MicroMerger WhatsApp par job applications accept nahi karta."
        )
    return (
        "💼 *Careers at MicroMerger*\n\n"
        "To apply for a job, please go to https://xpertjobs.pk/\n\n"
        f"🌐 {XPERTJOBS_URL}\n\n"
        "*How to apply:*\n"
        f"1. Visit {XPERTJOBS_URL} and browse open positions\n"
        "2. Create an account or sign in\n"
        "3. Submit your application online for the role you're interested in\n\n"
        "MicroMerger does not accept job applications via WhatsApp."
    )


def _guest_job_status(lang: str) -> str:
    if lang == "Urdu":
        return (
            "📝 *درخواست کی صورتحال*\n\n"
            "اپنی ملازمت کی درخواست کی صورتحال دیکھنے کے لیے https://xpertjobs.pk/ پر جائیں:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*Status دیکھنے کا طریقہ:*\n"
            f"1. اپنے XpertJobs اکاؤنٹ {XPERTJOBS_URL} میں سائن ان کریں\n"
            "2. *My Applications* / *Applied Jobs* کھولیں\n"
            "3. ہر درخواست کی تازہ ترین اپڈیٹ دیکھیں\n\n"
            "کسی مخصوص درخواست کے لیے مدد چاہیے تو مینو سے *Contact HR* منتخب کریں۔"
        )
    if lang == "Roman Urdu":
        return (
            "📝 *Application Status*\n\n"
            "Apni job application status check karne ke liye https://xpertjobs.pk/ par jaein:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*Status kaise dekhein:*\n"
            f"1. Apne XpertJobs account {XPERTJOBS_URL} mein sign in karein\n"
            "2. *My Applications* / *Applied Jobs* kholen\n"
            "3. Har application ki latest update dekhein\n\n"
            "Kisi khaas application ke liye madad chahiye to menu se *Contact HR* select karein."
        )
    return (
        "📝 *Application Status*\n\n"
        "To track your job application, please go to https://xpertjobs.pk/\n\n"
        f"🌐 {XPERTJOBS_URL}\n\n"
        "*How to check status:*\n"
        f"1. Sign in to your XpertJobs account at {XPERTJOBS_URL}\n"
        "2. Open *My Applications* / *Applied Jobs*\n"
        "3. View the latest update for each submission\n\n"
        "For help with a specific application, select *Contact HR* from the menu."
    )


def _former_careers(lang: str) -> str:
    if lang == "Urdu":
        return (
            "💼 *کیریئر کے مواقع*\n\n"
            "سابقہ ٹیم ممبرز (Former team members) ملازمت کے لیے درخواست دینے کے لیے https://xpertjobs.pk/ پر جائیں:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*درخواست دینے کا طریقہ:*\n"
            f"1. {XPERTJOBS_URL} پر موجود vacancies دیکھیں\n"
            "2. سائن ان کریں اور آن لائن درخواست جمع کروائیں\n"
            "3. درخواست کی صورتحال *My Applications* میں دیکھیں\n\n"
            "WhatsApp پر ملازمت کی درخواست قبول نہیں کی جاتی — صرف XpertJobs پورٹل استعمال کریں۔"
        )
    if lang == "Roman Urdu":
        return (
            "💼 *Career Opportunities*\n\n"
            "Purane team members (Former team members) job ke liye apply karne ke liye https://xpertjobs.pk/ par jaein:\n\n"
            f"🌐 {XPERTJOBS_URL}\n\n"
            "*Apply kaise karein:*\n"
            f"1. Portal {XPERTJOBS_URL} par vacancies dekhein\n"
            "2. Sign in kar ke online application submit karein\n"
            "3. Status *My Applications* mein dekhein\n\n"
            "WhatsApp par job applications accept nahi hoti — sirf XpertJobs portal istemal karein."
        )
    return (
        "💼 *Career Opportunities*\n\n"
        "Former team members are welcome to apply for open roles by visiting https://xpertjobs.pk/\n\n"
        f"🌐 {XPERTJOBS_URL}\n\n"
        "*How to apply:*\n"
        f"1. Browse current vacancies on {XPERTJOBS_URL}\n"
        "2. Sign in and submit your application online\n"
        "3. Track status under *My Applications*\n\n"
        "Job applications are not accepted on WhatsApp — please use the XpertJobs portal only."
    )
