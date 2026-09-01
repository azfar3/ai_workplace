from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class GeneralHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        clean = intent.replace("svc_", "")
        return clean in (
            "help", "hr_pin_help", "my_day", "supervisor_reporting", "staff_supervisor",
            "guest_number_changed", "contact_hr", "guest_contact", "staff_contact_hr",
            "concerns", "guest_concern", "former_concern"
        )

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        
        if clean_intent == "help":
            from ai_workplace.services.help import build_help_response
            from ai_workplace.conversation.menu import get_available_services_for_context
            from ai_workplace.conversation.manager import build_language_selection_message
            update_conversation(conv, state=ConversationState.AWAITING_LANGUAGE)
            help_intro = build_help_response(context, get_available_services_for_context(context))
            lang_out = build_language_selection_message(context)
            lang_out.body_text = f"{help_intro}\n\n{lang_out.body_text}"
            outbound = lang_out
            action = "display_language_menu"
            
        elif clean_intent in ("contact_hr", "guest_contact", "staff_contact_hr"):
            from ai_workplace.services.hr_chat import handle_contact_hr_request
            outbound = handle_contact_hr_request(conv, context, trace_id=trace_id, identity=context.get("identity"))
            action = "open_hr_live_chat"
            
        elif clean_intent in ("concerns", "guest_concern", "former_concern"):
            from ai_workplace.services.concern_report import start_concern_report
            outbound = start_concern_report(conv, context)
            action = "start_concern_report"
            
        elif clean_intent == "hr_pin_help":
            from ai_workplace.services.security import build_pin_help_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_pin_help_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_pin_help"
            
        elif clean_intent == "my_day":
            from ai_workplace.services.my_day import build_my_day_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_my_day_response(context)
            action = "view_my_day"
            
        elif clean_intent in ("supervisor_reporting", "staff_supervisor"):
            from ai_workplace.services.hr_profile import build_supervisor_reporting_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_supervisor_reporting_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_supervisor_reporting"
            
        elif clean_intent == "guest_number_changed":
            from ai_workplace.services.guest import build_number_changed_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_number_changed_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_number_changed_help"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="general",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
