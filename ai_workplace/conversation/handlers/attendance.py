from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class AttendanceHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        return intent.startswith("att_") or intent.startswith("svc_att_")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        
        if clean_intent in ("att_checkin", "att_checkout", "att_request_exception", "att_retry_location"):
            from ai_workplace.services.attendance_location import handle_attendance_menu_action
            return handle_attendance_menu_action(conv, context, clean_intent)
            
        elif clean_intent == "att_today":
            from ai_workplace.services.attendance_leave import build_today_attendance_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_today_attendance_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_today_attendance"
            
        elif clean_intent in ("att_monthly", "att_summary"):
            from ai_workplace.services.attendance_leave import build_monthly_attendance_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_monthly_attendance_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_monthly_attendance"
            
        elif clean_intent == "att_monthly_last7":
            from ai_workplace.services.attendance_leave import build_last7_attendance_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_last7_attendance_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_last_7_days_attendance"
            
        elif clean_intent == "att_monthly_download":
            from ai_workplace.services.attendance_leave import build_monthly_download_caption
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_monthly_download_caption(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "download_monthly_attendance"
            
        elif clean_intent == "att_missing":
            from ai_workplace.services.attendance_leave import build_missing_attendance_response
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            resp_text = build_missing_attendance_response(context)
            outbound = wrap_with_menu_again(resp_text, context)
            action = "view_missing_attendance"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="attendance",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None

