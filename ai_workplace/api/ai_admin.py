"""
Whitelisted admin APIs for AI Workplace platform management.
"""

from __future__ import annotations

import secrets

import frappe

from ai_workplace.ai.indexer import reindex_all_sources, reindex_source


@frappe.whitelist()
def reindex_knowledge_source(source_name: str) -> dict:
    frappe.only_for("System Manager")
    count = reindex_source(source_name)
    return {"success": True, "source": source_name, "chunk_count": count}


@frappe.whitelist()
def reindex_all_knowledge_sources() -> dict:
    frappe.only_for("System Manager")
    counts = reindex_all_sources()
    return {"success": True, "sources": counts}


@frappe.whitelist()
def test_provider_connection(provider_name: str) -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("AI Workplace Provider", provider_name):
        frappe.throw("Provider not found")
    provider = frappe.get_doc("AI Workplace Provider", provider_name)
    return provider.test_connection()


@frappe.whitelist()
def get_providers_dashboard() -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("DocType", "AI Workplace Provider"):
        return {"providers": [], "summary": {}}

    providers = frappe.get_all(
        "AI Workplace Provider",
        fields=["name", "provider_name", "api_base_url", "priority", "is_active"],
        order_by="priority asc",
    )
    active = [p for p in providers if p.is_active]
    default = active[0] if active else None
    default_model = ""
    if default:
        default_model = (
            frappe.db.get_value(
                "AI Workplace Model",
                {"provider": default.name, "is_active": 1},
                "model_slug",
            )
            or ""
        )

    rows = []
    for p in providers:
        has_key = bool(frappe.db.get_value("AI Workplace Provider", p.name, "api_key"))
        model_slug = (
            frappe.db.get_value(
                "AI Workplace Model",
                {"provider": p.name, "is_active": 1},
                "model_slug",
            )
            or ""
        )
        rows.append(
            {
                "name": p.name,
                "provider_name": p.provider_name,
                "api_base_url": p.api_base_url or "",
                "has_api_key": has_key,
                "default_model": model_slug,
                "priority": p.priority,
                "is_active": p.is_active,
                "is_default": bool(default and p.name == default.name),
            }
        )

    return {
        "providers": rows,
        "summary": {
            "active_count": len(active),
            "total_count": len(providers),
            "default_provider": default.provider_name if default else "",
            "default_model": default_model,
            "fallback_count": max(0, len(active) - 1),
        },
    }


@frappe.whitelist()
def get_models_dashboard() -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("DocType", "AI Workplace Model"):
        return {"models": [], "summary": {}}

    models = frappe.get_all(
        "AI Workplace Model",
        fields=[
            "name",
            "model_slug",
            "display_name",
            "provider",
            "capabilities",
            "max_tokens",
            "temperature",
            "is_active",
        ],
        order_by="provider asc, model_slug asc",
    )
    active = sum(1 for m in models if m.is_active)
    rows = []
    for m in models:
        caps = (m.capabilities or "TEXT").upper()
        provider_name = frappe.db.get_value("AI Workplace Provider", m.provider, "provider_name") or m.provider
        rows.append(
            {
                "name": m.name,
                "model_slug": m.model_slug,
                "display_name": m.display_name or m.model_slug,
                "provider": provider_name,
                "capabilities": caps.split(",") if "," in caps else [caps],
                "supports_vision": "IMAGE" in caps,
                "max_tokens": m.max_tokens,
                "temperature": m.temperature,
                "is_active": m.is_active,
            }
        )

    return {
        "models": rows,
        "summary": {"active_count": active, "total_count": len(models)},
    }


@frappe.whitelist()
def get_agents_dashboard() -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("DocType", "AI Workplace Agent"):
        return {"agents": [], "endpoint_base": frappe.utils.get_url()}

    agents = frappe.get_all(
        "AI Workplace Agent",
        fields=[
            "name",
            "agent_slug",
            "agent_name",
            "agent_type",
            "default_model",
            "is_active",
            "allow_external_access",
            "allowed_applications",
            "rate_limit_per_minute",
        ],
        order_by="agent_name asc",
    )
    base = frappe.utils.get_url()
    rows = []
    for a in agents:
        model_slug = ""
        if a.default_model:
            model_slug = frappe.db.get_value("AI Workplace Model", a.default_model, "model_slug") or ""
        has_key = bool(frappe.db.get_value("AI Workplace Agent", a.name, "api_key"))
        rows.append(
            {
                **a,
                "default_model_slug": model_slug,
                "has_api_key": has_key,
                "endpoint_url": f"{base}/api/method/ai_workplace.api.agent_api.chat",
            }
        )

    settings = {}
    if frappe.db.exists("DocType", "AI Workplace Settings"):
        settings = frappe.get_single("AI Workplace Settings").as_dict()

    return {
        "agents": rows,
        "endpoint_base": base,
        "agent_settings": {
            "proactive_notifications_enabled": settings.get("proactive_notifications_enabled"),
            "proactive_gap_threshold": settings.get("proactive_gap_threshold"),
            "proactive_attendance_nudge": settings.get("proactive_attendance_nudge"),
            "proactive_cooldown_hours": settings.get("proactive_cooldown_hours"),
            "agent_confidence_threshold": settings.get("agent_confidence_threshold"),
        },
    }


@frappe.whitelist()
def generate_agent_api_key(agent_slug: str) -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("AI Workplace Agent", agent_slug):
        frappe.throw("Agent not found")

    key = secrets.token_urlsafe(32)
    doc = frappe.get_doc("AI Workplace Agent", agent_slug)
    doc.api_key = key
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "agent_slug": agent_slug, "api_key": key}


@frappe.whitelist()
def update_agent_share(agent_slug: str, allow_external_access: int = 0, allowed_applications: str = "") -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("AI Workplace Agent", agent_slug):
        frappe.throw("Agent not found")

    doc = frappe.get_doc("AI Workplace Agent", agent_slug)
    doc.allow_external_access = int(allow_external_access)
    doc.allowed_applications = allowed_applications
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def save_agent_preferences(
    proactive_notifications_enabled: int = 0,
    proactive_gap_threshold: int = 80,
    proactive_attendance_nudge: int = 1,
    proactive_cooldown_hours: int = 24,
    agent_confidence_threshold: float = 0,
) -> dict:
    frappe.only_for("System Manager")
    doc = frappe.get_single("AI Workplace Settings")
    doc.proactive_notifications_enabled = int(proactive_notifications_enabled)
    doc.proactive_gap_threshold = int(proactive_gap_threshold)
    doc.proactive_attendance_nudge = int(proactive_attendance_nudge)
    doc.proactive_cooldown_hours = int(proactive_cooldown_hours)
    doc.agent_confidence_threshold = float(agent_confidence_threshold)
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def get_usage_summary(days: int = 7) -> dict:
    frappe.only_for("System Manager")
    if not frappe.db.exists("DocType", "AI Workplace Usage Log"):
        return {"total": 0, "success": 0, "failed": 0}

    since = frappe.utils.add_days(frappe.utils.today(), -int(days))
    logs = frappe.get_all(
        "AI Workplace Usage Log",
        filters={"creation": [">=", since]},
        fields=["success"],
    )
    total = len(logs)
    success = sum(1 for row in logs if row.success)
    return {"total": total, "success": success, "failed": total - success, "days": days}
