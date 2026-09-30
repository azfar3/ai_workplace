import frappe
frappe.init(site="erp.v15")
frappe.connect()

from ai_workplace.ai.hybrid_handler import handle_hybrid
from unittest.mock import MagicMock

context = {"policy_scope": "HO", "preferred_language": "English", "employee": "EMP-001"}
class MockConv:
    name = "TestConv"
    whatsapp_identity = "TestWA"
    erp_user = "TestUser"
    employee = "EMP-001"
    wa_id = "12345"

conv = MockConv()

outbound = handle_hybrid(
    intent_key="search_knowledge",
    tool_name="search_knowledge",
    context=context,
    user_query="what is the notice period",
    conv=conv
)

print("\n--- FINAL OUTBOUND MESSAGE ---")
print(outbound.body_text)
