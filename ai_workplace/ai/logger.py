from typing import Optional
import frappe

def log_llm_usage(
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    employee: Optional[str] = None,
    channel: str = "WhatsApp",
    status: str = "Success",
    error_message: str = "",
    trace_id: str = "",
) -> None:
    """
    Logs LLM token usage and latency to the AI Workplace Usage Log DocType.
    """
    try:
        if not frappe.db.exists("DocType", "AI Workplace Usage Log"):
            return

        doc = frappe.new_doc("AI Workplace Usage Log")
        doc.provider = provider
        doc.model = model
        doc.channel = channel
        doc.employee = employee
        doc.status = status
        doc.success = 1 if status == "Success" else 0
        doc.tokens_in = tokens_in
        doc.tokens_out = tokens_out
        doc.tokens_total = tokens_in + tokens_out
        doc.latency_ms = latency_ms
        doc.error_message = error_message
        
        # In a real implementation, cost calculation would happen here based on the provider/model
        doc.input_cost = 0.0
        doc.output_cost = 0.0
        doc.total_cost = 0.0

        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.insert()
        frappe.db.commit()
    except Exception as e:
        frappe.logger("ai_workplace").error(f"Failed to log LLM usage: {e}")
