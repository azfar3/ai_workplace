import frappe
from frappe.model.document import Document
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AIConversationPreference(Document):
    def validate(self):
        if self.user == 'Guest':
            frappe.throw('Guest accounts cannot store notification preferences.')
        if not 0 <= int(self.quiet_start or 0) <= 23 or not 0 <= int(self.quiet_end or 0) <= 23:
            frappe.throw('Quiet hours must be between 0 and 23.')
        try:
            ZoneInfo(self.timezone or frappe.utils.get_system_timezone())
        except ZoneInfoNotFoundError:
            frappe.throw('Choose a valid IANA timezone.')
