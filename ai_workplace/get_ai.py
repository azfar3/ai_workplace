import frappe

def get_errors():
    logs = frappe.get_all("Error Log", filters={"method": ["like", "AI Orchestrator Message Failed%"]}, fields=["name", "creation", "method", "error"], order_by="creation desc", limit=10)
    for log in logs:
        print(f"[{log.creation}] {log.method}")
        print(log.error)
        print("-" * 50)
