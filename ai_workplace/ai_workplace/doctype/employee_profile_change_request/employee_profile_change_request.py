import frappe
from frappe.model.document import Document


class EmployeeProfileChangeRequest(Document):
    def before_save(self):
        if self.is_new() and not self.submitted_on:
            self.submitted_on = frappe.utils.now_datetime()
        if self.workflow_state and not self.has_value_changed("status"):
            self.status = self.workflow_state

    def on_update(self):
        before = self.get_doc_before_save()
        previous_status = before.status if before else ""

        if self.status == "Approved" and not self.applied_on:
            from ai_workplace.services.profile_change_applier import apply_approved_profile_request

            apply_approved_profile_request(self.name)
            before = self.get_doc_before_save()
            previous_status = before.status if before else previous_status

        from ai_workplace.services.profile_notifications import notify_employee_profile_request_status

        notify_employee_profile_request_status(self, previous_status=previous_status)

    @frappe.whitelist()
    def approve_request(self):
        frappe.only_for(("HR Manager", "System Manager"))
        self.status = "Approved"
        self.workflow_state = "Approved"
        self.hr_reviewer = frappe.session.user
        self.reviewed_on = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)

    @frappe.whitelist()
    def reject_request(self, reason: str = ""):
        frappe.only_for(("HR Manager", "System Manager"))
        self.status = "Rejected"
        self.workflow_state = "Rejected"
        self.rejection_reason = reason
        self.hr_reviewer = frappe.session.user
        self.reviewed_on = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)

    @frappe.whitelist()
    def request_more_info(self, remarks: str = ""):
        frappe.only_for(("HR Manager", "System Manager"))
        self.status = "Needs More Info"
        self.workflow_state = "Needs More Info"
        self.hr_remarks = remarks
        self.hr_reviewer = frappe.session.user
        self.reviewed_on = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)
