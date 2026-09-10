import frappe
from ai_workplace.api.whatsapp_webhook import process_async_whatsapp_message
import json
import uuid

def execute():
    # Find the user's wa_id from the db log
    logs = frappe.db.get_all("WhatsApp Message Log", filters={"direction": "Inbound"}, fields=["wa_id"], limit=1)
    if not logs:
        print("No wa_id found")
        return
    wa_id = logs[0].wa_id
    
    # Mock inbound log
    doc = frappe.new_doc("WhatsApp Message Log")
    doc.direction = "Inbound"
    doc.wa_id = wa_id
    doc.message_type = "interactive"
    doc.message = "svc_pay_slip_latest"
    doc.status = "Queued"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    
    message_id = f"wamid.{uuid.uuid4().hex}"
    
    print(f"Testing with wa_id: {wa_id}, inbound_log: {doc.name}")
    
    try:
        process_async_whatsapp_message(
            inbound_log_name=doc.name,
            message_id=message_id,
            wa_id=wa_id,
            raw_phone=wa_id,
            message_text="svc_pay_slip_latest",
            parsed_payload=json.dumps({
                "type": "interactive",
                "interactive_id": "svc_pay_slip_latest",
                "text": "svc_pay_slip_latest"
            }),
            sender_type="Employee"
        )
        print("Process async complete.")
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

