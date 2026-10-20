import frappe
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.auth.gateway import IdentityResult

def run():
    identity = IdentityResult(
        status="matched",
        normalized_phone="+923001234567",
        user="john@example.com",
        employee=frappe.db.get_value("Employee", {"user_id": "john@example.com"}, "name"),
        full_name="John Doe",
    )
    
    process_message("Hi", identity, message_id="msg-1", trace_id="tr-1")
    resp2 = process_message("lang_en", identity, message_id="msg-2", trace_id="tr-1")
    
    rows = resp2.follow_up[0].interactive["action"]["sections"][0]["rows"]
    row_ids = [r["id"] for r in rows]
    print("Available services:", row_ids)

