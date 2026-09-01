"""
AI HR Agent — Native LLM tool calling, hybrid RAG citations, evidence gateway, and continuous feedback.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

import frappe

from ai_workplace.ai.router import complete, is_ai_chat_enabled
from ai_workplace.ai.indexer import search_knowledge
from ai_workplace.ai.tools import get_openai_tools_schema, run_tool, TOOL_REGISTRY
from ai_workplace.ai.prompts.reactive_qa import REACTIVE_QA, TOOL_SELECTION
from ai_workplace.ai.evidence import redact_sensitive_text
from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.services.profile_gaps import get_employee_profile_gaps

ESCALATION_KEYWORDS = re.compile(
    r"\b(harassment|fraud|legal|lawyer|sue|discriminat)\b",
    re.I,
)

ALLOWED_TOOLS = frozenset(TOOL_REGISTRY.keys())


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

    # 1. Interactive Button Handlers in HR Agent session
    if lower in ("fb_helpful", "👍 helpful"):
        _log_feedback("HELPFUL", clean, context, conv)
        return OutboundMessage(
            body_text="Thank you for your feedback! 😊\n\nIs there anything else I can help you with today? Feel free to ask another question or type *menu*."
        )

    if lower in ("fb_not_helpful", "👎 not helpful"):
        _log_feedback("NOT_HELPFUL", clean, context, conv)
        return OutboundMessage(
            body_text="Thank you for your feedback! An HR representative will review this topic to improve our responses.\n\nIs there anything else I can help you with today? Feel free to ask another question or type *menu*."
        )

    if lower in ("svc_contact_hr", "talk to hr", "contact hr", "👤 talk to hr"):
        from ai_workplace.services.registry import execute_service
        return execute_service("contact_hr", conv, context)

    if lower in ("menu", "main menu", "exit", "quit"):
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None)
        from ai_workplace.conversation.menu import build_menu

        menu_out, _ = build_menu(context)
        return menu_out

    if conv.current_intent == "onboarding_agent":
        from ai_workplace.services.onboarding import handle_onboarding_message

        return handle_onboarding_message(conv, clean, context)

    if ESCALATION_KEYWORDS.search(clean):
        return build_button_message(
            "This sounds like a sensitive matter. Please use Contact HR or submit a confidential Concern.",
            [
                {"id": "svc_contact_hr", "title": "Contact HR"},
                {"id": "svc_concerns", "title": "Report Concern"},
            ],
        )

    # 2. Feature Flag Check: Strict AI OFF Guarantee
    if not is_ai_chat_enabled():
        return build_button_message(
            "AI Chat is currently offline. Please select an option from the menu or contact HR.",
            [
                {"id": "svc_contact_hr", "title": "Contact HR"},
                {"id": "svc_main_menu", "title": "Main Menu"},
            ],
        )

    employee = context.get("employee") or ""
    emp_type = context.get("employment_type") or ""
    if not emp_type and employee:
        try:
            emp_type = frappe.db.get_value("Employee", employee, "employment_type") or "Full-time"
        except Exception:
            emp_type = "Full-time"
    
    # 3. Hybrid RAG Search with Metadata & Citations
    knowledge = search_knowledge(clean, limit=3, employment_type=emp_type)
    knowledge_text = ""
    source_citations = []
    if knowledge:
        k_lines = []
        for k in knowledge:
            src = k.get("source_title") or k.get("document") or k.get("source")
            sec = k.get("section") or "General"
            k_lines.append(f"[Source: {src} | Section: {sec}]\n{k['text'][:500]}")
            if src and src not in source_citations:
                source_citations.append(f"• {src} ({sec})")
        knowledge_text = "\n\n".join(k_lines)

    history_text = _get_recent_conversation_history(conv)
    openai_tools = get_openai_tools_schema()

    # 4. Native Tool Calling Loop with Multi-turn Execution
    system_prompt = REACTIVE_QA
    user_metadata = (
        f"Authenticated Context:\n"
        f"- Employee ID: {employee}\n"
        f"- Employment Type: {emp_type}\n\n"
        f"Recent History:\n{history_text}\n\n"
        f"Relevant Policy Evidence:\n{knowledge_text or 'No specific policy chunk matched.'}"
    )

    initial_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{user_metadata}\n\nUser Question: {clean}"},
    ]

    result = complete(
        messages=initial_messages,
        tools=openai_tools,
        channel="WhatsApp",
        employee=employee,
    )

    # Handle Tool Calling Loop if Model requests tool calls
    if result.get("success") and result.get("tool_calls"):
        tool_calls = result["tool_calls"]
        messages_with_tools = list(initial_messages)
        raw_msg = result.get("raw_message") or {
            "role": "assistant",
            "content": result.get("text") or "",
            "tool_calls": tool_calls,
        }
        messages_with_tools.append(raw_msg)

        executed_tools = []
        for tc in tool_calls:
            func = tc.get("function", {})
            t_name = func.get("name", "")
            t_id = tc.get("id", f"call_{t_name}")
            args_str = func.get("arguments", "{}")
            try:
                t_args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except Exception:
                t_args = {}

            # Execute tool server-side with strict employee identity override
            t_res = run_tool(t_name, context, **t_args)
            executed_tools.append(t_name)

            messages_with_tools.append({
                "role": "tool",
                "tool_call_id": t_id,
                "name": t_name,
                "content": json.dumps(t_res),
            })

        # Second completion turn passing tool execution results
        result = complete(
            messages=messages_with_tools,
            channel="WhatsApp",
            employee=employee,
        )

    # 5. Deterministic Fallback if Native LLM Tool Calling returned nothing or failed
    if not result.get("success") or (not result.get("text") and not result.get("tool_calls")):
        tool_names = _select_tools(clean)
        tool_context = _run_tools(tool_names, context, clean)
        fallback_prompt = (
            f"{user_metadata}\n\n"
            f"Tool Execution Results:\n{tool_context}\n\n"
            f"User question: {clean}"
        )
        result = complete(
            fallback_prompt,
            system=REACTIVE_QA,
            channel="WhatsApp",
            employee=employee,
        )

    _log_agent_turn(conv, context, clean, result)

    if not result.get("success"):
        _log_knowledge_gap(clean, context, failure_reason="LLM_FAILURE", ai_response=result.get("error", ""))
        return OutboundMessage(
            body_text="I'm having trouble reaching the AI service right now. Please try again or contact HR."
        )

    reply = result.get("text", "")
    reply = redact_sensitive_text(reply)

    # Attach Source Citations to answer if policy knowledge was used
    if source_citations and any(term in lower for term in ("policy", "rule", "leave", "entitlement", "notice", "probation")):
        if "\n\n*Sources:*" not in reply and "Source:" not in reply:
            reply += "\n\n📚 *Sources:*\n" + "\n".join(source_citations)

    # Attach Interactive Feedback Options
    return build_button_message(
        reply,
        [
            {"id": "fb_helpful", "title": "👍 Helpful"},
            {"id": "fb_not_helpful", "title": "👎 Not Helpful"},
            {"id": "svc_contact_hr", "title": "👤 Talk to HR"},
        ],
    )


def _select_tools(question: str) -> list[str]:
    from ai_workplace.ai_workplace.doctype.ai_intent_pattern.ai_intent_pattern import match_intent_pattern

    matched = match_intent_pattern(question)
    if matched and matched.get("tools"):
        return [t for t in matched["tools"] if t in ALLOWED_TOOLS]

    deterministic = _fallback_tools(question)
    lower = question.lower()
    if any(w in lower for w in ("leave", "leaves", "balance", "sick", "casual", "annual", "attendance", "present", "absent", "employment", "designation", "department", "profile")):
        return deterministic

    try:
        result = complete(
            f"User question: {question}",
            system=TOOL_SELECTION,
            channel="WhatsApp",
        )
        if result.get("success"):
            raw = result.get("text", "")
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                data = json.loads(match.group())
                tools = [t for t in data.get("tools", []) if t in ALLOWED_TOOLS]
                if tools:
                    return list(dict.fromkeys(deterministic + tools))
    except Exception:
        pass

    return deterministic


def _fallback_tools(question: str) -> list[str]:
    lower = question.lower()
    tools = []
    
    if any(w in lower for w in ("profile", "complete", "cnic", "bank", "education", "degree", "father", "dob", "missing", "employment", "job", "designation", "department", "role", "title", "type", "salary")):
        tools.append("get_profile_gaps")
    if any(w in lower for w in ("attendance", "check in", "checkin", "check-in", "missing", "present", "absent", "late", "early", "time")):
        tools.append("get_attendance_summary")
    if any(w in lower for w in ("leave", "leaves", "balance", "vacation", "casual", "sick", "annual", "time off", "day off", "entitlement", "remaining")):
        tools.append("get_leave_balance")
    if any(w in lower for w in ("policy", "policies", "sop", "rule", "rules", "guideline", "guidelines", "hours", "handbook", "allowance")):
        tools.extend(["search_knowledge", "get_published_policies"])
        
    if not tools:
        tools.append("search_knowledge")
    return list(dict.fromkeys(tools))


def _run_tools(tool_names: list[str], context: dict[str, Any], question: str) -> str:
    parts = []
    for name in tool_names:
        kwargs = {"query": question} if name == "search_knowledge" else {}
        try:
            result = run_tool(name, context, **kwargs)
            parts.append(f"{name}: {result}")
        except Exception as exc:
            parts.append(f"{name}: error {exc}")
    return "\n".join(parts)


def _get_recent_conversation_history(conv: Any, limit: int = 4) -> str:
    try:
        msgs = frappe.get_all(
            "WhatsApp Message Log",
            filters={"whatsapp_id": conv.whatsapp_identity},
            fields=["direction", "message"],
            order_by="creation desc",
            limit=limit,
        )
        msgs.reverse()
        history = []
        for m in msgs:
            role = "User" if m.direction == "Inbound" else "Assistant"
            text = (m.message or "").strip()[:150]
            if text:
                history.append(f"{role}: {text}")
        return "\n".join(history)
    except Exception:
        return ""


def _confidence_threshold() -> float:
    try:
        settings = frappe.get_single("AI Workplace Settings")
        return float(getattr(settings, "agent_confidence_threshold", 0) or 0)
    except Exception:
        return 0


def _log_feedback(feedback_type: str, raw_text: str, context: dict, conv: Any):
    try:
        doc = frappe.new_doc("AI Feedback Log")
        doc.feedback_type = feedback_type
        if feedback_type == "NOT_HELPFUL":
            doc.feedback_reason = "IRRELEVANT"
        doc.query = raw_text
        doc.employee = context.get("employee")
        doc.user = context.get("user")
        doc.whatsapp_identity = conv.whatsapp_identity
        doc.insert(ignore_permissions=True)
    except Exception:
        pass


def _log_knowledge_gap(query: str, context: dict, failure_reason: str = "NO_KNOWLEDGE", ai_response: str = ""):
    try:
        from ai_workplace.ai_workplace.doctype.ai_knowledge_gap_log.ai_knowledge_gap_log import log_knowledge_gap

        log_knowledge_gap(
            query=query,
            context=context,
            failure_reason=failure_reason,
            detected_intent="hr_ai_agent",
            ai_response=ai_response
        )
    except Exception:
        pass


def _log_agent_turn(conv: Any, context: dict[str, Any], question: str, result: dict) -> None:
    try:
        from ai_workplace.conversation.orchestrator import log_ai_action

        log_ai_action(
            trace_id=getattr(conv, "trace_id", "") or "",
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=context.get("employee") or "",
            intent="hr_ai_agent",
            service="pol_ai_assistant",
            action="agent_turn",
            result=(result.get("text") or "")[:500],
            status="Success" if result.get("success") else "Failed",
        )
    except Exception:
        pass
