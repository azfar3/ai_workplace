import frappe
from frappe.utils import flt, getdate, today
from ai_workplace.services.attendance_leave import get_fiscal_year_leave_period

def get_info():
    # Find employee with 8 Sick Leaves allocated
    allocs = frappe.db.sql("""
        SELECT employee 
        FROM `tabLeave Allocation` 
        WHERE docstatus = 1 AND leave_type = 'Sick Leaves' AND total_leaves_allocated = 8
        LIMIT 1
    """, as_dict=1)
    
    if not allocs:
        print("Employee not found!")
        return
        
    employee_id = allocs[0].employee
    print(f"Employee: {employee_id}")
    
    if not allocs:
        print("Employee not found!")
        return
        
    employee_id = allocs[0].employee
    print(f"Employee: {employee_id}")

    curr_today = today()
    fy_from, fy_to = get_fiscal_year_leave_period()
    print(f"FY: {fy_from} to {fy_to}")

    allocations = frappe.db.get_all(
        "Leave Allocation",
        filters={"employee": employee_id, "to_date": [">=", curr_today], "docstatus": 1},
        fields=["name", "leave_type", "total_leaves_allocated", "from_date", "to_date"],
        order_by="leave_type asc",
    )
    for alloc in allocations:
        leave_type = alloc.get("leave_type")
        from_d = alloc.get("from_date") or fy_from
        to_d = alloc.get("to_date") or fy_to

        app_filters = {
            "employee": employee_id,
            "leave_type": leave_type,
            "docstatus": ["!=", 2],
            "status": ["!=", "Rejected"],
        }
        if from_d and to_d:
            app_filters["from_date"] = [">=", from_d]
            app_filters["to_date"] = ["<=", to_d]
        elif from_d:
            app_filters["from_date"] = [">=", from_d]
        elif to_d:
            app_filters["to_date"] = ["<=", to_d]

        leave_apps = frappe.db.get_all(
            "Leave Application",
            filters=app_filters,
            fields=["name", "total_leave_days", "status", "from_date", "to_date", "docstatus"]
        )
        print(f"\n{leave_type} - Allocated: {alloc.total_leaves_allocated} ({alloc.from_date} to {alloc.to_date})")
        print(f"Filters used: {app_filters}")
        print("Leave Apps found:")
        for r in leave_apps:
            print(f"  {r.name}: {r.total_leave_days} days (Status: {r.status}, {r.from_date} to {r.to_date})")

        # Let's also query without from_date and to_date filters to see what's missed
        all_apps = frappe.db.get_all(
            "Leave Application",
            filters={"employee": employee_id, "leave_type": leave_type, "docstatus": ["!=", 2], "status": ["!=", "Rejected"]},
            fields=["name", "total_leave_days", "status", "from_date", "to_date", "docstatus"]
        )
        print("ALL Leave Apps for this type:")
        for r in all_apps:
            print(f"  {r.name}: {r.total_leave_days} days (Status: {r.status}, {r.from_date} to {r.to_date})")
