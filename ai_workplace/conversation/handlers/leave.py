from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class LeaveHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent.startswith("leave_") or intent == "svc_leave"

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent == "leave_balance":
            from ai_workplace.services.leave import build_leave_balance_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_leave_balance_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_leave_balance"
            
        elif intent == "leave_apply":
            from ai_workplace.services.leave_apply import start_leave_application
            outbound = start_leave_application(conv, context)
            action = "start_leave_application"
            
        elif intent == "leave_requests":
            from ai_workplace.services.leave import build_leave_requests_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_leave_requests_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_leave_requests"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="leave",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
