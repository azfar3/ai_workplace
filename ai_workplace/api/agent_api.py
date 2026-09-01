"""
External Agent API — share HR Agent with other applications (Portal, mobile, ai_analytics).
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

from ai_workplace.ai.router import complete
from ai_workplace.ai.tools import run_tool

HEADER_KEY = "X-AI-Workplace-Key"
APP_HEADER = "X-AI-Workplace-App"


def _extract_api_key() -> str:
    key = frappe.get_request_header(HEADER_KEY) or frappe.form_dict.get("api_key") or ""
    return (key or "").strip()


def _extract_app_name() -> str:
    return (frappe.get_request_header(APP_HEADER) or frappe.form_dict.get("app_name") or "").strip()


def _validate_agent_access(agent_slug: str, api_key: str, app_name: str = "") -> dict:
    if not agent_slug:
        frappe.throw("agent_slug is required", frappe.ValidationError)
    if not api_key:
        frappe.throw("API key required", frappe.AuthenticationError)

    if not frappe.db.exists("AI Workplace Agent", agent_slug):
        frappe.throw("Agent not found", frappe.DoesNotExistError)

    agent = frappe.get_doc("AI Workplace Agent", agent_slug)
    if not agent.is_active:
        frappe.throw("Agent is inactive", frappe.PermissionError)
    if not agent.allow_external_access:
        frappe.throw("External access is disabled for this agent", frappe.PermissionError)

    stored = ""
    try:
        stored = agent.get_password("api_key")
    except Exception:
        stored = agent.get("api_key") or ""
    if not stored or api_key != stored:
        frappe.throw("Invalid API key", frappe.AuthenticationError)

    if app_name and agent.allowed_applications:
        allowed = {a.strip().lower() for a in agent.allowed_applications.split(",") if a.strip()}
        if allowed and app_name.lower() not in allowed:
            frappe.throw(f"Application '{app_name}' is not authorized", frappe.PermissionError)

    _check_rate_limit(agent_slug, cint(agent.rate_limit_per_minute or 60))
    return agent.as_dict()


def _check_rate_limit(agent_slug: str, limit: int) -> None:
    if limit <= 0:
        return
    cache_key = f"awa_agent_rl:{agent_slug}"
    count = cint(frappe.cache().get_value(cache_key) or 0)
    if count >= limit:
        frappe.throw("Rate limit exceeded", frappe.TooManyRequestsError)
    frappe.cache().set_value(cache_key, count + 1, expires_in_sec=60)


@frappe.whitelist(allow_guest=True)
def chat(agent_slug: str, message: str, employee: str = "", context_json: str = "") -> dict:
    """
    External chat endpoint for shared agents.

    Headers:
      X-AI-Workplace-Key: agent API key
      X-AI-Workplace-App: calling application name (optional)
    """
    api_key = _extract_api_key()
    app_name = _extract_app_name()
    agent = _validate_agent_access(agent_slug, api_key, app_name)

    clean = (message or "").strip()
    if not clean:
        frappe.throw("message is required", frappe.ValidationError)

    context = {"employee": employee or ""}
    if context_json:
        import json

        try:
            context.update(json.loads(context_json))
        except Exception:
            pass

    system = agent.get("system_prompt") or ""
    model_slug = ""
    if agent.get("default_model"):
        model_slug = frappe.db.get_value("AI Workplace Model", agent.default_model, "model_slug") or ""

    tool_context = ""
    if employee:
        tool_context = f"\nProfile: {run_tool('get_profile_gaps', context)}"

    result = complete(
        f"User: {clean}\n{tool_context}",
        system=system,
        channel=f"API:{app_name or 'external'}",
        employee=employee,
        model_slug=model_slug,
    )

    return {
        "success": bool(result.get("success")),
        "reply": result.get("text", ""),
        "agent": agent_slug,
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
        "error": result.get("error", ""),
    }


@frappe.whitelist()
def get_integration_info(agent_slug: str) -> dict:
    """Return endpoint URL and sharing metadata for Desk admin UI."""
    frappe.only_for("System Manager")
    if not frappe.db.exists("AI Workplace Agent", agent_slug):
        frappe.throw("Agent not found")

    agent = frappe.get_doc("AI Workplace Agent", agent_slug)
    base = frappe.utils.get_url()
    return {
        "agent_slug": agent.agent_slug,
        "agent_name": agent.agent_name,
        "allow_external_access": agent.allow_external_access,
        "allowed_applications": agent.allowed_applications or "",
        "has_api_key": bool(agent.get("api_key")),
        "endpoint_url": f"{base}/api/method/ai_workplace.api.agent_api.chat",
        "headers": {
            HEADER_KEY: "<your-api-key>",
            APP_HEADER: "<calling-app-name>",
        },
        "example_curl": (
            f'curl -X POST "{base}/api/method/ai_workplace.api.agent_api.chat" '
            f'-H "Content-Type: application/json" '
            f'-H "{HEADER_KEY}: YOUR_API_KEY" '
            f'-H "{APP_HEADER}: hrms_portal" '
            f'-d \'{{"agent_slug": "{agent.agent_slug}", "message": "What is the leave policy?"}}\''
        ),
    }
