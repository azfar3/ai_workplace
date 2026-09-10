import frappe
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.whatsapp.identity import resolve_sender_identity

def execute():
    wa_id = "923330788803"
    print(f"Testing with wa_id: {wa_id}")
    
    identity = resolve_sender_identity(wa_id)
    
    outbound1 = process_message(
        phone_number=wa_id,
        message_text="svc_pay_slip_latest",
        message_type="interactive",
        identity=identity,
        trace_id="test_trace_123"
    )
    print(f"Process message (svc_pay_slip_latest) returned: {outbound1}")

    if outbound1 and not outbound1.has_document():
        print(f"Text: {outbound1.body_text}")
        print(f"Interactive: {outbound1.interactive}")
        print(f"Follow up: {outbound1.follow_up}")

execute()
