import frappe

def debug_latest():
    print("--- Recent WhatsApp Message Logs ---")
    msgs = frappe.get_all("WhatsApp Message Log", fields=["name", "whatsapp_id", "direction", "message", "creation"], order_by="creation desc", limit=6)
    for m in msgs:
        print(m)

    print("\n--- Recent AI Action Logs ---")
    actions = frappe.get_all("AI Action Log", fields=["name", "whatsapp_identity", "employee", "intent", "action", "status", "result", "creation"], order_by="creation desc", limit=6)
    for a in actions:
        print(a)

    if msgs:
        wa_id = msgs[0].whatsapp_id
        print("\n--- User Context for WA ID:", wa_id, "---")
        conv = frappe.get_all("WhatsApp Conversation", filters={"whatsapp_identity": wa_id})
        print("Conversation:", conv)
        if conv:
            c_doc = frappe.get_doc("WhatsApp Conversation", conv[0].name)
            print("ERP User:", c_doc.erp_user, "Employee:", c_doc.employee)
            if c_doc.employee:
                from ai_workplace.ai.tools import get_leave_balance
                from ai_workplace.ai.evidence import sanitize_tool_evidence
                lb = get_leave_balance(c_doc.employee)
                print("Raw get_leave_balance:", lb)
                san = sanitize_tool_evidence("get_leave_balance", lb, {"employee": c_doc.employee})
                print("Sanitized Evidence:", san)
