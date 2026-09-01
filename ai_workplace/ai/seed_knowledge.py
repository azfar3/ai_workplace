"""
Seed default AI Workplace Knowledge Sources and reindex.
"""

from __future__ import annotations

import os

import frappe

from ai_workplace.ai.indexer import reindex_source

DEFAULT_SOURCES = [
    {
        "source_name": "policies",
        "source_type": "Policy",
        "description": "Published HR policies from HRMS",
        "is_active": 1,
    },
    {
        "source_name": "menu_catalog",
        "source_type": "MenuCatalog",
        "description": "WhatsApp menu catalog for agent routing",
        "is_active": 1,
    },
    {
        "source_name": "portal_help",
        "source_type": "PortalHelp",
        "description": "HRMIS Portal how-to guides",
        "is_active": 1,
    },
    {
        "source_name": "onboarding_default",
        "source_type": "Onboarding",
        "description": "New hire onboarding orientation content",
        "is_active": 1,
    },
]


def setup_default_knowledge_sources(force: bool = False) -> None:
    if not frappe.db.exists("DocType", "AI Workplace Knowledge Source"):
        return

    portal_content = _load_portal_guides()
    for spec in DEFAULT_SOURCES:
        name = spec["source_name"]
        payload = dict(spec)
        if spec["source_type"] == "PortalHelp" and portal_content:
            payload["content"] = portal_content

        if frappe.db.exists("AI Workplace Knowledge Source", name):
            if force:
                doc = frappe.get_doc("AI Workplace Knowledge Source", name)
                doc.update({k: v for k, v in payload.items() if k != "source_name"})
                doc.flags.ignore_permissions = True
                doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "AI Workplace Knowledge Source", **payload}).insert(
                ignore_permissions=True
            )

        try:
            reindex_source(name)
        except Exception:
            frappe.logger("ai_workplace").warning(f"Could not reindex knowledge source {name}")

    frappe.db.commit()


def _load_portal_guides() -> str:
    guides_dir = os.path.join(
        frappe.get_app_path("ai_workplace"),
        "doc",
        "portal_guides",
    )
    if not os.path.isdir(guides_dir):
        return ""
    parts = []
    for fname in sorted(os.listdir(guides_dir)):
        if fname.endswith(".md"):
            path = os.path.join(guides_dir, fname)
            with open(path, encoding="utf-8") as f:
                parts.append(f"# {fname}\n\n{f.read()}")
    return "\n\n---\n\n".join(parts)
