"""
Resolve menu security levels from WhatsApp Menu Item records.
"""

from __future__ import annotations

import frappe

POLICY_NONE = "none"
POLICY_PIN_REQUIRED = "pin_required"
POLICY_PIN_PLUS_APPROVAL = "pin_plus_approval"

MENU_SECURITY_CACHE_PREFIX = "wa_menu_sec:"


def menu_security_label_to_policy(label: str | None) -> str:
    if label == "PIN Required":
        return POLICY_PIN_REQUIRED
    if label == "PIN + Approval":
        return POLICY_PIN_PLUS_APPROVAL
    return POLICY_NONE


def get_menu_item_security_policy(menu_key: str) -> str | None:
    """Return policy from WhatsApp Menu Item, or None if not configured in menu catalog."""
    if not menu_key or not frappe.db.exists("DocType", "WhatsApp Menu Item"):
        return None

    cache_key = f"{MENU_SECURITY_CACHE_PREFIX}{menu_key}"
    cached = frappe.cache().get_value(cache_key)
    if cached is not None:
        return cached or None

    if not frappe.db.exists("WhatsApp Menu Item", menu_key):
        frappe.cache().set_value(cache_key, "", expires_in_sec=300)
        return None

    row = frappe.db.get_value(
        "WhatsApp Menu Item",
        menu_key,
        ["security_level", "is_active"],
        as_dict=True,
    )
    if not row or not row.is_active:
        frappe.cache().set_value(cache_key, "", expires_in_sec=300)
        return None

    policy = menu_security_label_to_policy(row.security_level)
    frappe.cache().set_value(cache_key, policy, expires_in_sec=300)
    return policy


def clear_menu_security_cache(menu_key: str | None = None) -> None:
    if menu_key:
        frappe.cache().delete_value(f"{MENU_SECURITY_CACHE_PREFIX}{menu_key}")
        return
    frappe.cache().delete_keys(f"{MENU_SECURITY_CACHE_PREFIX}*")
