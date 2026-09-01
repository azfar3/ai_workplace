import frappe

def test_full_llm_flow():
    from ai_workplace.services.hr_agent import handle_hr_agent_message
    from ai_workplace.context.resolver import get_user_context

    emp = "EMP-MM-00796"
    ctx = get_user_context({
        "status": "matched",
        "user": "azfarmurtaaddasdaza34@gmail.com",
        "employee": emp,
        "full_name": "Azfar Murtaza"
    })
    
    conv = frappe.get_doc("WhatsApp Conversation", "WACN-2026-08-31-05172")
    out = handle_hr_agent_message(conv, "How many leaves do I have left?", ctx)
    print("Outbound text:")
    print(out.body_text)
