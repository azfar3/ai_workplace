"""
Seed default AI Workplace Agent records.
"""

from __future__ import annotations

import secrets

import frappe

from ai_workplace.ai.prompts.reactive_qa import REACTIVE_QA

DEFAULT_AGENTS = [
    {
        "agent_slug": "hr_agent",
        "agent_name": "MicroMerger HR Agent",
        "agent_type": "HR Agent",
        "description": "WhatsApp and API HR assistant for policies, profile, and attendance.",
        "system_prompt": REACTIVE_QA,
        "allow_external_access": 1,
        "allowed_applications": "hrms_portal,ai_analytics,mobile_app",
    },
    {
        "agent_slug": "onboarding_agent",
        "agent_name": "New Hire Onboarding Agent",
        "agent_type": "Onboarding Agent",
        "description": "Orientation assistant for employees within first 30 days.",
        "system_prompt": "You are MicroMerger's onboarding assistant for new hires.",
        "allow_external_access": 0,
        "allowed_applications": "hrms_portal",
    },
]


def setup_default_agents(force: bool = False) -> None:
    if not frappe.db.exists("DocType", "AI Workplace Agent"):
        return

    default_model = frappe.db.get_value("AI Workplace Model", {"is_active": 1}, "name")

    for spec in DEFAULT_AGENTS:
        slug = spec["agent_slug"]
        if frappe.db.exists("AI Workplace Agent", slug):
            if force:
                doc = frappe.get_doc("AI Workplace Agent", slug)
                doc.update({k: v for k, v in spec.items() if k != "agent_slug"})
                if default_model and not doc.default_model:
                    doc.default_model = default_model
                doc.flags.ignore_permissions = True
                doc.save(ignore_permissions=True)
            continue

        doc = frappe.get_doc(
            {
                "doctype": "AI Workplace Agent",
                **spec,
                "is_active": 1,
                "default_model": default_model,
            }
        )
        key = secrets.token_urlsafe(32)
        doc.api_key = key
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
