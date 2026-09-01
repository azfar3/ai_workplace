"""Fetch recent error logs."""
import frappe


def run():
    rows = frappe.get_all(
        "Error Log",
        filters={"creation": [">=", "2026-08-31 18:40:00"]},
        fields=["name", "method", "error", "creation"],
        order_by="creation desc",
        limit=5,
    )
    for r in rows:
        print("---", r.name, r.creation, r.method)
        print((r.error or "")[:2000])
