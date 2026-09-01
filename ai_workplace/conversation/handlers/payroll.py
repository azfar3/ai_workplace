from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class PayrollHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent.startswith("pay_") or intent.startswith("svc_pay_") or intent in ("former_payslip", "pay_slip")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        
        if clean_intent in ("pay_download_slip", "former_payslip", "pay_slip"):
            from ai_workplace.services.payroll import build_salary_slip_download_intro
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_salary_slip_download_intro(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_payslip"
            
        elif clean_intent in ("pay_tax_deduction", "tax_certificate"):
            from ai_workplace.services.tax_certificate import build_tax_certificate_download_outbound
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_tax_certificate_download_outbound(context)
            action = "view_tax_deduction"
            
        elif clean_intent in ("pay_bank_letter", "bank_letter"):
            from ai_workplace.services.employee_letters import generate_bank_letter_pdf, build_letter_download_outbound, build_letter_download_error, resolve_bank_name
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            bank_name = resolve_bank_name(context) or "Faysal Bank"
            try:
                pdf_bytes, filename = generate_bank_letter_pdf(context.get("employee", ""), bank_name)
                caption = f"📄 Bank Letter for {bank_name}"
                outbound = build_letter_download_outbound(context, pdf_bytes, filename, caption)
            except Exception:
                err = build_letter_download_error(context, "Bank Letter")
                outbound = wrap_with_menu_again(err, context)
            action = "download_bank_letter"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="payroll",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None

