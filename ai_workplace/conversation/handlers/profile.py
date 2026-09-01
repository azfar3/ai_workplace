from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class ProfileHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        clean = intent.replace("svc_", "")
        return (
            clean in ("prof_my_requests", "update_profile", "my_profile", "prof_view", "prof_update", "my_requests", "profile_gaps")
            or clean.startswith("prof_")
            or clean.startswith("gap_")
        )

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        
        if clean_intent in ("my_profile", "prof_view", "prof_summary"):
            from ai_workplace.services.hr_profile import build_my_profile_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_my_profile_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_profile_summary"
            
        elif clean_intent in ("update_profile", "prof_update", "profile_gaps"):
            from ai_workplace.services.profile_completion import build_profile_completion_hub
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_profile_completion_hub(context)
            action = "view_update_profile"
            
        elif clean_intent in ("prof_my_requests", "my_requests"):
            from ai_workplace.services.profile_completion import build_my_requests_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_my_requests_response(context)
            action = "view_profile_requests"

        elif clean_intent.startswith("gap_"):
            from ai_workplace.services.profile_completion import handle_profile_gap_action
            gap_key = clean_intent[4:]
            outbound = handle_profile_gap_action(conv, context, gap_key)
            action = f"profile_gap_{gap_key}"

        elif clean_intent.startswith("prof_"):
            from ai_workplace.services.profile_completion import start_profile_flow
            outbound = start_profile_flow(conv, context, clean_intent)
            action = f"start_profile_flow_{clean_intent}"

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
