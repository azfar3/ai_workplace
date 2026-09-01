import frappe

def test_hr_agent_access_roles():
    from ai_workplace.services.hr_chat import get_hr_agent_role_access, evaluate_reply_permission

    # 1. Update AI Workplace Settings table with Main and Assigned HR users
    settings = frappe.get_single("AI Workplace Settings")
    settings.set("hr_chat_agents", [
        {
            "user": "Administrator",
            "user_full_name": "Administrator",
            "agent_role": "Main HR User (View & Reply All)",
            "is_active": 1
        },
        {
            "user": "Guest",
            "user_full_name": "Guest User",
            "agent_role": "Assigned HR User (View & Reply Assigned Only)",
            "is_active": 1
        }
    ])
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    print("=== Testing Role Access Resolutions ===")
    print("Administrator Access:", get_hr_agent_role_access("Administrator"))
    print("Guest Access:", get_hr_agent_role_access("Guest"))

    # 2. Test session assigned to Administrator
    if not frappe.db.exists("HR Live Chat Session", "TEST-HR-SESSION-001"):
        session = frappe.new_doc("HR Live Chat Session")
        session.name = "TEST-HR-SESSION-001"
        session.whatsapp_identity = "WAI-TEST-9999"
        session.status = "Active"
        session.assigned_to = "Administrator"
        session.opened_at = frappe.utils.now_datetime()
        session.last_user_message_at = frappe.utils.now_datetime()
        session.session_window_expires_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=24)
        session.insert(ignore_permissions=True)
    else:
        session = frappe.get_doc("HR Live Chat Session", "TEST-HR-SESSION-001")
        session.assigned_to = "Administrator"
        session.status = "Active"
        session.save(ignore_permissions=True)

    frappe.db.commit()

    # Admin reply test
    can_admin_reply, reason_admin = evaluate_reply_permission(session, user="Administrator")
    print("\nAdmin (Main HR) Can Reply to Admin Session:", can_admin_reply, f"({reason_admin})")

    # Guest (Assigned HR User) reply test on Admin session
    can_guest_reply, reason_guest = evaluate_reply_permission(session, user="Guest")
    print("Guest (Assigned HR) Can Reply to Admin Session:", can_guest_reply, f"({reason_guest})")
