"""
Menu registry integrity — seed structure, unique keys, parents, security levels.
"""

from __future__ import annotations

import unittest

from ai_workplace.menu.seed_data import get_flow_menu_seed_items, get_menu_seed_items
from ai_workplace.conversation.orchestrator import SERVICE_ALIASES, _resolve_service_key

# Leaf menu keys with deterministic handlers (or alias targets) in orchestrator
_KNOWN_LEAF_HANDLERS = frozenset(
    {
        "att_today",
        "att_checkin",
        "att_checkout",
        "att_monthly",
        "att_missing",
        "leave_balance",
        "leave_apply",
        "leave_requests",
        "pay_download_slip",
        "pay_previous_slips",
        "pay_tax_deduction",
        "pay_experience_letter",
        "pay_bank_letter",
        "trv_apply",
        "trv_approved",
        "trv_upcoming",
        "trv_claim_status",
        "trv_vehicle_info",
        "trv_sop",
        "trv_problem",
        "doc_contract",
        "my_day",
        "my_profile",
        "supervisor_reporting",
        "update_profile",
        "prof_my_requests",
        "hr_pin_help",
        "concerns",
        "contact_hr",
        "pol_view_policies",
        "pol_ai_assistant",
        "dlv_add",
        "dlv_submit",
        "dlv_status",
        "former_letter",
        "former_payslip",
        "former_verification",
        "former_concern",
        "former_careers",
        "guest_careers",
        "guest_job_status",
        "guest_verification",
        "guest_vendor",
        "guest_concern",
        "guest_number_changed",
    }
)

_PARENT_MENU_KEYS = frozenset(
    {
        "attendance_leave",
        "payroll",
        "travel",
        "documents",
        "hr",
        "staff_support",
        "policies",
        "deliverables",
    }
)


def _flatten_seed_items() -> list[dict]:
    rows: list[dict] = []
    for item in get_menu_seed_items():
        parent = dict(item)
        submenus = parent.pop("submenus", [])
        rows.append(parent)
        for sub in submenus:
            rows.append({**sub, "parent_menu_item": item["menu_key"]})
    rows.extend(get_flow_menu_seed_items())
    return rows


class TestMenuSeedIntegrity(unittest.TestCase):
    def test_menu_keys_unique(self):
        keys = [row["menu_key"] for row in _flatten_seed_items()]
        self.assertEqual(len(keys), len(set(keys)), f"Duplicate keys: {[k for k in keys if keys.count(k) > 1]}")

    def test_submenu_parents_exist(self):
        all_keys = {row["menu_key"] for row in _flatten_seed_items()}
        for row in _flatten_seed_items():
            parent = row.get("parent_menu_item")
            if parent:
                self.assertIn(parent, all_keys, f"{row['menu_key']} parent {parent} missing")

    def test_security_level_defined_on_submenus(self):
        for row in _flatten_seed_items():
            if row.get("parent_menu_item") or row.get("is_flow_action"):
                self.assertIn(
                    "security_level",
                    row,
                    f"{row['menu_key']} missing security_level",
                )

    def test_active_employee_top_level_services(self):
        top = [i for i in get_menu_seed_items() if i.get("user_category") == "Active Employee" and "submenus" in i]
        keys = {i["menu_key"] for i in top}
        for expected in ("attendance_leave", "payroll", "travel", "documents", "hr", "staff_support", "policies"):
            self.assertIn(expected, keys)

    def test_leaf_items_have_handler_or_alias(self):
        for row in _flatten_seed_items():
            key = row["menu_key"]
            if key in _PARENT_MENU_KEYS or key == "main_menu":
                continue
            if row.get("is_flow_action"):
                continue
            if key in SERVICE_ALIASES:
                target = SERVICE_ALIASES[key]
                self.assertIn(target, _KNOWN_LEAF_HANDLERS | _PARENT_MENU_KEYS | set(SERVICE_ALIASES.values()))
                continue
            self.assertIn(
                key,
                _KNOWN_LEAF_HANDLERS | set(SERVICE_ALIASES.keys()),
                f"No handler registered for leaf menu key: {key}",
            )

    def test_service_aliases_resolve(self):
        self.assertEqual(_resolve_service_key("doc_salary_slip"), "pay_download_slip")
        self.assertEqual(_resolve_service_key("staff_supervisor"), "supervisor_reporting")
        self.assertEqual(_resolve_service_key("attendance_leave"), "attendance_leave")


if __name__ == "__main__":
    unittest.main()
