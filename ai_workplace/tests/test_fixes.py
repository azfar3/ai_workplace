import frappe

def test_fixes():
    from ai_workplace.services.hr_agent import handle_hr_agent_message
    from ai_workplace.context.resolver import get_user_context

    ctx = get_user_context({
        "status": "matched",
        "user": "azfarmurtaaddasdaza34@gmail.com",
        "employee": "EMP-MM-00796",
        "full_name": "Azfar Murtaza"
    })
    conv = frappe.get_doc("WhatsApp Conversation", "WACN-2026-08-31-05172")

    print("\n--- Test 1: Leaves Query ---")
    out1 = handle_hr_agent_message(conv, "How many leaves do I have left?", ctx)
    print("Body:", out1.body_text)

    print("\n--- Test 2: Employment Type Query ---")
    out2 = handle_hr_agent_message(conv, "what is my employment type?", ctx)
    print("Body:", out2.body_text)

    print("\n--- Test 3: Interactive Button Click ---")
    out3 = handle_hr_agent_message(conv, "fb_helpful", ctx)
    print("Body:", out3.body_text)
