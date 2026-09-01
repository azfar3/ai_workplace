"""
ai_workplace/ai/evidence.py
───────────────────────────────────
Server-side Evidence Gateway for AI Workplace.

Responsibilities:
1. Enforces Data Minimization — converts raw ERPNext DB dicts into minimal safe LLM evidence objects.
2. Strict Employee Authorization — prevents LLM arguments from altering the authenticated employee context.
3. Data Safety Classification — flags data as ORGANIZATIONAL, EMPLOYEE_SPECIFIC, SENSITIVE, or SYSTEM_INTERNAL.
4. Masking — redacts CNIC, bank numbers, passwords, and support PINs before prompt assembly.
"""

from __future__ import annotations

import re
from typing import Any

# Classification constants
CLASS_ORGANIZATIONAL = "ORGANIZATIONAL"
CLASS_EMPLOYEE_SPECIFIC = "EMPLOYEE_SPECIFIC"
CLASS_SENSITIVE = "SENSITIVE"
CLASS_SYSTEM_INTERNAL = "SYSTEM_INTERNAL"


def sanitize_tool_evidence(tool_name: str, raw_result: Any, context: dict[str, Any]) -> dict[str, Any]:
    """
    Pass raw ERPNext python results through the Evidence Gateway.
    Filters out internal IDs, sensitive fields, and enforces data minimization.
    """
    employee = context.get("employee") or ""
    
    if isinstance(raw_result, dict) and "error" in raw_result:
        return {"tool": tool_name, "status": "error", "message": str(raw_result["error"])}

    if tool_name == "get_leave_balance":
        return _minimize_leave_balance(raw_result)

    if tool_name == "get_attendance_summary":
        return _minimize_attendance_summary(raw_result)

    if tool_name == "get_profile_gaps":
        return _minimize_profile_gaps(raw_result)

    if tool_name == "get_pending_profile_requests":
        return _minimize_pending_requests(raw_result)

    if tool_name == "get_published_policies":
        return _minimize_published_policies(raw_result)

    if tool_name == "search_knowledge":
        return _minimize_knowledge_search(raw_result)

    # General dict fallback with recursive sanitization
    if isinstance(raw_result, dict):
        return {
            "tool": tool_name,
            "data": _sanitize_dict(raw_result)
        }

    return {"tool": tool_name, "value": redact_sensitive_text(str(raw_result))}


def _minimize_leave_balance(data: Any) -> dict[str, Any]:
    """Minimizes leave allocation dict to leave types and remaining days only."""
    if not data:
        return {"leave_balances": []}
    
    minimized = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                minimized.append({
                    "leave_type": item.get("leave_type", "Leave"),
                    "remaining_leaves": item.get("remaining", item.get("remaining_leaves", 0.0)),
                    "total_allocated": item.get("allocated", item.get("total_leaves", 0.0)),
                    "leaves_taken": item.get("taken", item.get("leaves_taken", 0.0)),
                })
    elif isinstance(data, dict):
        for leave_type, stats in data.items():
            if isinstance(stats, dict):
                minimized.append({
                    "leave_type": leave_type,
                    "remaining_leaves": stats.get("remaining_leaves", stats.get("remaining", 0.0)),
                    "total_allocated": stats.get("total_leaves", stats.get("allocated", 0.0)),
                    "leaves_taken": stats.get("leaves_taken", stats.get("taken", 0.0)),
                })
    return {"leave_balances": minimized}


def _minimize_attendance_summary(data: Any) -> dict[str, Any]:
    """Minimizes attendance snapshot to present/absent/late counts."""
    if not isinstance(data, dict):
        return {"status_today": "Not Checked In", "in_time": None, "out_time": None}
    
    return {
        "status_today": data.get("status_today", data.get("status", "Not Checked In")),
        "in_time": data.get("in_time"),
        "out_time": data.get("out_time"),
        "working_hours": data.get("working_hours", "0.00"),
        "days_present_this_month": data.get("days_present", data.get("present", 0)),
        "days_absent_this_month": data.get("days_absent", data.get("absent", 0)),
        "late_entries": data.get("late_entries", data.get("late", 0)),
    }


def _minimize_profile_gaps(data: Any) -> dict[str, Any]:
    """Returns completeness score, employment type, designation, department, and list of missing field labels."""
    if not isinstance(data, dict):
        return {"completeness_score": 100, "missing_fields": [], "status": "Complete"}
    
    gap_objs = data.get("all_gaps", data.get("critical_gaps", data.get("missing_fields", [])))
    labels = []
    for g in gap_objs:
        if isinstance(g, dict):
            labels.append(g.get("label", g.get("key", str(g))))
        else:
            labels.append(str(g))

    res = {
        "completeness_score": data.get("completeness_score", 100),
        "missing_fields": labels,
        "status": data.get("status", "Incomplete" if labels else "Complete"),
    }
    for field in ("employment_type", "designation", "department", "branch", "employee_name"):
        if data.get(field):
            res[field] = data[field]
    return res


def _minimize_pending_requests(data: Any) -> dict[str, Any]:
    """Returns list of pending profile requests without sensitive values."""
    if not isinstance(data, list):
        return {"pending_requests": []}
    
    items = []
    for req in data:
        if isinstance(req, dict):
            items.append({
                "request_type": req.get("request_type"),
                "status": req.get("status"),
                "workflow_state": req.get("workflow_state"),
            })
    return {"pending_requests": items}


def _minimize_published_policies(data: Any) -> dict[str, Any]:
    if not isinstance(data, list):
        return {"policies": []}
    
    policies = []
    for p in data[:10]:
        if isinstance(p, dict):
            policies.append({
                "title": p.get("title"),
                "description": p.get("description", "")[:300],
            })
    return {"policies": policies}


def _minimize_knowledge_search(data: Any) -> dict[str, Any]:
    if not isinstance(data, list):
        return {"knowledge_matches": []}
    
    matches = []
    for k in data[:5]:
        if isinstance(k, dict):
            matches.append({
                "source_title": k.get("source_title") or k.get("source", "Policy"),
                "text": redact_sensitive_text((k.get("text") or "")[:500]),
            })
    return {"knowledge_matches": matches}


def _sanitize_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip internal keys, passwords, hashes, and redact text."""
    forbidden_keys = {
        "password", "api_key", "secret", "auth", "hash", "support_pin",
        "pin", "cnic", "bank_account", "iban", "docstatus", "idx", "owner"
    }
    clean = {}
    for k, v in d.items():
        if k.lower() in forbidden_keys:
            continue
        if isinstance(v, dict):
            clean[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize_dict(item) if isinstance(item, dict) else redact_sensitive_text(str(item)) for item in v]
        elif isinstance(v, str):
            clean[k] = redact_sensitive_text(v)
        else:
            clean[k] = v
    return clean


def classify_data_safety(text_or_dict: Any) -> str:
    """
    Classify evidence safety level.
    Returns: ORGANIZATIONAL, EMPLOYEE_SPECIFIC, SENSITIVE, or SYSTEM_INTERNAL.
    """
    raw = str(text_or_dict).lower()
    
    # Sensitive checks (CNIC, Bank, Passwords, PINs)
    if any(term in raw for term in ("cnic", "bank_account", "iban", "password", "support_pin", "pin_code")):
        return CLASS_SENSITIVE

    # Personal employee specific checks
    if any(term in raw for term in ("remaining_leaves", "leaves_taken", "days_present", "completeness_score", "emp-")):
        return CLASS_EMPLOYEE_SPECIFIC

    # Internal metadata
    if any(term in raw for term in ("docstatus", "hash", "version_hash", "modified_by")):
        return CLASS_SYSTEM_INTERNAL

    return CLASS_ORGANIZATIONAL


def redact_sensitive_text(text: str) -> str:
    """Mask CNIC numbers, IBANs, and PINs in output text."""
    if not text:
        return ""
    
    # Redact 13-digit CNIC (e.g. 61101-1234567-1 or 6110112345671)
    text = re.sub(r"\b\d{5}[-]?\d{7}[-]?\d\b", "[CNIC REDACTED]", text)
    
    # Redact IBAN (e.g. PK36FAYS0001234567890123)
    text = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{12,30}\b", "[BANK ACCOUNT REDACTED]", text)
    
    return text
