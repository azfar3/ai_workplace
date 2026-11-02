"""Pure conversation decisions shared by request handling and catch-up jobs."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

LEAVE_QUESTIONS = {
    "awaiting_leave_type": "Which leave reason would you like to select?",
    "awaiting_from_date": "What is the start date of your leave?",
    "awaiting_to_date": "What is the end date of your leave?",
    "awaiting_half_day": "Would you like to request a half day?",
    "awaiting_reason": "What reason would you like to include in your request?",
    "awaiting_confirm": "Would you like to review your leave request before submitting it?",
}

COPY = {
    "English": {
        "policy": "Would you like help applying this policy to your situation? Tell me which part you need help with.",
        "leave_policy": "Would you like to check your leave balance or apply for leave?",
        "catchup": "Earlier, you were asking about {topic}. Would you like to continue?",
        "continue": "Continue", "later": "Remind me later", "dismiss": "Dismiss",
        "dismissed": "Okay, I won't follow up on this conversation.",
        "later_ack": "I'll send one reminder later, if this conversation is still unfinished.",
    },
    "Roman Urdu": {
        "policy": "Kya aap is policy ko apni situation par samajhna chahte hain? Kis hissay mein madad chahiye?",
        "leave_policy": "Kya aap leave balance check karna ya leave apply karna chahte hain?",
        "catchup": "Aap pehle {topic} ke bare mein pooch rahe thay. Kya hum baat aage barhayein?",
        "continue": "Jari rakhein", "later": "Baad mein yaad dilayein", "dismiss": "Rehne dein",
        "dismissed": "Theek hai, is conversation ka reminder nahi bhejoon ga.",
        "later_ack": "Agar baat adhoori rahi to baad mein aik reminder bhejoon ga.",
    },
    "Urdu": {
        "policy": "کیا آپ اپنی صورت حال کے مطابق اس پالیسی کو سمجھنا چاہتے ہیں؟ کس حصے میں مدد چاہیے؟",
        "leave_policy": "کیا آپ چھٹیوں کا بیلنس دیکھنا یا چھٹی کی درخواست دینا چاہتے ہیں؟",
        "catchup": "آپ پہلے {topic} کے بارے میں پوچھ رہے تھے۔ کیا آپ بات جاری رکھنا چاہتے ہیں؟",
        "continue": "جاری رکھیں", "later": "بعد میں یاد دلائیں", "dismiss": "رہنے دیں",
        "dismissed": "ٹھیک ہے، اس گفتگو کا مزید یاد دہانی پیغام نہیں بھیجوں گا۔",
        "later_ack": "اگر بات ادھوری رہی تو بعد میں ایک یاد دہانی بھیجوں گا۔",
    },
}


def load_memory(value):
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def copy_for(language):
    return COPY.get(language, COPY["English"])


def quiet_now(now: datetime, start: int, end: int) -> bool:
    if start == end:
        return False
    return start <= now.hour < end if start < end else now.hour >= start or now.hour < end


def eligible(conv, memory, now: datetime) -> bool:
    """Fail closed for stale, completed, reassigned, or human-owned conversations."""
    if conv.get("conversation_status") != "Active" or conv.get("active_hr_chat_session"):
        return False
    if conv.get("current_state") in {"LIVE_HR_CHAT", "COMPLETED", "CANCELLED", "WAITING_FOR_SUPPORT_PIN"}:
        return False
    if memory.get("status") != "awaiting_user" or memory.get("opted_out"):
        return False
    if memory.get("employee") != conv.get("employee") or memory.get("user") != conv.get("erp_user"):
        return False
    if not conv.get("employee") or not conv.get("erp_user"):
        return False
    if memory.get("topic") == "leave application" and conv.get("current_intent") != "leave_apply":
        return False
    try:
        last_inbound = datetime.fromisoformat(memory["last_inbound_at"])
        due = datetime.fromisoformat(memory["due_at"])
        activity = conv.get("last_activity_at")
        if activity and (activity if isinstance(activity, datetime) else datetime.fromisoformat(str(activity))) > last_inbound:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    # Conservative free-form window; never send stale HR information or templates here.
    return due <= now and timedelta(0) <= now - last_inbound < timedelta(hours=23)


COMPANY_QUESTIONS = {
    "English": "Are you interested in MicroMerger's services, career opportunities, or company background?",
    "Urdu": "کیا آپ مائیکرو مرجر کی خدمات، ملازمت کے مواقع یا کمپنی کے پس منظر کے بارے میں جاننا چاہتے ہیں؟",
    "Roman Urdu": "Kya aap MicroMerger ki services, career opportunities, ya company background ke bare mein jaanna chahte hain?",
}


COMPANY_SERVICE_QUESTIONS = {
    "English": "Which MicroMerger service would you like to explore further?",
    "Urdu": "آپ مائیکرو مرجر کی کس خدمت کے بارے میں مزید جاننا چاہتے ہیں؟",
    "Roman Urdu": "Aap MicroMerger ki kis service ke bare mein mazeed jaanna chahte hain?",
}


def is_company_question(query):
    """Public company discovery, excluding personal and HR-policy questions."""
    import re
    query = " ".join((query or "").lower().replace("micro merger", "micromerger").split())
    if not re.search(r"\b(micromerger|our company|the company)\b", query):
        return False
    if re.search(r"\b(policy|policies|leave|salary|payroll|attendance|benefits?|employee|employees|jobs?|careers?|vacancies|recruitment|tax|expense|claim|travel|medical|insurance)\b", query):
        return False
    return bool(re.search(r"\b(know|about|company|what|who|services?|background|history|founded|founder|established|mission|vision|offices?|location|address|clients?|sectors?|business|industries|overview)\b", query))


def concise_company_answer(text, limit=90, *, user_query=""):
    """Keep complete sentences/lines; do not rewrite or invent company facts."""
    import re
    if wants_detailed_answer(user_query):
        return text
    if len(text.split()) <= limit:
        return text
    chunks = re.split(r"(?<=[.!?۔؟])\s+|\n+", text.strip())
    kept, count = [], 0
    for chunk in chunks:
        words = len(chunk.split())
        if count + words > limit:
            break
        kept.append(chunk)
        count += words
    # Avoid truncating a single long sentence into a misleading factual claim.
    return "\n".join(kept).strip() if kept and count >= 12 else text



def wants_detailed_answer(query):
    """Recognize explicit depth requests, including repeated-letter typos."""
    import re
    query = (query or "").lower()
    if re.search(r"\b(brief|briefly|short|shortly|concise|summari[sz]e)\b", query):
        return False
    return bool(re.search(
        r"\b(detail+l*(?:ed|s)?|full(?:y)?|in[ -]depth|comprehensive|thorough|elaborate|explain more|tell me more)\b|تفصیل|تفصیلی|tafs[ei]el|tafseel",
        query,
    ))


def company_answer_instructions(query):
    if wants_detailed_answer(query):
        depth = (
            "The user explicitly requested detail. Give a thorough, organized explanation "
            "with short headings and readable sections for the requested topics. "
            "Do not apply the brief introduction word limit. Explain services and company "
            "background to the extent supported by retrieved sources; avoid repetition and filler. "
        )
    else:
        depth = (
            "Give a concise WhatsApp answer of at most 80 words. For a broad introduction, "
            "use 2–3 sentences about the company and its main services. For a specific "
            "question, answer that question directly. "
        )
    return (
        " For this public company-information question, retrieve approved knowledge before answering. "
        + depth +
        "Avoid promotional claims. Include statistics only when relevant to the request and "
        "supported by the retrieved sources; do not invent facts or calculate years of "
        "experience from outdated website copy. Do not add a closing question; the application supplies it."
    )


# Application-owned next actions. IDs always return through normal authorization.
SERVICE_GUIDANCE = {
    'leave': ('leave services', {
        'English': 'Would you like to check your leave balance or start a leave application?',
        'Urdu': 'کیا آپ چھٹیوں کا بیلنس دیکھنا یا چھٹی کی درخواست دینا چاہتے ہیں؟',
        'Roman Urdu': 'Kya aap leave balance check karna ya leave apply karna chahte hain?',
    }, {'balance': 'svc_leave_balance', 'apply': 'svc_leave_apply'}),
    'attendance': ('attendance services', {
        'English': 'Do you need help reviewing attendance or requesting a correction?',
        'Urdu': 'کیا آپ حاضری دیکھنا یا اس کی درستگی کی درخواست دینا چاہتے ہیں؟',
        'Roman Urdu': 'Kya aap attendance dekhna ya correction request karna chahte hain?',
    }, {'review': 'svc_att_monthly', 'correction': 'apply for attendance request'}),
    'payroll': ('payroll services', {
        'English': 'Would you like help with a salary slip, tax information, or an HR question?',
        'Urdu': 'کیا آپ کو سیلری سلپ، ٹیکس کی معلومات یا HR کے سوال میں مدد چاہیے؟',
        'Roman Urdu': 'Kya aap ko salary slip, tax information, ya HR sawal mein madad chahiye?',
    }, {'salary slip': 'svc_pay_slip_latest', 'tax': 'svc_tax_certificate', 'hr': 'svc_contact_hr'}),
    'travel': ('travel services', {
        'English': 'Would you like to explore travel rules or start a travel request?',
        'Urdu': 'کیا آپ سفر کے قواعد جاننا یا سفر کی درخواست دینا چاہتے ہیں؟',
        'Roman Urdu': 'Kya aap travel rules jaanna ya travel request shuru karna chahte hain?',
    }, {'rules': 'what is my travel policy', 'apply': 'svc_trv_apply'}),
    'profile': ('profile services', {
        'English': 'Which profile detail would you like help reviewing or updating?',
        'Urdu': 'آپ اپنی پروفائل کی کون سی تفصیل دیکھنا یا درست کرنا چاہتے ہیں؟',
        'Roman Urdu': 'Aap profile ki kaunsi detail dekhna ya update karna chahte hain?',
    }, {'update': 'svc_update_profile', 'review': 'svc_my_profile'}),
    'careers': ('career guidance', {
        'English': 'Are you looking for vacancies, application guidance, or application status?',
        'Urdu': 'کیا آپ آسامیوں، درخواست دینے کے طریقے یا درخواست کی حیثیت کے بارے میں جاننا چاہتے ہیں؟',
        'Roman Urdu': 'Kya aap vacancies, apply karne ka tareeqa, ya application status jaanna chahte hain?',
    }, {'vacancies': 'svc_guest_careers', 'application status': 'svc_guest_job_status', 'guidance': 'how do I apply for a job at MicroMerger?'}),
    'onboarding': ('onboarding guidance', {
        'English': 'Which onboarding step or required document would you like help with?',
        'Urdu': 'آپ کو ملازمت شروع کرنے کے کس مرحلے یا دستاویز میں مدد چاہیے؟',
        'Roman Urdu': 'Aap ko onboarding ke kis step ya document mein madad chahiye?',
    }, {}),
    'documents': ('document guidance', {
        'English': 'Which document do you need, and what would you like help doing with it?',
        'Urdu': 'آپ کو کون سی دستاویز چاہیے اور اس کے لیے کیا مدد درکار ہے؟',
        'Roman Urdu': 'Aap ko kaunsa document chahiye aur us mein kya madad chahiye?',
    }, {}),
}


def guidance_category(intent, query=''):
    import re
    value = f'{intent} {query}'.lower().replace('_', ' ')
    for category, pattern in [
        ('careers',r'\b(career|careers|job|jobs|vacancies)\b'),
        ('onboarding',r'\b(onboarding|joining)\b'),
        ('leave',r'\b(leave|leaves)\b'),
        ('attendance',r'\b(attendance|checkin|checkout)\b'),
        ('payroll',r'\b(payroll|salary|payslip|tax|deduction|slip)\b'),
        ('travel',r'\b(travel|trv|dsa|expense)\b'),
        ('profile',r'\b(profile|department|designation|bank|contact)\b'),
        ('documents',r'\b(document|documents|letter|certificate)\b'),
    ]:
        if re.search(pattern,value):
            return category
    return None
