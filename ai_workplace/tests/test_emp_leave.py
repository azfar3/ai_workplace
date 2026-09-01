import frappe

def test_emp_leave():
    from ai_workplace.ai.tools import get_leave_balance
    from hrms.hr.doctype.leave_application.leave_application import get_leave_details
    from frappe.utils import today

    emp = "EMP-MM-00796"
    print("Today:", today())
    print("Employee:", emp)
    
    try:
        details = get_leave_details(emp, date=today())
        print("Raw HRMS get_leave_details:", details)
    except Exception as exc:
        print("Error getting HRMS details:", exc)

    tool_res = get_leave_balance(emp)
    print("\nTools get_leave_balance:", tool_res)
