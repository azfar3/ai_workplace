import frappe
from ai_workplace.services.hr_chat import (
    open_session,
    get_inbox_sessions,
    take_session,
    assign_session,
)
from ai_workplace.api.hr_chat import get_session_detail

def run_tests():
    frappe.set_user("Administrator")
    frappe.db.sql("DELETE FROM `tabHR Live Chat Session` WHERE wa_id LIKE 'test_vis_%'")
    frappe.db.commit()

    try:
        # Test 1: Queued chat is unassigned
        s1 = open_session(
            whatsapp_identity="test_vis_identity_queued",
            whatsapp_conversation="test_vis_conv_q",
            wa_id="test_vis_queued",
            display_name="User Queued",
            contact_hr_selected=True,
            ready_for_hr=True,
        )
        assert s1.status == "Queued", f"Expected Queued status, got {s1.status}"
        assert not s1.assigned_to, f"Expected assigned_to to be None, got {s1.assigned_to}"
        print("✓ Test 1 passed: Queued chat is unassigned.")

        # Test 2: Visibility filtering
        agent_a = "Administrator"
        agent_b = "test_agent_b@example.com"

        if not frappe.db.exists("User", agent_b):
            user_b = frappe.new_doc("User")
            user_b.email = agent_b
            user_b.first_name = "Agent B"
            user_b.insert(ignore_permissions=True)

        user_b_doc = frappe.get_doc("User", agent_b)
        # Ensure agent_b is an HR Agent but NOT a System Manager
        if hasattr(user_b_doc, "remove_roles"):
            user_b_doc.remove_roles("System Manager")
        user_b_doc.roles = [r for r in user_b_doc.roles if r.role != "System Manager"]
        user_b_doc.save(ignore_permissions=True)
        user_b_doc.add_roles("HR Workplace Agent")

        # Session 2: Assigned to Agent A
        s2 = open_session(
            whatsapp_identity="test_vis_identity_a",
            whatsapp_conversation="test_vis_conv_a",
            wa_id="test_vis_a",
            display_name="User A",
            contact_hr_selected=True,
            ready_for_hr=True,
        )
        s2_updated = take_session(s2.name, user=agent_a)
        assert s2_updated.assigned_to == agent_a, f"Expected assigned_to {agent_a}, got {s2_updated.assigned_to}"

        # Session 3: Assigned to Agent B
        s3 = open_session(
            whatsapp_identity="test_vis_identity_b",
            whatsapp_conversation="test_vis_conv_b",
            wa_id="test_vis_b",
            display_name="User B",
            contact_hr_selected=True,
            ready_for_hr=True,
        )
        s3_updated = assign_session(s3.name, assign_to=agent_b, user=agent_a)
        assert s3_updated.assigned_to == agent_b, f"Expected assigned_to {agent_b}, got {s3_updated.assigned_to}"

        # Test 2: Check Agent A (System Manager / Administrator) view:
        # System Manager MUST see all chats: assigned to self, unassigned, or assigned to other agents
        frappe.set_user(agent_a)
        agent_a_sessions = get_inbox_sessions(status_filter="all")
        agent_a_names = [s["name"] for s in agent_a_sessions]

        assert s1.name in agent_a_names, "Unassigned queued chat should be visible to System Manager (Agent A)"
        assert s2.name in agent_a_names, "Chat assigned to Agent A should be visible to System Manager (Agent A)"
        assert s3.name in agent_a_names, "Chat assigned to Agent B MUST be visible to System Manager (Agent A)"
        print("✓ Test 2 passed: System Manager sees all chats (own, unassigned, and assigned to others).")

        # Test 3: Check Agent B (Non-System Manager HR Agent) view:
        # Non-System Manager must ONLY see chats assigned to self or unassigned; MUST NOT see Agent A's chat
        frappe.set_user(agent_b)
        agent_b_sessions = get_inbox_sessions(status_filter="all")
        agent_b_names = [s["name"] for s in agent_b_sessions]

        assert s1.name in agent_b_names, "Unassigned queued chat should be visible to Agent B"
        assert s3.name in agent_b_names, "Chat assigned to Agent B should be visible to Agent B"
        assert s2.name not in agent_b_names, "Chat assigned to Agent A MUST NOT be visible to regular Agent B"
        print("✓ Test 3 passed: Regular HR Agent sees only unassigned and own chats.")

        # Test 4: Detail API permission check
        # System Manager can access detail of any session
        frappe.set_user(agent_a)
        detail_s3 = get_session_detail(s3.name)
        assert detail_s3 and detail_s3["session"]["name"] == s3.name

        # Regular agent cannot access detail of another agent's session
        frappe.set_user(agent_b)
        permission_error_raised = False
        try:
            get_session_detail(s2.name)
        except frappe.PermissionError:
            permission_error_raised = True
        assert permission_error_raised, "Regular agent accessing another agent's session must raise PermissionError"
        print("✓ Test 4 passed: Detail API correctly enforces System Manager vs regular agent permissions.")

        print("\nALL INBOX VISIBILITY & UNASSIGNED QUEUE TESTS PASSED SUCCESSFULLY!")

    finally:
        frappe.set_user("Administrator")
        frappe.db.sql("DELETE FROM `tabHR Live Chat Session` WHERE wa_id LIKE 'test_vis_%'")
        frappe.db.commit()
