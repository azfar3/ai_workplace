from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again

class PolicyHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        clean = intent.replace("svc_", "")
        return clean in ("pol_view_policies", "pol_ai_assistant", "doc_contract", "pol_policy_hub", "policies_help") or clean.startswith("pol_")

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        
        if clean_intent in ("pol_view_policies", "pol_policy_hub", "pol_ai_assistant", "policies_help", "staff_hr_guidance"):
            lang = context.get("preferred_language", "English")
            if lang == "Urdu":
                msg = (
                    "🤖 *ای آئی پالیسی اسسٹنٹ*\n\n"
                    "کمپنی کی کسی بھی پالیسی یا قاعدے کے بارے میں اپنا سوال براہ راست لکھیے "
                    "(مثلاً: *'رخصت کی پالیسی کیا ہے؟'*, *'ٹریول الاؤنس کتنا ہے؟'*, *'ڈیٹا پرائیویسی کی کیا پالیسی ہے؟'*).\n\n"
                    "میں تمام شائع شدہ پالیسیوں سے آپ کے لیے درست جواب تلاش کر کے فراہم کروں گا۔"
                )
            elif lang == "Roman Urdu":
                msg = (
                    "🤖 *AI Policy Assistant*\n\n"
                    "Company ki kisi bhi policy ya rule ke baray mein apna sawal poochein "
                    "(maslan: *'Leave policy kya hai?'*, *'Travel allowance kitna hai?'*, *'Data privacy policy kya hai?'*).\n\n"
                    "Main tamam published policies se aap ke liye sahi jawab dhoond kar bataoon ga."
                )
            else:
                msg = (
                    "🤖 *AI Policy Assistant*\n\n"
                    "Ask any question about company policies or workplace guidelines "
                    "(e.g., *'What is the leave policy?'*, *'What are the travel DSA rates?'*, *'What is the data privacy policy?'*).\n\n"
                    "I will search across all published company policies and provide the exact answer for you."
                )
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = wrap_with_menu_again(msg, context)
            action = "start_hr_ai_agent"
            
        elif clean_intent in ("doc_contract", "contract"):
            from ai_workplace.services.employee_letters import generate_experience_letter_pdf, build_letter_download_outbound, build_letter_download_error
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            try:
                pdf_bytes, filename = generate_experience_letter_pdf(context.get("employee", ""))
                caption = "📄 Experience / Employment Document"
                outbound = build_letter_download_outbound(context, pdf_bytes, filename, caption)
            except Exception:
                err = build_letter_download_error(context, "Experience Letter")
                outbound = wrap_with_menu_again(err, context)
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

