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
        
        if clean_intent in ("pol_view_policies", "pol_policy_hub"):
            from ai_workplace.services.policies import build_policies_list_message
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_policies_list_message(context)
            action = "view_published_policies"
            
        elif clean_intent in ("pol_ai_assistant", "policies_help"):
            from ai_workplace.whatsapp.interactive import build_show_menu_again_button
            lang = context.get("preferred_language", "English")
            if lang == "Urdu":
                msg = "💬 *پالیسی اور HR اسسٹنٹ*\n\nآپ کسی بھی وقت اپنا سوال یہاں لکھیے (مثلاً: رخصت کی پالیسی کیا ہے؟، پروProbation کا دورانیہ کتنا ہے؟)۔"
            elif lang == "Roman Urdu":
                msg = "💬 *Policy & HR Assistant*\n\nAap kisi bhi waqt apna sawal yahan likhein (maslan: leave policy kya hai?, probation period kitna hai?)."
            else:
                msg = "💬 *Policy & HR Assistant*\n\nYou can ask any HR or policy question directly here (e.g. *'What is the leave policy?'*, *'How long is probation?'*)."
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

