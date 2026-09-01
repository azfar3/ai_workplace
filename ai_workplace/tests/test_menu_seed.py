"""
ai_workplace/tests/test_menu_seed.py
──────────────────────────────────────
Validate WhatsApp Menu Item seed structure (parents & flow groups).
"""

import unittest

import frappe

from ai_workplace.menu.seed_data import FLOW_GROUP_SPECS, get_flow_menu_seed_items


class TestMenuSeedStructure(unittest.TestCase):
    def test_flow_items_have_parent_and_flow_group(self):
        for item in get_flow_menu_seed_items():
            self.assertTrue(item.get("is_flow_action"), item["menu_key"])
            self.assertTrue(item.get("flow_group"), f"{item['menu_key']} missing flow_group")
            if item["menu_key"] != "main_menu":
                self.assertTrue(
                    item.get("parent_menu_item"),
                    f"{item['menu_key']} missing parent_menu_item",
                )

    def test_flow_group_specs_reference_seeded_keys(self):
        seeded_keys = {item["menu_key"] for item in get_flow_menu_seed_items()}
        for group, keys in FLOW_GROUP_SPECS.items():
            for key in keys:
                if key == "main_menu" or key in seeded_keys:
                    continue
                # att_monthly is a regular submenu trigger, not a flow action seed row
                if key in ("att_monthly",):
                    continue
                self.fail(f"Flow group {group} references unknown key {key}")

    def test_db_flow_items_have_parents_after_seed(self):
        frappe.db.rollback()
        from ai_workplace.ai_workplace.doctype.whatsapp_menu_item.whatsapp_menu_item import (
            setup_default_menu_items,
        )

        setup_default_menu_items(force=True)
        rows = frappe.get_all(
            "WhatsApp Menu Item",
            filters={"is_flow_action": 1, "menu_key": ["!=", "main_menu"]},
            fields=["menu_key", "parent_menu_item", "flow_group"],
        )
        for row in rows:
            self.assertTrue(row.get("flow_group"), row["menu_key"])
            self.assertTrue(row.get("parent_menu_item"), row["menu_key"])
