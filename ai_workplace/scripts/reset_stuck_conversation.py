"""Reset stuck WhatsApp conversation for a wa_id."""
import frappe


def run(wa_id: str = "923111123678"):
    from ai_workplace.conversation.state import ConversationState

    conv_name = frappe.db.get_value(
        "WhatsApp Conversation",
        {"wa_id": wa_id, "conversation_status": "Active"},
        "name",
    )
    if not conv_name:
        print(f"No active conversation for wa_id={wa_id}")
        return
    frappe.db.set_value(
        "WhatsApp Conversation",
        conv_name,
        {
            "current_state": ConversationState.AWAITING_SELECTION,
            "current_intent": None,
            "active_service": None,
            "active_hr_chat_session": None,
        },
    )
    frappe.db.set_value(
        "WhatsApp Message Log",
        {"message": "svc_contact_hr", "status": "Processing"},
        "status",
        "Received",
    )
    frappe.db.commit()
    print(f"Reset conversation {conv_name} for wa_id={wa_id}")
