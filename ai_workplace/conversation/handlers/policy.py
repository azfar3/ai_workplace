from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class PolicyHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent in ("pol_view_policies", "pol_ai_assistant", "doc_contract")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent == "pol_view_policies":
            from ai_workplace.services.policy import build_published_policies_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_published_policies_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_published_policies"
            
        elif intent == "pol_ai_assistant":
            # This is the AI Chat intent. The orchestrator transitions state.
            from ai_workplace.services.hr_agent import build_agent_welcome_message
            update_conversation(conv, state=ConversationState.PROCESSING, current_intent="hr_ai_agent", active_service=None)
            outbound = build_agent_welcome_message(context)
            action = "start_hr_ai_agent"
            
        elif intent == "doc_contract":
            from ai_workplace.services.policy import build_contract_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_contract_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_contract"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="policy",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
