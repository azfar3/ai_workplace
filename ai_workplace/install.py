"""
ai_workplace/install.py
───────────────────────
Post-install hooks for AI Workplace app setup.
"""

from __future__ import annotations

import frappe


HR_AGENT_ROLE = "HR Workplace Agent"
PAGE_NAME = "whatsapp-hr-inbox"
WORKSPACE_NAME = "Ai Workplace"


def after_install():
    setup_hr_live_chat()
    _ensure_default_menu_items()
    _ensure_security_policies()
    _ensure_knowledge_and_onboarding()


def after_migrate():
    setup_hr_live_chat()
    _ensure_default_menu_items()
    _ensure_security_policies()
    _ensure_knowledge_and_onboarding()


def setup_hr_live_chat():
    _ensure_hr_agent_role()
    _ensure_desk_page()
    _ensure_workspace_link()


def _ensure_default_menu_items():
    if not frappe.db or not frappe.db.exists("DocType", "WhatsApp Menu Item"):
        return

    from ai_workplace.ai_workplace.doctype.whatsapp_menu_item.whatsapp_menu_item import (
        setup_default_menu_items,
    )

    setup_default_menu_items(force=True)


def _ensure_security_policies():
    if not frappe.db or not frappe.db.exists("DocType", "WhatsApp Service Security Policy"):
        return

    from ai_workplace.security.seed_policies import setup_default_security_policies

    setup_default_security_policies(force=True)
    _ensure_ai_admin_page()


def _ensure_knowledge_and_onboarding():
    try:
        from ai_workplace.ai.seed_knowledge import setup_default_knowledge_sources

        setup_default_knowledge_sources(force=True)
    except Exception:
        pass
    try:
        from ai_workplace.services.onboarding import seed_default_onboarding_playbook

        seed_default_onboarding_playbook()
    except Exception:
        pass
    try:
        from ai_workplace.ai.seed_agents import setup_default_agents

        setup_default_agents(force=True)
    except Exception:
        pass


def _ensure_ai_admin_page():
    page_name = "ai-workplace-admin"
    if frappe.db.exists("Page", page_name):
        return
    page = frappe.new_doc("Page")
    page.page_name = page_name
    page.title = "AI Workplace Admin"
    page.module = "Ai Workplace"
    page.append("roles", {"role": "System Manager"})
    page.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_hr_agent_role():
    if frappe.db.exists("Role", HR_AGENT_ROLE):
        return

    role = frappe.new_doc("Role")
    role.role_name = HR_AGENT_ROLE
    role.desk_access = 1
    role.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_desk_page():
    if frappe.db.exists("Page", PAGE_NAME):
        return

    page = frappe.new_doc("Page")
    page.page_name = PAGE_NAME
    page.title = "WhatsApp HR Inbox"
    page.module = "Ai Workplace"
    for role_name in (HR_AGENT_ROLE, "HR Manager", "System Manager"):
        page.append("roles", {"role": role_name})
    page.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_workspace_link():
    if not frappe.db.exists("Workspace", WORKSPACE_NAME):
        return

    ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
    link_exists = any(
        link.link_type == "Page" and link.link_to == PAGE_NAME for link in (ws.links or [])
    )
    if link_exists:
        return

    ws.append(
        "links",
        {
            "type": "Link",
            "label": "WhatsApp HR Inbox",
            "link_type": "Page",
            "link_to": PAGE_NAME,
            "onboard": 0,
            "hidden": 0,
            "is_query_report": 0,
        },
    )
    ws.save(ignore_permissions=True)
    frappe.db.commit()
