from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class ProfileHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent in ("prof_my_requests", "update_profile", "my_profile")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent == "my_profile":
            from ai_workplace.services.profile import build_profile_summary_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_profile_summary_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_profile_summary"
            
        elif intent == "update_profile":
            from ai_workplace.services.profile import build_update_profile_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_update_profile_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_update_profile"
            
        elif intent == "prof_my_requests":
            from ai_workplace.services.profile import build_profile_requests_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_profile_requests_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_profile_requests"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="profile",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
