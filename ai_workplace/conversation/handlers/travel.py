from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class TravelHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent.startswith("trv_")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent == "trv_apply":
            from ai_workplace.services.travel import start_travel_authorization
            outbound = start_travel_authorization(conv, context)
            action = "start_travel_authorization"
            
        elif intent == "trv_problem":
            from ai_workplace.services.travel import start_travel_problem_report
            outbound = start_travel_problem_report(conv, context)
            action = "start_travel_problem_report"
            
        elif intent == "trv_sop":
            from ai_workplace.services.travel import build_travel_sop_outbound
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_travel_sop_outbound(context)
            action = "download_travel_sop"
            
        elif intent == "trv_approved":
            from ai_workplace.services.travel import build_approved_travel_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_approved_travel_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_approved_travel"
            
        elif intent == "trv_upcoming":
            from ai_workplace.services.travel import build_upcoming_travel_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_upcoming_travel_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_upcoming_travel"
            
        elif intent == "trv_claim_status":
            from ai_workplace.services.travel import build_claim_status_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_claim_status_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_travel_claim_status"
            
        elif intent == "trv_vehicle_info":
            from ai_workplace.services.travel import build_vehicle_info_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_vehicle_info_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_vehicle_info"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="travel",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
