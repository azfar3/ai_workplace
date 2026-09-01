"""
AI HR Agent — Deterministic Intent Routing + RAG Evidence Gateway.
"""

from typing import Any
import frappe
from ai_workplace.ai.router import complete, is_ai_chat_enabled
from ai_workplace.ai.tools import run_tool

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
    
    # 2. Extract allowed tools based on context
    allowed_tools = []
    from ai_workplace.ai.intent_catalog import INTENT_CATALOG
    for intent in (ai_context.allowed_intents or []):
        if intent in INTENT_CATALOG:
            t = INTENT_CATALOG[intent].get("tool")
            if t and t != "clarification":
                allowed_tools.append(t)
    
    from ai_workplace.ai.tools import get_openai_tools_schema
    tools_schema = get_openai_tools_schema(allowed_tools)

    # 3. Setup ReAct Loop Prompts
    system_prompt = f"""You are a highly capable AI HR Assistant.
Your goal is to answer the user's questions or execute HR processes by reasoning and calling the appropriate tools.
- ONLY answer questions using data from your tools. Do not invent HR facts.
- The user is: {ai_context.employee_name or 'Guest'}.
- Always reply in {ai_context.language}.
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": clean}
    ]

    # 4. Agentic Planner Loop (Max 5 Steps)
    MAX_STEPS = 5
    for step in range(MAX_STEPS):
        res = complete(
            messages=messages, 
            tools=tools_schema if tools_schema else None, 
            channel="WhatsApp", 
            employee=context.get("employee")
        )
        
        if not res.get("success"):
            return _build_feedback_message("I am experiencing technical difficulties.", context)
        
        # Append assistant message
        msg_obj = res.get("raw_message", {})
        if msg_obj:
            messages.append(msg_obj)
        else:
            messages.append({"role": "assistant", "content": res.get("text") or ""})
            
        tool_calls = res.get("tool_calls", [])
        if not tool_calls:
            # Planner has finished reasoning and provided a direct response
            final_text = res.get("text") or "I couldn't find an answer."
            
            # 5. Redact sensitive text (like PII) using the evidence gateway
            from ai_workplace.ai.evidence import redact_sensitive_text
            final_text = redact_sensitive_text(final_text)
            
            # Log final response
            trace_id = getattr(conv, "trace_id", "") or ""
            from ai_workplace.conversation.orchestrator import log_ai_action
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                intent="planner_synthesis",
                action="agent_planner_loop",
                result={"steps": step + 1, "final_text": final_text},
                status="Success"
            )
            return _build_feedback_message(final_text, context)
            
        # Execute tools observed by the planner
        import json
        for tc in tool_calls:
            t_name = tc.get("function", {}).get("name")
            try:
                t_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except Exception:
                t_args = {}
                
            raw_res = run_tool(t_name, context, **t_args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "name": t_name,
                "content": json.dumps(raw_res) if isinstance(raw_res, dict) else str(raw_res)
            })

    return _build_feedback_message("I had to stop because the task took too many steps. Please try asking more specifically.", context)

def _build_feedback_message(text: str, context: dict) -> OutboundMessage:
    return build_button_message(
        text,
        [
            {"id": "fb_helpful", "title": "👍 Helpful"},
            {"id": "fb_not_helpful", "title": "👎 Not Helpful"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )

def _mask_sensitive(text: str) -> str:
    import re
    if not text:
        return ""
    # Mask 13-digit CNIC numbers
    text = re.sub(r"\b\d{13}\b", "*****", text)
    text = re.sub(r"\b\d{5}-\d{7}-\d{1}\b", "*****", text)
    return text

