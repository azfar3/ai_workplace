import frappe
from ai_workplace.services.hr_agent import handle_hr_agent_message

class MockConv:
    name = "TestConv"
    whatsapp_identity = "WA_TEST"
    erp_user = "test@erp.com"
    employee = "EMP-001"
    trace_id = "test-123"
    current_intent = "hr_ai_agent"

def run():
    conv = MockConv()
    context = {
        "employee": "EMP-001",
        "full_name": "John Doe",
        "person_type": "Employee",
        "preferred_language": "English",
        "allowed_services": ["leave_balance", "policies", "search_knowledge", "get_leave_balance"],
    }
    
    print("Testing HR Agent Pipeline...")
    resp = handle_hr_agent_message(conv, "How many leaves do I have?", context)
    print("Response Body:\n", resp.body_text)

