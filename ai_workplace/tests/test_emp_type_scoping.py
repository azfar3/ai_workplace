import frappe

def test_emp_type_scoping():
    from ai_workplace.services.hr_agent import handle_hr_agent_message
    from ai_workplace.context.resolver import get_user_context

    # 1. Create a Knowledge Entry specific to Contract employees
    entry_title = "Contract Employee Notice Period Policy"
    if not frappe.db.exists("AI Knowledge Entry", {"title": entry_title}):
        doc = frappe.new_doc("AI Knowledge Entry")
        doc.title = entry_title
        doc.category = "Policy"
        doc.applicable_employment_type = "Contract"
        doc.question = "What is the notice period for contract employees?"
        doc.answer = "Contract employees must give 15 days written notice before resignation."
        doc.status = "PUBLISHED"
        doc.insert(ignore_permissions=True)
    else:
        doc = frappe.get_doc("AI Knowledge Entry", {"title": entry_title})
        doc.applicable_employment_type = "Contract"
        doc.answer = "Contract employees must give 15 days written notice before resignation."
        doc.status = "PUBLISHED"
        doc.save(ignore_permissions=True)

    frappe.db.commit()

    # 2. Test query with a Contract employee
    ctx_contract = get_user_context({
        "status": "matched",
        "user": "azfarmurtaaddasdaza34@gmail.com",
        "employee": "EMP-MM-00796",
        "full_name": "Azfar Murtaza",
        "employment_type": "Contract"
    })
    conv = frappe.get_doc("WhatsApp Conversation", "WACN-2026-08-31-05172")

    print("\n=== CONTRACT EMPLOYEE QUERY ===")
    out_contract = handle_hr_agent_message(conv, "What is the notice period for contract employees?", ctx_contract)
    print("Body:", out_contract.body_text)

    # 3. Test query with a Full-time employee
    ctx_fulltime = get_user_context({
        "status": "matched",
        "user": "azfarmurtaaddasdaza34@gmail.com",
        "employee": "EMP-MM-00796",
        "full_name": "Azfar Murtaza",
        "employment_type": "Full-time"
    })
    print("\n=== FULL-TIME EMPLOYEE QUERY ===")
    out_fulltime = handle_hr_agent_message(conv, "What is the notice period for contract employees?", ctx_fulltime)
    print("Body:", out_fulltime.body_text)
