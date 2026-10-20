from ai_workplace.services.hr_agent import handle_hr_agent_message

def run():
    class MockConv:
        name = "Test"
        trace_id = "test-trace"
        whatsapp_identity = "test-phone"
        current_intent = "hr_ai_agent"

    context = {
        "employee": "HR-EMP-00001",
        "employee_name": "Test User",
        "language": "English",
        "person_type": "Employee",
        "allowed_intents": ["leave_balance", "policies", "leave_application", "profile_queries"]
    }

    res = handle_hr_agent_message(MockConv(), "What is my leave balance? and then how do I apply for leave?", context)
    print("FINAL RESPONSE:", res)
