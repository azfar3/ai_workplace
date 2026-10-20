import frappe
from ai_workplace.conversation.orchestrator import process_message
from ai_workplace.whatsapp.identity import resolve_sender_identity

def execute():
    wa_id = "923330788803"
    print(f"Testing with wa_id: {wa_id}")
    
    try:
        identity = resolve_sender_identity(wa_id)
        
        # Test 1: svc_pay_slip_latest
        outbound1 = process_message(
            phone_number=wa_id,
            message_text="svc_pay_slip_latest",
            message_type="interactive",
            identity=identity,
            trace_id="test_trace_123"
        )
        print(f"Process message (svc_pay_slip_latest) returned: {outbound1}")

        # Test 2: Last Salary Slip
        outbound2 = process_message(
            phone_number=wa_id,
            message_text="Last Salary Slip",
            message_type="text",
            identity=identity,
            trace_id="test_trace_124"
        )
        print(f"Process message (Last Salary Slip) returned: {outbound2}")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
