# Copyright (c) 2026, MicroMerger and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ai_workplace.menu.seed_data import (
    LEGACY_MENU_KEYS,
    get_flow_menu_seed_items,
    get_menu_seed_items,
)
from ai_workplace.security.menu_security import clear_menu_security_cache


class WhatsAppMenuItem(Document):
    def on_update(self):
        clear_menu_security_cache(self.menu_key)

    def on_trash(self):
        clear_menu_security_cache(self.menu_key)


def _upsert_menu_item(payload: dict) -> None:
    key = payload["menu_key"]
    if frappe.db.exists("WhatsApp Menu Item", key):
        doc = frappe.get_doc("WhatsApp Menu Item", key)
        doc.update(payload)
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({"doctype": "WhatsApp Menu Item", **payload}).insert(ignore_permissions=True)


def setup_default_menu_items(force: bool = False) -> None:
    """
    Upsert WhatsApp Menu Item records from canonical seed data.
    Called on install/migrate (force=True) or when table is empty.
    """
    if not force and frappe.db.count("WhatsApp Menu Item") > 0:
        return

    for item_data in get_menu_seed_items():
        submenus = item_data.pop("submenus", [])
        parent_category = item_data.get("user_category", "Active Employee")
        _upsert_menu_item({
            **item_data,
            "is_flow_action": item_data.get("is_flow_action", 0),
            "security_level": item_data.get("security_level", "None"),
        })

        for sub in submenus:
            sub_payload = {
                "menu_key": sub["menu_key"],
                "title": sub["title"],
                "title_urdu": sub.get("title_urdu", sub["title"]),
                "title_roman_urdu": sub.get("title_roman_urdu", sub["title"]),
                "description": sub.get("description", ""),
                "user_category": sub.get("user_category", parent_category),
                "parent_menu_item": item_data["menu_key"],
                "sequence": sub.get("sequence", 0),
                "is_active": 1,
                "is_flow_action": 0,
                "security_level": sub.get("security_level", "None"),
            }
            _upsert_menu_item(sub_payload)

    for flow_item in get_flow_menu_seed_items():
        _upsert_menu_item(flow_item)

    for legacy_key in LEGACY_MENU_KEYS:
        if frappe.db.exists("WhatsApp Menu Item", legacy_key):
            frappe.delete_doc("WhatsApp Menu Item", legacy_key, ignore_permissions=True, force=True)

    frappe.db.commit()
