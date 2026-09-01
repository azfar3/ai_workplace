"""
Deterministic keyword → service routing (no LLM).
"""

from __future__ import annotations

# (keywords, service_key or submenu parent)
_KEYWORD_ROUTES: list[tuple[tuple[str, ...], str]] = [
    (("salary slip", "payslip", "payroll", "salary"), "payroll"),
    (("leave balance", "apply leave", "leave request", "chutti", "leave"), "attendance_leave"),
    (("check in", "checkin", "check out", "checkout", "attendance", "hazri"), "attendance_leave"),
    (("travel", "dsa", "safar", "claim"), "travel"),
    (("contract", "document", "letter", "certificate"), "documents"),
    (("profile", "supervisor", "my hr", "update details"), "hr"),
    (("policy", "policies", "sop"), "policies"),
    (("concern", "harassment", "misconduct", "complaint", "grievance"), "staff_support"),
    (("support", "help me", "workplace"), "staff_support"),
    (("chat with hr", "chat hr", "contact hr", "speak hr", "hr chat"), "contact_hr"),
    (("deliverable",), "deliverables"),
]


def match_keyword_service(text: str) -> str | None:
    """Return top-level service key if text matches a known employee request."""
    lower = (text or "").strip().lower()
    if len(lower) < 3:
        return None
    for keywords, service in _KEYWORD_ROUTES:
        if any(kw in lower for kw in keywords):
            return service
    return None
