from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again
from ai_workplace.services.careers_guide import build_careers_guide_response, CAREERS_MENU_KEYS

class CareersHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        clean = intent.replace("svc_", "").lower()
        return clean in CAREERS_MENU_KEYS

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        clean_intent = intent.replace("svc_", "").lower()
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
        
        resp_text = build_careers_guide_response(clean_intent, context)
        outbound = wrap_with_menu_again(resp_text, context)
        
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent=intent,
            service="careers",
            action=f"view_{clean_intent}",
            result=outbound.log_text(),
            status="Success",
        )
        return outbound
