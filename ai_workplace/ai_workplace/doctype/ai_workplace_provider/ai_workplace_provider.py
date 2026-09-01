import frappe
from frappe.model.document import Document

from ai_workplace.ai.router import complete


class AIWorkplaceProvider(Document):
    @frappe.whitelist()
    def test_connection(self):
        result = complete(
            "Reply with exactly: OK",
            system="You are a connection test assistant.",
            channel="Desk",
        )
        return {
            "success": bool(result.get("success")),
            "message": result.get("text", ""),
            "provider": result.get("provider", self.name),
            "model": result.get("model", ""),
            "error": result.get("error", ""),
        }
