"""
ai_workplace/ai/intent_catalog.py
──────────────────────────────────
Deterministic Intent Catalog.

Each entry defines a mappable employee intent with:
  intents        — internal keyword identifiers (used by Layer 4 keyword scorer)
  aliases        — exact / near-exact phrases (used by Layers 1 & 2)
  tool           — tool function name to call (see ai/tools.py)
  response_mode  — "deterministic" | "hybrid" | "clarification" | "workflow" | "escalate"
  workflow_intent— when response_mode="workflow", the orchestrator intent key to activate
  requires_authentication — employee session required
  llm_allowed    — whether the LLM may be involved in answering
  source_type    — ERP | RAG | FAQ | MIXED | NAVIGATION | ORGANIZATION

Scoring priority: exact alias (1.0) > regex pattern (0.85) > alias substring (0.80) > keyword (0.70)
"""

from __future__ import annotations
from typing import Any, Dict

INTENT_CATALOG: Dict[str, Dict[str, Any]] = {

    # ══════════════════════════════════════════════════════════════════════════
    # LEAVE
    # ══════════════════════════════════════════════════════════════════════════

    "leave_balance": {
        "category": "leave",
        "intents": ["leave_balance", "show_leave_balance", "my_leaves", "how_many_leaves"],
        "aliases": [
            "how many leaves do i have",
            "what is my leave balance",
            "show my remaining leaves",
            "how much leave is left",
            "how many leaves are remaining",
            "mere kitne leaves hain",
            "meri leave balance batao",
            "leave balance",
            "my leave balance",
            "how many annual leaves remaining",
            "how many casual leaves remaining",
            "how many sick leaves remaining",
        ],
        "tool": "get_leave_balance",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "apply_leave": {
        "category": "leave",
        "intents": ["apply_leave", "create_leave_application", "submit_leave", "request_leave"],
        "aliases": [
            "i want to apply for leave",
            "apply for leave",
            "apply leave",
            "request leave",
            "submit a leave request",
            "chutti chahiye",
            "chutti leni hai",
            "take leave",
            "need a leave",
            "leave application",
        ],
        "tool": None,
        "requires_authentication": True,
        "read_only": False,
        "requires_confirmation": True,
        "llm_allowed": False,
        "response_mode": "workflow",
        "workflow_intent": "leave_apply",
        "source_type": "ERP",
    },

    "leave_history": {
        "category": "leave",
        "intents": ["leave_history", "my_leaves_taken", "past_leaves"],
        "aliases": [
            "show my leave history",
            "my leave history",
            "leaves i have taken",
            "how many leaves did i take",
            "leave record",
            "previous leave",
            "past leaves",
        ],
        "tool": "get_leave_history",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "show_leave": {
        "category": "leave",
        "intents": ["show_leave"],
        "aliases": [
            "show my leave",
            "my leave details",
            "leave record",
            "leave info",
        ],
        "tool": "clarification",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "clarification",
        "source_type": "NAVIGATION",
    },

    "carry_forward_leave": {
        "category": "leave",
        "intents": ["carry_forward_leave", "leave_carryforward"],
        "aliases": [
            "can i carry forward my remaining 4 leaves",
            "how many leaves can i carry forward",
            "carry forward leave",
            "can unused leave be carried forward",
            "what happens to unused annual leave",
            "leave encashment",
        ],
        "tool": "search_knowledge",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": True,
        "response_mode": "hybrid",
        "source_type": "MIXED",
    },

    "leave_application_procedure": {
        "category": "procedure",
        "intents": ["leave_application_procedure", "how_to_apply_leave"],
        "aliases": [
            "how do i apply for leave",
            "what is the procedure for leave application",
            "how to apply leave",
            "leave apply karna hai",
        ],
        "tool": "search_knowledge",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": True,
        "response_mode": "hybrid",
        "source_type": "FAQ",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # ATTENDANCE
    # ══════════════════════════════════════════════════════════════════════════

    "today_attendance": {
        "category": "attendance",
        "intents": ["today_attendance", "attendance_summary", "checkin_status"],
        "aliases": [
            "today attendance",
            "my attendance today",
            "aaj ki attendance",
            "did i check in today",
            "have i checked in",
            "check in status today",
            "aaj check in hua",
            "what time did i check in",
            "my check in time",
        ],
        "tool": "get_attendance_summary",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "monthly_attendance": {
        "category": "attendance",
        "intents": ["monthly_attendance", "attendance_report"],
        "aliases": [
            "show my attendance for this month",
            "monthly attendance",
            "attendance this month",
            "attendance summary",
            "my attendance record",
            "august attendance",
            "last month attendance",
        ],
        "tool": "get_monthly_attendance",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "forgot_checkin": {
        "category": "attendance",
        "intents": ["forgot_checkin", "missed_checkin", "attendance_exception"],
        "aliases": [
            "i forgot to check in",
            "i forgot to check in today",
            "missed check in",
            "check in nahi hua",
            "i didn't check in",
            "i did not check in today",
            "bhool gaya check in",
        ],
        "tool": None,
        "requires_authentication": True,
        "read_only": False,
        "requires_confirmation": True,
        "llm_allowed": False,
        "response_mode": "workflow",
        "workflow_intent": "att_exception",
        "source_type": "ERP",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PAYROLL
    # ══════════════════════════════════════════════════════════════════════════

    "latest_salary_slip": {
        "category": "payroll",
        "intents": ["latest_salary_slip", "salary_slip", "show_salary_slip", "payslip"],
        "aliases": [
            "show my salary slip",
            "salary slip",
            "show my payslip",
            "send salary slip",
            "latest salary",
            "meri salary slip bhejo",
            "download salary slip",
            "my salary slip",
            "get my payslip",
            "view salary slip",
        ],
        "tool": "get_latest_salary_slip",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "tax_deductions": {
        "category": "payroll",
        "intents": ["tax_deductions", "how_much_tax", "income_tax"],
        "aliases": [
            "how much was deducted in tax",
            "my tax deductions",
            "mera tax kitna kata",
            "income tax deduction",
            "tax details",
            "how much tax was deducted",
            "tax summary",
        ],
        "tool": "get_tax_details",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "tax_policy": {
        "category": "policy",
        "intents": ["tax_policy", "why_tax_deducted"],
        "aliases": [
            "why is tax deducted",
            "tax rules",
            "how is tax calculated",
            "tax calculation policy",
        ],
        "tool": "search_knowledge",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": True,
        "response_mode": "hybrid",
        "source_type": "RAG",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # EMPLOYEE PROFILE
    # ══════════════════════════════════════════════════════════════════════════

    "my_designation": {
        "category": "employee",
        "intents": ["designation", "job_title", "my_designation"],
        "aliases": [
            "what is my designation",
            "my designation",
            "my job title",
            "my position",
            "what is my job title",
            "mera designation kya hai",
            "meri post kya hai",
        ],
        "tool": "get_employee_profile",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "my_department": {
        "category": "employee",
        "intents": ["department", "my_department"],
        "aliases": [
            "what department am i in",
            "my department",
            "which department am i in",
            "mera department kya hai",
            "which dept do i belong to",
        ],
        "tool": "get_employee_profile",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "profile_gaps": {
        "category": "employee",
        "intents": ["profile_gaps", "profile_completion", "missing_profile"],
        "aliases": [
            "my profile gaps",
            "profile completion",
            "what is missing in my profile",
            "profile complete karna hai",
            "incomplete profile",
            "profile status",
        ],
        "tool": "get_profile_gaps",
        "requires_authentication": True,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # POLICY / KNOWLEDGE
    # ══════════════════════════════════════════════════════════════════════════

    "maternity_leave_policy": {
        "category": "policy",
        "intents": ["maternity_leave_policy", "maternity_leave"],
        "aliases": [
            "what is the maternity leave policy",
            "maternity leave details",
            "maternity leave rules",
            "how many days maternity leave",
            "paternity leave policy",
        ],
        "tool": "search_knowledge",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": True,
        "response_mode": "hybrid",
        "source_type": "RAG",
    },

    "policy_count": {
        "category": "policy",
        "intents": ["policy_count", "how_many_policies"],
        "aliases": [
            "how many polices are there",
            "total policies",
            "how many policies do we have",
        ],
        "tool": "get_published_policies",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "policy_list": {
        "category": "policy",
        "intents": ["policy_list", "show_policies", "all_policies"],
        "aliases": [
            "show me the published policies",
            "list of policies",
            "show all policies",
            "available policies",
            "company policies",
            "hr policies",
        ],
        "tool": "get_published_policies",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ERP",
    },

    "travel_allowance_policy": {
        "category": "travel",
        "intents": ["travel_allowance_policy", "dsa_policy"],
        "aliases": [
            "what is the travel allowance",
            "travel policy",
            "dsa policy",
            "travel allowance rules",
            "safar allowance",
        ],
        "tool": "search_knowledge",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": True,
        "response_mode": "hybrid",
        "source_type": "RAG",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # ORGANISATION / NAVIGATION
    # ══════════════════════════════════════════════════════════════════════════

    "office_timings": {
        "category": "organization",
        "intents": ["office_timings", "office_hours", "work_timings"],
        "aliases": [
            "what are the office timings",
            "office hours",
            "timings",
            "office time",
            "work hours",
            "when does office start",
            "when does office end",
            "office schedule",
        ],
        "tool": "get_office_timings",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "ORGANIZATION",
    },

    "menu_help": {
        "category": "navigation",
        "intents": ["menu_help", "bot_capabilities", "what_can_you_do"],
        "aliases": [
            "what can you do",
            "help",
            "menu",
            "show menu",
            "what services do you offer",
            "what can i ask",
            "list all services",
        ],
        "tool": "get_menu_help",
        "requires_authentication": False,
        "read_only": True,
        "requires_confirmation": False,
        "llm_allowed": False,
        "response_mode": "deterministic",
        "source_type": "NAVIGATION",
    },
}
