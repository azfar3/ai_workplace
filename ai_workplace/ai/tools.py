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



def get_latest_salary_slip(employee: str) -> dict[str, Any]:
    from ai_workplace.services.payroll import get_past_salary_slips
    slips = get_past_salary_slips(employee, months=1)
    if not slips:
        return {}
    s = slips[0]
    return {
        "salary_slip_name": s.name,
        "start_date": str(s.start_date),
        "end_date": str(s.end_date),
        "net_pay": s.rounded_total
    }

def get_tax_details(employee: str) -> dict[str, Any]:
    from ai_workplace.services.payroll import get_past_salary_slips
    slips = get_past_salary_slips(employee, months=1)
    if not slips:
        return {}
    s = slips[0]
    return {
        "salary_slip_name": s.name,
        "start_date": str(s.start_date),
        "end_date": str(s.end_date),
        "total_deductions": s.total_deduction
    }

def get_office_timings(employee: Optional[str] = None) -> dict[str, Any]:
    from frappe.utils import today, formatdate, format_time
    
    office_days = "Monday to Friday"
    timings_str = ""
    
    try:
        settings = frappe.get_single("AI Workplace Settings")
        if getattr(settings, "office_hours_enabled", 0) and settings.office_start_time and settings.office_end_time:
            s_time = format_time(settings.office_start_time, "hh:mm a") if settings.office_start_time else "9:00 AM"
            e_time = format_time(settings.office_end_time, "hh:mm a") if settings.office_end_time else "5:00 PM"
            timings_str = f"{s_time} - {e_time}"
            if settings.office_days:
                office_days = settings.office_days
    except Exception:
        pass

    if not timings_str and employee:
        curr_today = today()
        try:
            shift = frappe.db.get_value(
                "Shift Assignment",
                {"employee": employee, "docstatus": 1, "start_date": ["<=", curr_today]},
                ["shift_type"],
                as_dict=True,
                order_by="start_date desc"
            )
            if shift and shift.get("shift_type"):
                stype = frappe.db.get_value("Shift Type", shift["shift_type"], ["start_time", "end_time"], as_dict=True)
                if stype and stype.get("start_time") and stype.get("end_time"):
                    s_time = format_time(stype["start_time"], "hh:mm a")
                    e_time = format_time(stype["end_time"], "hh:mm a")
                    timings_str = f"{s_time} - {e_time}"
        except Exception:
            pass

    if not timings_str:
        timings_str = "9:00 AM - 5:00 PM"

    curr_today = today()
    emp_hl_name = frappe.db.get_value("Employee", employee, "holiday_list") if employee else None
    
    is_active = False
    if emp_hl_name:
        hl_dates = frappe.db.get_value("Holiday List", emp_hl_name, ["from_date", "to_date"], as_dict=True)
        if hl_dates and str(hl_dates.from_date) <= curr_today <= str(hl_dates.to_date):
            is_active = True

    if not is_active:
        active_hl = frappe.db.get_value("Holiday List", {"from_date": ["<=", curr_today], "to_date": [">=", curr_today]}, "name")
        if active_hl:
            emp_hl_name = active_hl

    upcoming_holidays = []
    weekly_off = "Saturday & Sunday"

    if emp_hl_name:
        try:
            hl_doc = frappe.get_doc("Holiday List", emp_hl_name)
            if hl_doc.weekly_off:
                weekly_off = hl_doc.weekly_off

            h_records = frappe.db.get_all(
                "Holiday",
                filters={"parent": emp_hl_name, "holiday_date": [">=", curr_today]},
                fields=["holiday_date", "description"],
                order_by="holiday_date asc",
                limit=5
            )
            for h in h_records:
                upcoming_holidays.append({
                    "date": formatdate(h.get("holiday_date"), "dd MMM YYYY"),
                    "description": h.get("description") or "Holiday"
                })
        except Exception:
            pass

    return {
        "office_days": office_days,
        "timings": timings_str,
        "weekly_off": weekly_off,
        "holiday_list": emp_hl_name or "Standard Holiday Calendar",
        "upcoming_holidays": upcoming_holidays,
    }

def create_leave_application(employee: str, from_date: str, to_date: str, leave_type: str, reason: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    from ai_workplace.services.leave_apply import _create_leave_application
    draft = {
        "employee": employee,
        "from_date": from_date,
        "to_date": to_date,
        "leave_type": leave_type,
        "description": reason,
        "half_day": 0
    }
    
    # We pass a minimal context if none is provided, although run_tool should pass context soon.
    ctx = context or {"employee": employee}
    
    try:
        doc_name = _create_leave_application(draft, ctx)
        return {"status": "success", "message": f"Leave application {doc_name} submitted successfully."}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


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
    from ai_workplace.services.attendance_leave import get_today_attendance_data

    return get_today_attendance_data(employee)


def get_leave_balance(employee: str) -> list[dict[str, Any]]:
    from ai_workplace.services.attendance_leave import get_leave_balance_data
    return get_leave_balance_data(employee)



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
    return _search(query, limit=limit, employment_type=emp_type, context=context)


def get_leave_history(employee: str) -> list[dict[str, Any]]:
    from ai_workplace.services.attendance_leave import get_recent_leave_requests
    return get_recent_leave_requests(employee) or []


def get_employee_profile(employee: str) -> dict[str, Any]:
    from ai_workplace.services.hr_profile import get_employee_profile_data
    return get_employee_profile_data(employee) or {}


def get_monthly_attendance(employee: str, month: Optional[int] = None, year: Optional[int] = None) -> dict[str, Any]:
    from ai_workplace.services.attendance_leave import get_monthly_attendance_data
    return get_monthly_attendance_data(employee) or {}


# Tool Specification Registry with OpenAI Function Call Schemas & Security Metadata

from ai_workplace.ai.intent_catalog import INTENT_CATALOG

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}
for intent_name, meta in INTENT_CATALOG.items():
    tool_name = meta["tool"]
    if tool_name not in ["clarification"]:
        
        # Determine specific parameters based on tool_name
        params = {
            "type": "object",
            "properties": {},
            "required": []
        }
        if tool_name == "search_knowledge":
            params["properties"]["query"] = {"type": "string", "description": "The specific question or topic to search for in the knowledge base."}
            params["required"].append("query")
        elif tool_name == "create_leave_application":
            params["properties"]["from_date"] = {"type": "string", "description": "Start date in YYYY-MM-DD format."}
            params["properties"]["to_date"] = {"type": "string", "description": "End date in YYYY-MM-DD format."}
            params["properties"]["leave_type"] = {"type": "string", "description": "Type of leave (e.g. Annual Leave, Sick Leave)."}
            params["properties"]["reason"] = {"type": "string", "description": "Reason for leave."}
            params["required"].extend(["from_date", "to_date", "leave_type"])

        TOOL_REGISTRY[tool_name] = {
            "name": tool_name,
            "description": f"Tool for {intent_name}",
            "parameters": params,
            "read_write": "read" if meta.get("read_only", True) else "write",
            "data_sensitivity": "internal",
            "required_permissions": ["Employee"] if meta.get("requires_employee") else [],
            "pin_required": meta.get("requires_confirmation", False),
            "handler": globals().get(tool_name) or search_knowledge
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

    # 0. Tool Policy Engine - Phase A
    # Check if tool exists
    if tool_name not in TOOL_REGISTRY:
        return sanitize_tool_evidence(tool_name, {"error": f"Unknown tool: {tool_name}"}, context)

    meta = TOOL_REGISTRY[tool_name]
    auth_employee = context.get("employee") or ""

    # Check Required Permissions
    if "Employee" in meta.get("required_permissions", []) and not auth_employee:
        return sanitize_tool_evidence(tool_name, {"error": "Unauthorized: Employee context required to use this tool."}, context)

    # Check Pin Required (Confirmation)
    if meta.get("pin_required"):
        return sanitize_tool_evidence(tool_name, {"status": "pending_confirmation", "message": f"Draft created for {tool_name}. Awaiting user confirmation."}, context)

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
        elif tool_name == "get_leave_history":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_employee_profile":
            raw = meta["handler"](auth_employee)
        elif tool_name == "get_monthly_attendance":
            raw = meta["handler"](auth_employee, **clean_kwargs)
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
        elif tool_name == "create_leave_application":
            raw = meta["handler"](employee=auth_employee, context=context, **clean_kwargs)
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
