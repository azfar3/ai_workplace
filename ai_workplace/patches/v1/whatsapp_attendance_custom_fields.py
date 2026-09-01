"""
Create custom fields for WhatsApp location attendance on Employee Checkin and Attendance Request.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(_employee_checkin_fields(), ignore_validate=True)
    create_custom_fields(_attendance_request_fields(), ignore_validate=True)
    frappe.db.commit()


def _employee_checkin_fields() -> dict:
    return {
        "Employee Checkin": [
            {
                "fieldname": "custom_log_from",
                "label": "Log From",
                "fieldtype": "Select",
                "options": "Mobile\nWhatsApp\nBiometric\nAttendance Request\nDesk",
                "insert_after": "device_id",
            },
            {
                "fieldname": "custom_whatsapp_message_id",
                "label": "WhatsApp Message ID",
                "fieldtype": "Data",
                "insert_after": "custom_log_from",
                "unique": 1,
            },
            {
                "fieldname": "custom_server_received_at",
                "label": "Server Received At",
                "fieldtype": "Datetime",
                "insert_after": "custom_whatsapp_message_id",
                "read_only": 1,
            },
            {
                "fieldname": "custom_distance_from_work_location",
                "label": "Distance From Work Location (m)",
                "fieldtype": "Float",
                "insert_after": "custom_server_received_at",
                "read_only": 1,
            },
            {
                "fieldname": "custom_geofence_result",
                "label": "Geofence Result",
                "fieldtype": "Select",
                "options": "Inside\nOutside\nExempt\nNot Required",
                "insert_after": "custom_distance_from_work_location",
                "read_only": 1,
            },
            {
                "fieldname": "custom_assigned_mobile_attendance",
                "label": "Assigned Mobile Attendance",
                "fieldtype": "Link",
                "options": "Mobile Attendance",
                "insert_after": "custom_geofence_result",
                "read_only": 1,
            },
        ]
    }


def _attendance_request_fields() -> dict:
    return {
        "Attendance Request": [
            {
                "fieldname": "custom_geofence_exception",
                "label": "Geofence Exception",
                "fieldtype": "Check",
                "insert_after": "explanation",
                "default": "0",
            },
            {
                "fieldname": "custom_exception_reason",
                "label": "Exception Reason",
                "fieldtype": "Select",
                "options": "\nField Visit\nOfficial Travel\nAssigned Meeting\nTemporary Duty Location\nWorksite Visit\nLocation/GPS Problem\nOther",
                "insert_after": "custom_geofence_exception",
            },
            {
                "fieldname": "custom_checkin_latitude",
                "label": "Check-In Latitude",
                "fieldtype": "Float",
                "insert_after": "custom_exception_reason",
            },
            {
                "fieldname": "custom_checkin_longitude",
                "label": "Check-In Longitude",
                "fieldtype": "Float",
                "insert_after": "custom_checkin_latitude",
            },
            {
                "fieldname": "custom_whatsapp_message_id",
                "label": "WhatsApp Message ID",
                "fieldtype": "Data",
                "insert_after": "custom_checkin_longitude",
            },
        ]
    }
