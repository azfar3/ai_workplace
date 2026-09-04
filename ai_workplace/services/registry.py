"""
ai_workplace/services/registry.py
───────────────────────────────────
Service Registry — menu items loaded from WhatsApp Menu Item doctype.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe

from ai_workplace.menu.seed_data import FLOW_GROUP_PROMPTS, FLOW_GROUP_SPECS
from ai_workplace.context.resolver import PAYROLL_SUBMENU_KEYS

# Pinned quick-action menu keys for active employees (employee-first UX)
ACTIVE_EMPLOYEE_QUICK_ACTION_KEYS = (
    "attendance_leave",
    "payroll",
    "contact_hr",
)

# Minimal fallback for items not stored in DB (navigation).
FALLBACK_SERVICES: dict[str, dict[str, Any]] = {
    "main_menu": {
        "key": "main_menu",
        "title": "🏠 Main Menu",
        "title_urdu": "🏠 اصلی مینو",
        "title_roman_urdu": "🏠 Main Menu",
        "mode": "available",
        "description": "Return to the main menu",
        "aliases": ["0", "main menu", "main_menu", "back", "menu", "home"],
    },
    "help": {
        "key": "help",
        "title": "Help / Change Language",
        "mode": "available",
        "description": "System help and language preference",
        "aliases": ["help", "language", "change language"],
    },
    "pay_slip_1m": {
        "key": "pay_slip_1m",
        "title": "📄 Last Month",
        "title_urdu": "📄 1 مہینہ",
        "title_roman_urdu": "📄 Last Month",
        "mode": "available",
        "description": "Last month payslip",
    },
    "pay_slip_3m": {
        "key": "pay_slip_3m",
        "title": "📄 Last 3 Months",
        "title_urdu": "📄 3 ماہ",
        "title_roman_urdu": "📄 Last 3 Months",
        "mode": "available",
        "description": "Last 3 months payslips",
    },
    "pay_slip_6m": {
        "key": "pay_slip_6m",
        "title": "📄 Last 6 Months",
        "title_urdu": "📄 6 ماہ",
        "title_roman_urdu": "📄 Last 6 Months",
        "mode": "available",
        "description": "Last 6 months payslips",
    },
}

BACK_TO_MAIN_MENU_ITEM: dict[str, Any] = FALLBACK_SERVICES["main_menu"]


def _user_category_for_context(context: dict[str, Any]) -> str:
    person_type = context.get("person_type", "Guest")
    if person_type in ("Former Employee", "Inactive"):
        return "Former Employee"
    if person_type == "Guest":
        return "Guest"
    return "Active Employee"


def _normalize_allowed_keys(allowed: list[str]) -> set[str]:
    keys = {s.lower() for s in allowed if s}
    if "policy" in keys:
        keys.add("policies")
    return keys


def _is_top_level_menu_item(item: dict[str, Any]) -> bool:
    return not (item.get("parent_menu_item") or "").strip()


def _has_flow_action_field() -> bool:
    try:
        return bool(frappe.get_meta("WhatsApp Menu Item").has_field("is_flow_action"))
    except Exception:
        return False


def _menu_records_to_services(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda row: (row.get("sequence") or 0, row.get("menu_key") or ""))
    return [
        {
            "key": item["menu_key"],
            "title": item["title"],
            "title_urdu": item.get("title_urdu") or item["title"],
            "title_roman_urdu": item.get("title_roman_urdu") or item["title"],
            "description": item.get("description") or "",
            "mode": "available",
            "sequence": item.get("sequence") or 0,
            "aliases": [item["menu_key"], (item.get("title") or "").lower()],
        }
        for item in ordered
    ]


def _fetch_menu_items(filters: dict[str, Any], fields: list[str] | None = None) -> list[dict[str, Any]]:
    if _has_flow_action_field() and "is_flow_action" not in filters:
        filters = {**filters, "is_flow_action": 0}
    default_fields = [
        "menu_key",
        "title",
        "title_urdu",
        "title_roman_urdu",
        "user_category",
        "parent_menu_item",
        "description",
        "sequence",
    ]
    return frappe.db.get_all(
        "WhatsApp Menu Item",
        filters=filters,
        fields=fields or default_fields,
        order_by="sequence asc",
    )


def get_service_info(service_key: str) -> Optional[dict[str, Any]]:
    """Return registration info for a service by key."""
    key_clean = (service_key or "").strip().lower()
    if key_clean in ("main_menu", "back_to_main", "svc_main_menu"):
        return BACK_TO_MAIN_MENU_ITEM

    if frappe.db and frappe.db.exists("WhatsApp Menu Item", service_key):
        item = frappe.get_doc("WhatsApp Menu Item", service_key)
        return {
            "key": item.menu_key,
            "title": item.title,
            "title_urdu": item.title_urdu or item.title,
            "title_roman_urdu": item.title_roman_urdu or item.title,
            "description": item.description or "",
            "mode": "available",
            "aliases": [item.menu_key, (item.title or "").lower()],
        }

    return FALLBACK_SERVICES.get(key_clean)


def get_flow_menu_items(flow_group: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Load ordered flow buttons for a dynamic group (titles from DB)."""
    keys = FLOW_GROUP_SPECS.get(flow_group) or []
    db_fields = [
        "menu_key",
        "title",
        "title_urdu",
        "title_roman_urdu",
        "description",
        "sequence",
        "flow_group",
        "parent_menu_item",
    ]

    by_key: dict[str, dict[str, Any]] = {}
    grouped = frappe.db.get_all(
        "WhatsApp Menu Item",
        filters={"flow_group": flow_group, "is_active": 1, "is_flow_action": 1},
        fields=db_fields,
        order_by="sequence asc",
    )
    for item in grouped:
        by_key[item["menu_key"]] = item

    lookup_keys = keys or [item["menu_key"] for item in grouped]
    missing_keys = [k for k in lookup_keys if k not in by_key]
    if missing_keys:
        extras = frappe.db.get_all(
            "WhatsApp Menu Item",
            filters={"menu_key": ["in", missing_keys], "is_active": 1},
            fields=db_fields,
        )
        for item in extras:
            by_key[item["menu_key"]] = item

    ordered_keys = keys or [item["menu_key"] for item in grouped]
    ordered = [by_key[k] for k in ordered_keys if k in by_key]

    if keys and len(ordered) < len(keys):
        for key in keys:
            if key not in by_key and key in FALLBACK_SERVICES:
                ordered.append({"menu_key": key, **FALLBACK_SERVICES[key]})

    return _menu_records_to_services(ordered)


def get_flow_group_prompt(flow_group: str, context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    prompts = FLOW_GROUP_PROMPTS.get(flow_group, {})
    return prompts.get(lang) or prompts.get("English") or "Choose an option:"


def _filter_submenu_items(
    items: list[dict[str, Any]],
    allowed: set[str],
    parent_key: str,
) -> list[dict[str, Any]]:
    """Filter submenu rows when staff have partial access to a parent menu."""
    parent = (parent_key or "").lower()
    if not allowed:
        return items

    if parent == "payroll" and allowed & PAYROLL_SUBMENU_KEYS:
        return [item for item in items if (item.get("menu_key") or "").lower() in allowed]

    if parent in allowed:
        return items

    return [item for item in items if (item.get("menu_key") or "").lower() in allowed]


def get_available_services_for_context(
    context: dict[str, Any],
    parent_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return menu services from WhatsApp Menu Item for the user's category."""
    category = _user_category_for_context(context)
    allowed = _normalize_allowed_keys(context.get("allowed_services") or [])

    try:
        if parent_key:
            db_items = _fetch_menu_items(
                {
                    "is_active": 1,
                    "parent_menu_item": parent_key,
                    "user_category": ["in", [category, "All"]],
                }
            )
            if db_items:
                filtered = _filter_submenu_items(db_items, allowed, parent_key)
                results = _menu_records_to_services(filtered)
                if not any(r["key"] == "main_menu" for r in results):
                    results.append(BACK_TO_MAIN_MENU_ITEM)
                return results
            return []

        db_items = _fetch_menu_items(
            {
                "is_active": 1,
                "user_category": ["in", [category, "All"]],
            }
        )
        top_level = [item for item in db_items if _is_top_level_menu_item(item)]
        if allowed:
            top_level = [item for item in top_level if item["menu_key"].lower() in allowed]
        if top_level:
            return _menu_records_to_services(top_level)
    except Exception:
        pass

    # Minimal DB-unavailable fallback when allowed_services is set
    if allowed:
        results = []
        for key in allowed:
            if key in FALLBACK_SERVICES:
                results.append(FALLBACK_SERVICES[key])
        return results
    return []
