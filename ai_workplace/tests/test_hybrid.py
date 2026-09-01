import frappe

def run_test():
    # 1. Enable AI Chat via DB set_value to bypass validation checks
    frappe.db.set_value("AI Workplace Settings", "AI Workplace Settings", "proactive_notifications_enabled", 0)
    frappe.db.set_value("AI Workplace Settings", "AI Workplace Settings", "ai_chat_enabled", 1)
    frappe.db.commit()

    # 2. Test handle_hr_agent_message with AI ON
    from ai_workplace.services.hr_agent import handle_hr_agent_message
    from ai_workplace.context.resolver import get_user_context

    ctx = get_user_context({
        "status": "matched",
        "user": "azfarmurtaaddasdaza34@gmail.com",
        "employee": "EMP-MM-00796",
        "full_name": "Azfar Murtaza"
    })
    conv = frappe.get_all("WhatsApp Conversation", limit=1)[0]
    conv_doc = frappe.get_doc("WhatsApp Conversation", conv.name)

    out = handle_hr_agent_message(conv_doc, "How many leaves do I have left?", ctx)
    print("\n=== AI CHAT ENABLED RESPONSE ===")
    print("Body:", out.body_text)
    print("Buttons:", [b["title"] for b in getattr(out, "buttons", [])])

    # 3. Test handle_hr_agent_message with AI OFF
    frappe.db.set_value("AI Workplace Settings", "AI Workplace Settings", "ai_chat_enabled", 0)
    frappe.db.commit()

    out_off = handle_hr_agent_message(conv_doc, "How many leaves do I have left?", ctx)
    print("\n=== AI CHAT DISABLED RESPONSE ===")
    print("Body:", out_off.body_text)

    # 4. Reset AI Settings to enabled
    frappe.db.set_value("AI Workplace Settings", "AI Workplace Settings", "ai_chat_enabled", 1)
    frappe.db.commit()

    # 5. Test Knowledge Gap Auto-logging
    from ai_workplace.ai_workplace.doctype.ai_knowledge_gap_log.ai_knowledge_gap_log import log_knowledge_gap
    gap_name = log_knowledge_gap("What is the child education allowance policy?", ctx, failure_reason="NO_KNOWLEDGE")
    print("\n=== KNOWLEDGE GAP LOGGED ===")
    print("Gap Name:", gap_name)

    # 6. Test 1-Click Publishing
    gap_doc = frappe.get_doc("AI Knowledge Gap Log", gap_name)
    entry_name = gap_doc.create_knowledge_entry(
        title="Child Education Allowance Policy",
        answer="MicroMerger provides up to PKR 15,000 annually per school-going child under the Welfare Policy."
    )
    print("Published Knowledge Entry Name:", entry_name)

    # Verify Knowledge Entry chunk indexing
    chunks = frappe.get_all("AI Workplace Knowledge Chunk", filters={"knowledge_source": "knowledge_entries"}, fields=["chunk_text"])
    print("Indexed Chunks:", [c.chunk_text for c in chunks])
