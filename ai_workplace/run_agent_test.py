import frappe
from ai_workplace.context.schema import AIRequestContext
from ai_workplace.ai.agent import IntentAgent

def run():
    context = AIRequestContext(
        employee_name="John Doe",
        language="English",
        person_type="Employee",
        staff_category="permanent",
        allowed_intents=["leave_balance", "policies"]
    )
    
    agent = IntentAgent()
    print("Agent initialized.")
    try:
        resp = agent.execute("How many leaves do I have left?", context)
        print("Response:", resp.json())
    except Exception as e:
        print("Error:", e)

