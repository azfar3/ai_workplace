import frappe
from frappe.utils import today

def test_leave_application_creation():
    frappe.connect()
    try:
        from ai_workplace.services.leave_apply import _create_leave_application
        
        # Pick an active employee
        emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
        print(f"Testing with Employee: {emp}")
        
        draft = {
            "employee": emp,
            "leave_type": "Casual Leave",
            "from_date": "2026-10-15",
            "to_date": "2026-10-15",
            "half_day": 0,
            "short_leave": 0,
            "description": "Automated Test Leave Application",
        }
        
        context = {
            "employee": emp,
            "user": "Administrator",
            "preferred_language": "English",
        }
        
        doc_name = _create_leave_application(draft, context)
        print(f"SUCCESS! Created Leave Application: {doc_name}")
        
        # Clean up test document
        frappe.db.rollback()
        print("Rolled back test Leave Application.")
    except Exception as e:
        frappe.db.rollback()
        print(f"FAILED with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_leave_application_creation()
