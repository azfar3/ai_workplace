# Copyright (c) 2026, MicroMerger Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HRLiveChatSession(Document):
    """Live HR chat session between a WhatsApp employee and an ERPNext HR agent."""

    pass


def get_permission_query_conditions(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""

    from ai_workplace.services.hr_chat import get_hr_agent_role_access

    access_role = get_hr_agent_role_access(user)
    if access_role == "Assigned HR User (View & Reply Assigned Only)":
        return f"`tabHR Live Chat Session`.assigned_to = {frappe.db.escape(user)}"

    return ""


def has_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True

    from ai_workplace.services.hr_chat import get_hr_agent_role_access

    access_role = get_hr_agent_role_access(user)
    if access_role == "Assigned HR User (View & Reply Assigned Only)":
        if doc.assigned_to != user:
            return False

    return True
