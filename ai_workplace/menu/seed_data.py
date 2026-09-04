"""
ai_workplace/menu/seed_data.py
────────────────────────────────
Canonical WhatsApp Menu Item definitions (DB seed source).
"""

from __future__ import annotations

from typing import Any

# Security level values stored on WhatsApp Menu Item
SEC_NONE = "None"
SEC_PIN = "PIN Required"
SEC_PIN_APPROVAL = "PIN + Approval"


def get_menu_seed_items() -> list[dict[str, Any]]:
    """Top-level and nested menu items (submenus key). Employee-first Staff Support layout."""
    return [
        {
            "menu_key": "attendance_leave",
            "title": "🕒 Attendance & Leave",
            "title_urdu": "🕒 حاضری اور رخصت",
            "title_roman_urdu": "🕒 Attendance & Leave",
            "user_category": "Active Employee",
            "sequence": 1,
            "description": "Check in/out, view attendance, apply for leave and track requests.",
            "submenus": [
                {"menu_key": "att_today", "title": "📅 Today's Attendance", "title_urdu": "📅 آج کی حاضری", "title_roman_urdu": "📅 Today's Attendance", "description": "Today's check-in/out status.", "sequence": 1, "security_level": SEC_NONE},
                {"menu_key": "att_checkin", "title": "✅ Check In", "title_urdu": "✅ چیک ان", "title_roman_urdu": "✅ Check In", "description": "Mark check-in with WhatsApp location.", "sequence": 2, "security_level": SEC_NONE},
                {"menu_key": "att_checkout", "title": "🚪 Check Out", "title_urdu": "🚪 چیک آؤٹ", "title_roman_urdu": "🚪 Check Out", "description": "Mark check-out with WhatsApp location.", "sequence": 3, "security_level": SEC_NONE},
                {"menu_key": "att_monthly", "title": "🗓️ Monthly Attendance", "title_urdu": "🗓️ ماہانہ حاضری", "title_roman_urdu": "🗓️ Monthly Attendance", "description": "Monthly attendance summary.", "sequence": 4, "security_level": SEC_PIN},
                {"menu_key": "att_missing", "title": "⚠️ Missing Attendance", "title_urdu": "⚠️ گمشدہ حاضری", "title_roman_urdu": "⚠️ Missing Attendance", "description": "Review missing attendance days.", "sequence": 5, "security_level": SEC_PIN},
                {"menu_key": "leave_balance", "title": "📊 Leave Balance", "title_urdu": "📊 رخصت کا بیلنس", "title_roman_urdu": "📊 Leave Balance", "description": "Remaining leave balance.", "sequence": 6, "security_level": SEC_PIN},
                {"menu_key": "leave_apply", "title": "📝 Apply for Leave", "title_urdu": "📝 رخصت کی درخواست", "title_roman_urdu": "📝 Apply Leave", "description": "Submit a leave application.", "sequence": 7, "security_level": SEC_PIN},
                {"menu_key": "leave_requests", "title": "📋 My Leave Requests", "title_urdu": "📋 میری رخصت کی درخواستیں", "title_roman_urdu": "📋 My Leave Requests", "description": "Track leave request status.", "sequence": 8, "security_level": SEC_PIN},
            ],
        },
        {
            "menu_key": "payroll",
            "title": "💰 Salary & Payroll",
            "title_urdu": "💰 تنخواہ اور پے رول",
            "title_roman_urdu": "💰 Salary & Payroll",
            "user_category": "Active Employee",
            "sequence": 2,
            "description": "Salary slips, tax documents and payroll information.",
            "submenus": [
                {"menu_key": "pay_download_slip", "title": "📥 Salary Slip", "title_urdu": "📥 سیلری سلپ", "title_roman_urdu": "📥 Salary Slip", "description": "Download salary slips as PDF (1, 3 or 6 months).", "sequence": 1, "security_level": SEC_PIN},
                {"menu_key": "pay_tax_deduction", "title": "🧾 Tax Certificate", "title_urdu": "🧾 ٹیکس سرٹیفکیٹ", "title_roman_urdu": "🧾 Tax Certificate", "description": "Tax deduction certificate.", "sequence": 2, "security_level": SEC_PIN},
                {"menu_key": "pay_experience_letter", "title": "📄 Experience Letter", "title_urdu": "📄 تجربہ سرٹیفکیٹ", "title_roman_urdu": "📄 Experience Letter", "description": "Service / experience certificate.", "sequence": 3, "security_level": SEC_PIN},
                {"menu_key": "pay_bank_letter", "title": "🏦 Bank Letter", "title_urdu": "🏦 بینک لیٹر", "title_roman_urdu": "🏦 Bank Letter", "description": "Bank account verification letter.", "sequence": 4, "security_level": SEC_PIN},
            ],
        },
        {
            "menu_key": "travel",
            "title": "🚗 Travel & DSA",
            "title_urdu": "🚗 سفر اور DSA",
            "title_roman_urdu": "🚗 Travel & DSA",
            "user_category": "Active Employee",
            "sequence": 3,
            "description": "Travel requests, approvals, claims and DSA policy.",
            "submenus": [
                {"menu_key": "trv_apply", "title": "➕ Request Travel Authorisation", "title_urdu": "➕ سفری منظوری کی درخواست", "title_roman_urdu": "➕ Request Travel Authorisation", "sequence": 0, "description": "Submit a new travel authorisation request.", "security_level": SEC_PIN},
                {"menu_key": "trv_approved", "title": "✅ My Approved Travel", "sequence": 1, "description": "Approved travel itineraries.", "security_level": SEC_PIN},
                {"menu_key": "trv_upcoming", "title": "🔜 Upcoming Travel", "sequence": 2, "description": "Scheduled upcoming visits.", "security_level": SEC_PIN},
                {"menu_key": "trv_claim_status", "title": "🔄 Claim Status", "sequence": 3, "description": "Travel expense claim status.", "security_level": SEC_PIN},
                {"menu_key": "trv_vehicle_info", "title": "🚙 Vehicle / Driver", "sequence": 4, "description": "Allocated vehicles and drivers.", "security_level": SEC_PIN},
                {"menu_key": "trv_sop", "title": "📖 Travel & DSA Policy", "sequence": 5, "description": "Travel SOP and DSA rates.", "security_level": SEC_NONE},
                {"menu_key": "trv_problem", "title": "🚨 Travel Support", "sequence": 6, "description": "Report a travel problem.", "security_level": SEC_NONE},
            ],
        },
        {
            "menu_key": "documents",
            "title": "📄 Documents & Contract",
            "title_urdu": "📄 دستاویزات اور معاہدہ",
            "title_roman_urdu": "📄 Documents & Contract",
            "user_category": "Active Employee",
            "sequence": 4,
            "description": "Employment documents, contracts and HR letters.",
            "submenus": [
                {"menu_key": "doc_contract", "title": "📃 Current Contract", "sequence": 1, "description": "View contract status and signing.", "security_level": SEC_PIN},
                {"menu_key": "doc_salary_slip", "title": "📥 Salary Slip", "sequence": 2, "description": "Latest payslip.", "security_level": SEC_PIN},
                {"menu_key": "doc_tax_cert", "title": "🧾 Tax Certificate", "sequence": 3, "description": "Tax deduction certificate.", "security_level": SEC_PIN},
                {"menu_key": "doc_experience_letter", "title": "📄 Experience Letter", "sequence": 4, "description": "Service / experience certificate.", "security_level": SEC_PIN},
                {"menu_key": "doc_bank_letter", "title": "🏦 Bank Letter", "sequence": 5, "description": "Bank verification letter.", "security_level": SEC_PIN},
                {"menu_key": "doc_my_requests", "title": "📋 My Document Requests", "sequence": 6, "description": "Track HR document requests.", "security_level": SEC_PIN},
            ],
        },
        {
            "menu_key": "hr",
            "title": "👤 My Profile & Documents",
            "title_urdu": "👤 میری پروفائل اور دستاویزات",
            "title_roman_urdu": "👤 My Profile & Documents",
            "user_category": "Active Employee",
            "sequence": 5,
            "description": "Profile information, supervisor, documents and update requests.",
            "submenus": [
                {"menu_key": "my_day", "title": "☀️ My Day", "title_urdu": "☀️ میرا دن", "title_roman_urdu": "☀️ My Day", "description": "Today's attendance, leave and actions.", "sequence": 5, "security_level": SEC_NONE},
                {"menu_key": "my_profile", "title": "👤 My Profile", "title_urdu": "👤 میری پروفائل", "title_roman_urdu": "👤 My Profile", "description": "View profile, contact and bank details.", "sequence": 10, "security_level": SEC_PIN},
                {"menu_key": "supervisor_reporting", "title": "👨‍💼 Supervisor & Reporting", "title_urdu": "👨‍💼 سپروائزر اور رپورٹنگ", "title_roman_urdu": "👨‍💼 Supervisor & Reporting", "description": "Supervisor and reporting contact details.", "sequence": 20, "security_level": SEC_PIN},
                {"menu_key": "update_profile", "title": "🛠️ Update My Details", "title_urdu": "🛠️ اپنی تفصیلات اپ ڈیٹ", "title_roman_urdu": "🛠️ Update My Details", "description": "Review or update personal information.", "sequence": 30, "security_level": SEC_PIN},
                {"menu_key": "prof_my_requests", "title": "📋 My Requests", "title_urdu": "📋 میری درخواستیں", "title_roman_urdu": "📋 My Requests", "description": "Track profile and change requests.", "sequence": 40, "security_level": SEC_PIN},
                {"menu_key": "hr_pin_help", "title": "🔐 Support PIN Help", "title_urdu": "🔐 Support PIN مدد", "title_roman_urdu": "🔐 Support PIN Help", "description": "How to set or reset Support PIN in HRMIS.", "sequence": 50, "security_level": SEC_NONE},
            ],
        },
        {
            "menu_key": "staff_support",
            "title": "💙 Staff Support",
            "title_urdu": "💙 ملازمین کی معاونت",
            "title_roman_urdu": "💙 Staff Support",
            "user_category": "Active Employee",
            "sequence": 6,
            "description": "Workplace guidance, safety and confidential matters.",
            "submenus": [
                {"menu_key": "staff_hr_guidance", "title": "🤖 AI Policy Assistant", "title_urdu": "🤖 AI پالیسی اسسٹنٹ", "title_roman_urdu": "🤖 AI Policy Assistant", "sequence": 1, "description": "Ask AI any company policy or workplace question.", "security_level": SEC_NONE},
                {"menu_key": "staff_supervisor", "title": "👨‍💼 Supervisor Support", "sequence": 2, "description": "Supervisor and reporting contact.", "security_level": SEC_PIN},
                {"menu_key": "concerns", "title": "🔒 Confidential Concern", "sequence": 3, "description": "Report a confidential workplace concern.", "security_level": SEC_NONE},
                {"menu_key": "staff_contact_hr", "title": "💬 Chat with HR", "sequence": 4, "description": "Speak with HR live on WhatsApp.", "security_level": SEC_NONE},
            ],
        },
        {
            "menu_key": "policies",
            "title": "🤖 AI Policy Assistant",
            "title_urdu": "🤖 AI پالیسی اسسٹنٹ",
            "title_roman_urdu": "🤖 AI Policy Assistant",
            "user_category": "Active Employee",
            "sequence": 7,
            "description": "Ask AI Assistant any question about company policies.",
            "security_level": SEC_NONE,
        },
        {
            "menu_key": "deliverables",
            "title": "📦 Deliverables",
            "title_urdu": "📦 ڈیلیوریبلز",
            "title_roman_urdu": "📦 Deliverables",
            "user_category": "Active Employee",
            "sequence": 8,
            "description": "Add, submit and track project deliverables.",
            "submenus": [
                {"menu_key": "dlv_add", "title": "➕ Add Deliverable", "title_urdu": "➕ ڈیلیوریبل شامل کریں", "title_roman_urdu": "➕ Add Deliverable", "description": "Create a new deliverable draft.", "sequence": 1, "security_level": SEC_NONE},
                {"menu_key": "dlv_submit", "title": "📤 Submit for Approval", "title_urdu": "📤 منظوری کے لیے بھیجیں", "title_roman_urdu": "📤 Submit", "description": "Send deliverable for approval.", "sequence": 2, "security_level": SEC_NONE},
                {"menu_key": "dlv_status", "title": "📋 My Deliverables", "title_urdu": "📋 میرے ڈیلیوریبلز", "title_roman_urdu": "📋 My Deliverables", "description": "View deliverable status.", "sequence": 3, "security_level": SEC_NONE},
            ],
        },
        {
            "menu_key": "contact_hr",
            "title": "💬 Chat with HR",
            "title_urdu": "💬 HR سے بات کریں",
            "title_roman_urdu": "💬 Chat with HR",
            "user_category": "All",
            "sequence": 9,
            "description": "Connect with HR support on WhatsApp.",
            "security_level": SEC_NONE,
        },
        # Former Employee
        {"menu_key": "former_letter", "title": "📄 Experience / Service Letter", "title_urdu": "📄 تجربہ / سروس لیٹر", "title_roman_urdu": "📄 Experience Letter", "user_category": "Former Employee", "sequence": 1, "description": "Download experience / service certificate.", "security_level": SEC_PIN},
        {"menu_key": "former_payslip", "title": "🧾 Payslip & Tax Documents", "title_urdu": "🧾 پے سلپ", "title_roman_urdu": "🧾 Payslip", "user_category": "Former Employee", "sequence": 2, "description": "Download salary slips (up to 6 months).", "security_level": SEC_PIN},
        {"menu_key": "former_verification", "title": "🔍 Employment Verification", "user_category": "Former Employee", "sequence": 3, "description": "Employment verification request.", "security_level": SEC_NONE},
        {"menu_key": "former_concern", "title": "🛡️ Report a Concern", "title_urdu": "🛡️ شکایت درج کریں", "title_roman_urdu": "🛡️ Report Concern", "user_category": "Former Employee", "sequence": 4, "description": "Confidential workplace concern.", "security_level": SEC_NONE},
        {"menu_key": "former_careers", "title": "💼 Career Opportunities", "user_category": "Former Employee", "sequence": 5, "description": "Job vacancies.", "security_level": SEC_NONE},
        # contact_hr (user_category All) covers former employees too
        # Guest
        {"menu_key": "guest_careers", "title": "💼 Careers at MicroMerger", "user_category": "Guest", "sequence": 1, "description": "Browse job openings.", "security_level": SEC_NONE},
        {"menu_key": "guest_job_status", "title": "📝 I Applied for a Job", "user_category": "Guest", "sequence": 2, "description": "Application status.", "security_level": SEC_NONE},
        {"menu_key": "guest_verification", "title": "🔍 Employment Verification", "user_category": "Guest", "sequence": 3, "description": "Verify employee records.", "security_level": SEC_NONE},
        {"menu_key": "guest_vendor", "title": "🤝 Vendor / Supplier Support", "user_category": "Guest", "sequence": 4, "description": "Vendor support.", "security_level": SEC_NONE},
        {"menu_key": "guest_concern", "title": "🛡️ Report a Concern", "title_urdu": "🛡️ شکایت درج کریں", "title_roman_urdu": "🛡️ Shikayat Darj Karein", "user_category": "Guest", "sequence": 5, "description": "Submit confidential reports on grievances, harassment, fraud, or safety issues.", "security_level": SEC_NONE},
        {"menu_key": "guest_number_changed", "title": "🔐 My number has changed", "user_category": "Guest", "sequence": 7, "description": "Link new WhatsApp number.", "security_level": SEC_NONE},
    ]


def get_flow_menu_seed_items() -> list[dict[str, Any]]:
    """Dynamic flow buttons (hidden from standard menus; parent = trigger menu item)."""
    common = {"is_flow_action": 1, "is_active": 1, "user_category": "All"}
    return [
        {
            **common,
            "menu_key": "pay_slip_1m",
            "parent_menu_item": "pay_download_slip",
            "flow_group": "salary_slip_period",
            "title": "📄 Last Month",
            "title_urdu": "📄 1 مہینہ",
            "title_roman_urdu": "📄 Last Month",
            "sequence": 1,
            "description": "Last month payslip.",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "pay_slip_3m",
            "parent_menu_item": "pay_download_slip",
            "flow_group": "salary_slip_period",
            "title": "📄 Last 3 Months",
            "title_urdu": "📄 3 ماہ",
            "title_roman_urdu": "📄 Last 3 Months",
            "sequence": 2,
            "description": "Last 3 months payslips.",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "pay_slip_6m",
            "parent_menu_item": "pay_download_slip",
            "flow_group": "salary_slip_period",
            "title": "📄 Last 6 Months",
            "title_urdu": "📄 6 ماہ",
            "title_roman_urdu": "📄 Last 6 Months",
            "sequence": 3,
            "description": "Last 6 months payslips.",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "pay_bank_faysal",
            "parent_menu_item": "pay_bank_letter",
            "flow_group": "bank_letter_select",
            "title": "🏦 Faysal Bank",
            "sequence": 1,
            "description": "Bank letter for Faysal Bank",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "pay_bank_scb",
            "parent_menu_item": "pay_bank_letter",
            "flow_group": "bank_letter_select",
            "title": "🏦 Standard Chartered",
            "sequence": 2,
            "description": "Bank letter for SCB",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "att_monthly_last7",
            "parent_menu_item": "att_monthly",
            "flow_group": "att_monthly_summary",
            "title": "📋 Last 7 Days",
            "title_urdu": "📋 7 دن",
            "title_roman_urdu": "📋 Last 7 Days",
            "sequence": 1,
            "description": "Last 7 working days attendance",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "att_monthly_download",
            "parent_menu_item": "att_monthly",
            "flow_group": "att_monthly_summary",
            "title": "📥 Full Month",
            "title_urdu": "📥 Excel",
            "title_roman_urdu": "📥 Full Month",
            "sequence": 2,
            "description": "Download full month attendance Excel",
            "security_level": SEC_PIN,
        },
        {
            **common,
            "menu_key": "main_menu",
            "flow_group": "main_nav",
            "title": "🏠 Main Menu",
            "title_urdu": "🏠 مینو",
            "title_roman_urdu": "🏠 Main Menu",
            "sequence": 99,
            "description": "Return to main menu",
            "security_level": SEC_NONE,
        },
    ]


# Ordered button keys per dynamic flow (titles loaded from WhatsApp Menu Item records).
FLOW_GROUP_SPECS: dict[str, list[str]] = {
    "salary_slip_period": ["pay_slip_1m", "pay_slip_3m", "pay_slip_6m"],
    "bank_letter_select": ["pay_bank_faysal", "pay_bank_scb"],
    "att_monthly_summary": ["att_monthly_last7", "att_monthly_download", "main_menu"],
    "att_monthly_detail": ["att_monthly_download", "att_monthly", "main_menu"],
    "main_nav": ["main_menu"],
}


FLOW_GROUP_PROMPTS: dict[str, dict[str, str]] = {
    "salary_slip_period": {
        "English": "How many months of payslips?",
        "Urdu": "کتنے مہینوں کی سلپ چاہیے؟",
        "Roman Urdu": "Kitne mahine ki slip chahiye?",
    },
    "bank_letter_select": {
        "English": "Select your bank for the letter:",
        "Urdu": "لیٹر کے لیے بینک منتخب کریں:",
        "Roman Urdu": "Letter ke liye bank select karein:",
    },
    "att_monthly_summary": {
        "English": "What would you like next?",
        "Urdu": "آگے کیا دیکھنا ہے؟",
        "Roman Urdu": "Aage kya dekhna hai?",
    },
    "att_monthly_detail": {
        "English": "What would you like next?",
        "Urdu": "آگے کیا دیکھنا ہے؟",
        "Roman Urdu": "Aage kya dekhna hai?",
    },
    "main_nav": {
        "English": "Need something else?",
        "Urdu": "مزید اختیارات کے لیے مینو کھولیں:",
        "Roman Urdu": "Kuch aur chahiye?",
    },
}


LEGACY_MENU_KEYS = (
    "hr_profile",
    "hr_reporting",
    "hr_update_info",
    "guest_contact",
    "former_contact",
    "concerns",
    "con_pseah",
    "con_abuse_authority",
    "con_fraud",
    "con_retaliation",
    "con_unethical",
    "con_safety",
    "con_wrongdoing",
    "con_anonymous_info",
    # Orphan policy / legacy submenus not in canonical seed
    "pay_previous_slips",
    "pol_view_policies",
    "pol_ai_assistant",
    "pol_casual_leaves",
    "pol_att_policy",
    "pol_personal_vehicle",
    "pol_absence_policy",
    "pol_dsa_policy",
    "pol_notice_period",
)
