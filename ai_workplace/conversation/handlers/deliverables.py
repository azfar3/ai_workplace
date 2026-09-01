from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class DeliverablesHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent in ("dlv_add", "dlv_submit", "dlv_status")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        
        if intent == "dlv_add":
            from ai_workplace.services.deliverables import start_deliverable_add
            outbound = start_deliverable_add(conv, context)
            action = "start_deliverable_add"
            
        elif intent == "dlv_submit":
            from ai_workplace.services.deliverables import start_deliverable_submit
            outbound = start_deliverable_submit(conv, context)
            action = "start_deliverable_submit"
            
        elif intent == "dlv_status":
            from ai_workplace.services.deliverables import build_deliverable_status_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_deliverable_status_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_deliverable_status"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="deliverables",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
