import base64
import json
import traceback
from typing import Any, Dict

import frappe
from frappe import _
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_private_key

@frappe.whitelist(allow_guest=True)
def handle_data_exchange():
    """Endpoint for WhatsApp Flows Data Exchange."""
    try:
        # Load the encrypted request body
        payload = frappe.request.get_data(as_text=True)
        if not payload:
            return {"error": "Empty payload"}
            
        data = json.loads(payload)
        
        encrypted_aes_key = data.get("encrypted_aes_key")
        encrypted_flow_data = data.get("encrypted_flow_data")
        initial_vector = data.get("initial_vector")
        
        if not all([encrypted_aes_key, encrypted_flow_data, initial_vector]):
            frappe.logger("ai_workplace").warning("Invalid WhatsApp Flow Payload")
            return {"error": "Missing encrypted parameters"}

        # Fetch Private Key from Settings
        settings = frappe.get_doc("AI Workplace Settings", "AI Workplace Settings")
        private_key_pem = settings.get_password("whatsapp_flow_private_key")
        
        if not private_key_pem:
            frappe.logger("ai_workplace").error("WhatsApp Flow Private Key not configured.")
            return {"error": "Configuration missing"}

        # 1. Decrypt AES Key using RSA Private Key
        private_key = load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
        
        aes_key = private_key.decrypt(
            base64.b64decode(encrypted_aes_key),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # 2. Decrypt Flow Data using AES-GCM
        iv = base64.b64decode(initial_vector)
        aesgcm = AESGCM(aes_key)
        decrypted_data_bytes = aesgcm.decrypt(iv, base64.b64decode(encrypted_flow_data), None)
        flow_data = json.loads(decrypted_data_bytes.decode('utf-8'))
        
        # 3. Process the Flow Data
        response_dict = _process_flow_request(flow_data)
        
        # 4. Encrypt Response
        # The flipped IV is created by flipping the bytes of the initial_vector
        flipped_iv = bytes(~b & 0xFF for b in iv)
        
        response_bytes = json.dumps(response_dict).encode('utf-8')
        encrypted_response = aesgcm.encrypt(flipped_iv, response_bytes, None)
        
        # Return exact format expected by Meta
        frappe.response["type"] = "json"
        return {
            "encrypted_flow_data": base64.b64encode(encrypted_response).decode('utf-8')
        }
        
    except Exception as e:
        frappe.logger("ai_workplace").error(f"WhatsApp Flow Exchange Error: {str(e)}\n{traceback.format_exc()}")
        return {"error": "Decryption or processing failed"}


def _process_flow_request(flow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process the decrypted payload and return response."""
    action = flow_data.get("action")
    screen = flow_data.get("screen")
    data = flow_data.get("data", {})
    
    # 1. Action: ping (Meta ping check)
    if action == "ping":
        return {
            "version": flow_data.get("version", "3.0"),
            "data": {
                "status": "active"
            }
        }
        
    # 2. Action: INIT (Populate dynamic data before showing the form)
    if action == "INIT":
        if screen == "Leave_Application":
            # Example: Fetch leave balances for this user to populate a dropdown
            # We would need user identity from flow_data, but for now we send static dropdown options
            return {
                "version": flow_data.get("version", "3.0"),
                "screen": "Leave_Application",
                "data": {
                    "leave_type_options": [
                        {"id": "Casual", "title": "Casual Leave"},
                        {"id": "Sick", "title": "Sick Leave"},
                        {"id": "Annual", "title": "Annual Leave"}
                    ]
                }
            }
            
    # 3. Action: data_exchange (Form submission)
    if action == "data_exchange":
        if screen == "Leave_Application":
            # Extract submitted fields
            leave_type = data.get("leave_type")
            from_date = data.get("from_date")
            to_date = data.get("to_date")
            reason = data.get("reason")
            
            # --- Insert Logic to Create Leave Application in Frappe ---
            # employee_id would be resolved here (we can pass it implicitly from the bot when triggering)
            # For now, we transition to the Success screen
            
            return {
                "version": flow_data.get("version", "3.0"),
                "screen": "SUCCESS",
                "data": {
                    "extension_message_response": {
                        "params": {
                            "flow_token": flow_data.get("flow_token"),
                            "status": "success",
                            "message": f"Leave Application for {leave_type} submitted."
                        }
                    }
                }
            }
            
    # Fallback response
    return {
        "version": flow_data.get("version", "3.0"),
        "screen": "SUCCESS",
        "data": {
            "extension_message_response": {
                "params": {
                    "flow_token": flow_data.get("flow_token")
                }
            }
        }
    }
