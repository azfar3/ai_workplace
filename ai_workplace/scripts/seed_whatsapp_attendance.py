"""
Seed default Mobile Attendance record for Head Office WhatsApp attendance pilot.
"""

from __future__ import annotations

import frappe


def seed_head_office_mobile_attendance() -> str:
    name = "Islamabad Head Office"
    if frappe.db.exists("Mobile Attendance", name):
        doc = frappe.get_doc("Mobile Attendance", name)
    else:
        doc = frappe.new_doc("Mobile Attendance")
        doc.name1 = name

    doc.allow_attendance_through_mobile_app = 1
    doc.geofence_is_must = 1
    doc.allow_whatsapp_location_attendance = 1
    doc.allow_outside_geofence_exception = 1
    doc.location_display_name = "Islamabad Office"
    doc.lat = "33.6844"
    doc.lang = "73.0479"
    doc.radius = 200
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)

    try:
        frappe.db.set_single_value("AI Workplace Settings", "whatsapp_attendance_enabled", 1)
        if not frappe.db.get_single_value("AI Workplace Settings", "whatsapp_attendance_pending_ttl_minutes"):
            frappe.db.set_single_value("AI Workplace Settings", "whatsapp_attendance_pending_ttl_minutes", 10)
    except Exception:
        pass

    frappe.db.commit()
    return doc.name


def execute():
    seed_head_office_mobile_attendance()
