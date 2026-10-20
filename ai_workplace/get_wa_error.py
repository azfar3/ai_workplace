import frappe
def get_log():
    logs = frappe.get_all("Error Log", filters={"method": "WhatsApp Meta API Full Traceback"}, fields=["name", "error"], order_by="creation desc", limit=1)
    if logs:
        print("======== LOG START ========")
        print(logs[0].error)
        print("======== LOG END ========")
    else:
        print("No logs found.")
