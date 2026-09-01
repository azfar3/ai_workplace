"""
AI HR Agent — Deterministic Intent Routing + RAG Evidence Gateway.
"""

from typing import Any
import frappe
from ai_workplace.ai.router import complete, is_ai_chat_enabled
from ai_workplace.ai.tools import run_tool
from ai_workplace.ai.agent import IntentAgent
from ai_workplace.context.schema import AIRequestContext
from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.services.profile_gaps import get_employee_profile_gaps

def start_hr_agent(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    employee = context.get("employee") or ""
    gaps = get_employee_profile_gaps(employee)
    lang = context.get("preferred_language", "English")

    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent="hr_ai_agent",
    )

    from ai_workplace.services.onboarding import get_onboarding_playbook, start_onboarding_agent

    playbook = get_onboarding_playbook(employee)
    if playbook:
        return start_onboarding_agent(conv, context, playbook, gaps)

    name = gaps.get("employee_name") or "there"
    if lang == "Urdu":
        body = f"🤖 *AI HR Assistant*\n\nسلام {name}! میں آپ کی HR پالیسیوں اور پروفائل میں مدد کر سکتا/سکتی ہوں۔"
    else:
        body = (
            f"🤖 *AI HR Assistant*\n\n"
            f"Hello {name}! Ask me about policies, leave, attendance, or your profile.\n"
            f"Type *menu* to exit."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_update_profile", "title": "Update Profile"},
            {"id": "svc_contact_hr", "title": "Contact HR"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )

def handle_hr_agent_message(conv: Any, text: str, context: dict[str, Any]) -> OutboundMessage:
    clean = (text or "").strip()
    lower = clean.lower()

    if lower in ("menu", "main menu", "exit", "quit"):
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None)
        from ai_workplace.conversation.menu import build_menu
        menu_out, _ = build_menu(context)
        return menu_out

    if conv.current_intent == "onboarding_agent":
        from ai_workplace.services.onboarding import handle_onboarding_message
        return handle_onboarding_message(conv, clean, context)

    if not is_ai_chat_enabled():
        return build_button_message(
            "AI Chat is currently offline. Please select an option from the menu or contact HR.",
            [{"id": "svc_contact_hr", "title": "Contact HR"}, {"id": "svc_main_menu", "title": "Main Menu"}],
        )

    # 1. Build Safe AI Request Context
    ai_context = AIRequestContext.from_erp_context(context)
    
    # 2. Determine Intent & Tool via IntentAgent
    agent = IntentAgent()
    trace_id = getattr(conv, "trace_id", "") or ""
    intent_resp = agent.execute(clean, ai_context, trace_id=trace_id)
    
    # 3. Log Intent Decision
    from ai_workplace.conversation.orchestrator import log_ai_action
    log_ai_action(
        trace_id=trace_id,
        conversation_name=conv.name,
        whatsapp_identity=conv.whatsapp_identity,
        intent=intent_resp.intent,
        action="agent_intent_classification",
        result=intent_resp.json(),
        status="Success"
    )

    if not intent_resp.requires_tool:
        # Agent provided a direct conversational response
        return _build_feedback_message(intent_resp.direct_response or "I didn't understand that.", context)

    # 4. Execute the Single Tool Identified by IntentAgent
    tool_name = intent_resp.tool_name
    if not tool_name:
        return _build_feedback_message("I understood your request but no tool was provided to resolve it.", context)

    tool_args = intent_resp.tool_arguments or {}
    
    # RAG search uses 'query' argument, IntentAgent might supply it or we fallback to user text
    if tool_name == "search_knowledge" and "query" not in tool_args:
        tool_args["query"] = clean
        
    raw_result = run_tool(tool_name, context, **tool_args)
    
    # 5. Synthesize Final Response using a generic completion prompt
    synthesis_prompt = f"""
You are an HR Assistant. 
The user asked: "{clean}"
The backend system returned this data for the intent '{intent_resp.intent}':
{raw_result}

Provide a concise, helpful summary in {ai_context.language}. 
If the data contains an error or empty result, politely inform the user.
"""
    synthesis_result = complete(
        messages=[{"role": "system", "content": synthesis_prompt}],
        channel="WhatsApp",
        employee=context.get("employee")
    )
    
    final_text = synthesis_result.get("text") or "I encountered an issue processing the data."
    
    # Redact sensitive text (like PII) using the evidence gateway
    from ai_workplace.ai.evidence import redact_sensitive_text
    final_text = redact_sensitive_text(final_text)
    
    return _build_feedback_message(final_text, context)

def _build_feedback_message(text: str, context: dict) -> OutboundMessage:
    return build_button_message(
        text,
        [
            {"id": "fb_helpful", "title": "👍 Helpful"},
            {"id": "fb_not_helpful", "title": "👎 Not Helpful"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )
