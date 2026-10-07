import frappe
def run():
    try:
        from ai_workplace.services.attendance_leave import get_employee_leave_policy_details
        emp = frappe.get_all("Employee", fields=["name"], limit=1)
        if emp:
            e = emp[0].name
            print("Exists", e, ":", frappe.db.exists("Employee", e))
            
            # ensure leave policy assignment
            lpa = frappe.get_all("Leave Policy Assignment", limit=1)
            if lpa:
                frappe.db.set_value("Leave Policy Assignment", lpa[0].name, "employee", e)
                frappe.db.commit()
            
            res = get_employee_leave_policy_details(e)
            print("DIRECT RES", e, ":", res)
    except Exception as e:
        print("Error:", e)
