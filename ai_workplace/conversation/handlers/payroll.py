from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class PayrollHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent.startswith("pay_") or intent == "former_payslip"

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent in ("pay_download_slip", "former_payslip"):
            from ai_workplace.services.payroll import build_payslip_download_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_payslip_download_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_payslip"
            
        elif intent == "pay_tax_deduction":
            from ai_workplace.services.payroll import build_tax_deduction_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_tax_deduction_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_tax_deduction"
            
        elif intent == "pay_bank_letter":
            from ai_workplace.services.payroll import build_bank_letter_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_bank_letter_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_bank_letter"
            
        elif intent == "pay_bank_faysal":
            from ai_workplace.services.payroll import build_bank_format_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_bank_format_response("Faysal Bank", context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_faysal_bank_format"
            
        elif intent == "pay_bank_scb":
            from ai_workplace.services.payroll import build_bank_format_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_bank_format_response("Standard Chartered", context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_scb_format"

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
