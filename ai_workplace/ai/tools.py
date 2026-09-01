"""
Deterministic ERP tools for HR Agent — JSON only, no LLM invention.
Standardized OpenAI tool calling schema & strict server-side authorization.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import json

import frappe
from ai_workplace.ai.evidence import (
    CLASS_EMPLOYEE_SPECIFIC,
    CLASS_ORGANIZATIONAL,
    CLASS_SENSITIVE,
    CLASS_SYSTEM_INTERNAL,
)


def get_profile_gaps(employee: str) -> dict[str, Any]:
    from ai_workplace.services.profile_gaps import get_employee_profile_gaps

    return get_employee_profile_gaps(employee)


def get_pending_profile_requests(employee: str) -> list[dict[str, Any]]:
    if not frappe.db.exists("DocType", "Employee Profile Change Request"):
        return []
    return frappe.get_all(
        "Employee Profile Change Request",
        filters={"employee": employee, "status": ["not in", ["Applied", "Rejected"]]},
        fields=["name", "request_type", "status", "workflow_state", "modified"],
        order_by="modified desc",
        limit=10,
    )


def get_attendance_summary(employee: str) -> dict[str, Any]:
    from ai_workplace.services.attendance_guidance import get_attendance_snapshot

    return get_attendance_snapshot(employee)


def get_leave_balance(employee: str) -> list[dict[str, Any]]:
    try:
        from hrms.hr.doctype.leave_application.leave_application import get_leave_details
        from frappe.utils import today

        return get_leave_details(employee, date=today()).get("leave_allocation", {})
    except Exception:
        return {}


def get_published_policies(employee: str = "") -> list[dict[str, Any]]:
    try:
        from hrms.api.employee import get_policies_data

        return get_policies_data() or []
    except Exception:
        return []


def get_menu_help(context: dict[str, Any]) -> list[dict[str, Any]]:
    from ai_workplace.services.registry import get_available_services_for_context

    return get_available_services_for_context(context)


def get_portal_url(route: str = "/hrms") -> str:
    return frappe.utils.get_url(route)


def search_knowledge(query: str, limit: int = 5, context: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    from ai_workplace.ai.indexer import search_knowledge as _search

    emp_type = (context or {}).get("employment_type", "") if context else ""
    return _search(query, limit=limit, employment_type=emp_type)


# Tool Specification Registry with OpenAI Function Call Schemas & Security Metadata
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_profile_gaps": {
        "name": "get_profile_gaps",
        "description": "Fetch profile completeness score, missing fields, and pending requests for the authenticated employee.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_EMPLOYEE_SPECIFIC,
        "required_permissions": ["Employee"],
        "pin_required": False,
        "handler": get_profile_gaps,
    },
    "get_pending_profile_requests": {
        "name": "get_pending_profile_requests",
        "description": "Fetch pending profile update tickets submitted by the authenticated employee.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_EMPLOYEE_SPECIFIC,
        "required_permissions": ["Employee"],
        "pin_required": False,
        "handler": get_pending_profile_requests,
    },
    "get_attendance_summary": {
        "name": "get_attendance_summary",
        "description": "Fetch attendance status snapshot for today (check-in/out time) and monthly present/absent counts.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_EMPLOYEE_SPECIFIC,
        "required_permissions": ["Employee"],
        "pin_required": False,
        "handler": get_attendance_summary,
    },
    "get_leave_balance": {
        "name": "get_leave_balance",
        "description": "Fetch current leave allocations and remaining balances (annual, casual, sick) for the authenticated employee.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_EMPLOYEE_SPECIFIC,
        "required_permissions": ["Employee"],
        "pin_required": False,
        "handler": get_leave_balance,
    },
    "get_published_policies": {
        "name": "get_published_policies",
        "description": "Retrieve list of published company policies and handbook guidelines.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_ORGANIZATIONAL,
        "required_permissions": [],
        "pin_required": False,
        "handler": get_published_policies,
    },
    "get_menu_help": {
        "name": "get_menu_help",
        "description": "List available interactive WhatsApp menu services based on authenticated user context.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_ORGANIZATIONAL,
        "required_permissions": [],
        "pin_required": False,
        "handler": get_menu_help,
    },
    "get_portal_url": {
        "name": "get_portal_url",
        "description": "Get deep link URL to HRMS web portal or specific route.",
        "parameters": {
            "type": "object",
            "properties": {
                "route": {
                    "type": "string",
                    "description": "Portal route, e.g. '/hrms' or '/hrms/me'",
                }
            },
            "required": [],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_ORGANIZATIONAL,
        "required_permissions": [],
        "pin_required": False,
        "handler": get_portal_url,
    },
    "search_knowledge": {
        "name": "search_knowledge",
        "description": "Perform hybrid RAG search across company policy documents, SOPs, and portal guides.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search topic or question, e.g. 'maternity leave policy' or 'notice period'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of knowledge chunks to return (default 5).",
                },
            },
            "required": ["query"],
        },
        "read_write": "read",
        "data_sensitivity": CLASS_ORGANIZATIONAL,
        "required_permissions": [],
        "pin_required": False,
        "handler": search_knowledge,
    },
}


def get_openai_tools_schema(allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Generates standard OpenAI-compatible tool specifications."""
    tools = []
    for tool_name, meta in TOOL_REGISTRY.items():
        if allowed_tools is not None and tool_name not in allowed_tools:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": meta["name"],
                "description": meta["description"],
                "parameters": meta["parameters"],
            },
        })
    return tools


def run_tool(tool_name: str, context: dict[str, Any], **kwargs) -> Any:
    """
    Executes authorized tool function server-side.
    STRICT SECURITY ENFORCEMENT:
    1. Rejects / overrides any 'employee' parameter coming from LLM arguments.
    2. Enforces authenticated employee context from server session.
    3. Logs tool invocation to AI Action Log.
    4. Sanitizes raw output via Evidence Gateway.
    """
    from ai_workplace.ai.evidence import sanitize_tool_evidence

    if tool_name not in TOOL_REGISTRY:
        return sanitize_tool_evidence(tool_name, {"error": f"Unknown tool: {tool_name}"}, context)

    meta = TOOL_REGISTRY[tool_name]
    
    # 1. Strict Employee Identity Overriding — LLM arguments MUST NOT control identity!
    auth_employee = context.get("employee") or ""
    
    # Remove any identity arguments passed by LLM to prevent identity spoofing
    clean_kwargs = {k: v for k, v in kwargs.items() if k not in ("employee", "user", "erp_user")}

    # 2. Execute Handler
    try:
        if tool_name == "get_profile_gaps":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_pending_profile_requests":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_attendance_summary":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_leave_balance":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_published_policies":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_menu_help":
            raw = meta["handler"](context)
        elif tool_name == "get_portal_url":
            raw = meta["handler"](clean_kwargs.get("route", "/hrms"))
        elif tool_name == "search_knowledge":
            raw = meta["handler"](
                clean_kwargs.get("query", ""),
                limit=clean_kwargs.get("limit", 5),
                context=context,
            )
        else:
            raw = meta["handler"](**clean_kwargs)
    except Exception as exc:
        raw = {"error": f"Tool execution failed: {str(exc)}"}

    # 3. Log to AI Action Log
    _log_tool_action(tool_name, context, clean_kwargs, raw)

    # 4. Pass output through Evidence Gateway
    return sanitize_tool_evidence(tool_name, raw, context)


def _log_tool_action(tool_name: str, context: dict[str, Any], kwargs: dict[str, Any], result: Any) -> None:
    """Audit logs tool execution in AI Action Log."""
    try:
        if not frappe.db.exists("DocType", "AI Action Log"):
            return
        doc = frappe.new_doc("AI Action Log")
        ident = context.get("whatsapp_identity") or context.get("whatsapp_id")
        if ident and frappe.db.exists("WhatsApp Identity", ident):
            doc.whatsapp_identity = ident
        user = context.get("user") or ""
        if user and frappe.db.exists("User", user):
            doc.erp_user = user
        emp = context.get("employee") or ""
        if emp and frappe.db.exists("Employee", emp):
            doc.employee = emp
        doc.intent = "tool_execution"
        doc.service = tool_name
        doc.action = f"run_{tool_name}"
        doc.result = json.dumps({"kwargs": kwargs, "status": "error" if isinstance(result, dict) and "error" in result else "success"})[:500]
        doc.status = "Failed" if isinstance(result, dict) and "error" in result else "Success"
        doc.insert(ignore_permissions=True)
    except Exception:
        pass
