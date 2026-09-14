"""
ai_workplace/www/xpertchat.py
─────────────────────────────
Server context controller for XpertChat Web Page (/xpertchat).
"""

import frappe

no_cache = 1


def get_context(context):
    user = frappe.session.user
    is_guest = user == "Guest" or not user

    context.title = "XpertChat - AI Support & Live HR"
    context.is_guest = is_guest
    context.user_email = user if not is_guest else ""
    context.user_fullname = ""

    if not is_guest:
        context.user_fullname = frappe.db.get_value("User", user, "full_name") or user

    return context
