"""
ai_workplace/ai/hybrid_handler.py
──────────────────────────────────
Phase 4 — Lightweight Hybrid Handler.

Architecture:
  1. Run deterministic tool  → get authoritative data (0 LLM calls)
  2. Pass data to LLM         → synthesise natural-language answer (1 LLM call)
  3. Deterministic fallback   → format_response() if LLM unavailable/fails

Contrast with the full hr_agent agentic loop (2-5 LLM calls + tool-call cycle).
The LLM here receives structured data; it cannot call tools, cannot hallucinate
numbers.  It can only narrate what the data says.

Usage::

    from ai_workplace.ai.hybrid_handler import handle_hybrid

    outbound = handle_hybrid(
        intent_key="carry_forward_leave",
        tool_name="search_knowledge",
        context=context,
        user_query="Can I carry forward my unused annual leave?",
        conv=conv,
        trace_id=trace_id,
    )
"""

from __future__ import annotations

from typing import Any, Optional

import frappe

from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message


def handle_hybrid(
    *,
    intent_key: str,
    tool_name: str,
    context: dict[str, Any],
    user_query: str,
    conv: Any,
    trace_id: str = "",
) -> OutboundMessage:
    """
    Lightweight hybrid: fetch data deterministically, then ask the LLM to
    narrate the result in natural language.  One LLM call maximum.

    Falls back to deterministic ResponseFormatter if:
    - AI Chat is disabled globally
    - The LLM call fails / times out
    - The LLM returns an empty response
    """
    from ai_workplace.ai.tools import run_tool
    from ai_workplace.ai.router import complete, is_ai_chat_enabled
    from ai_workplace.ai.response_formatter import ResponseFormatter

    # ── 1. Fetch authoritative data ────────────────────────────────────────────
    try:
        raw_data = run_tool(tool_name, context, query=user_query)
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"HybridHandler: tool {tool_name!r} failed: {exc}"
        )
        raw_data = {}

    # ── 2. If no data worth synthesising, return deterministic fallback ────────
    if not raw_data or (isinstance(raw_data, (list, dict)) and not raw_data):
        return _fallback(intent_key, raw_data, context)

    # ── 3. If AI is disabled, return deterministic fallback ───────────────────
    if not is_ai_chat_enabled():
        return _fallback(intent_key, raw_data, context)

    # ── 4. LLM synthesis — narrate, don't calculate ───────────────────────────
    lang = context.get("preferred_language", "English")
    lang_instruction = {
        "Urdu": "اردو میں جواب دیں۔ مختصر اور واضح رہیں۔",
        "Roman Urdu": "Roman Urdu mein jawab dein. Mukhtasir aur wazeh rahein.",
        "English": "Respond in clear, concise English.",
    }.get(lang, "Respond in clear, concise English.")

    synthesis_system = (
        "You are a helpful HR assistant. You answer employee questions using only "
        "the structured data provided. You do NOT invent facts, numbers, or policies "
        "that are not in the data. You do NOT call any tools. You only narrate the "
        "data clearly and naturally."
    )

    synthesis_prompt = (
        f"Employee asked: \"{user_query}\"\n\n"
        f"Here is the authoritative data from the HR system:\n{raw_data}\n\n"
        f"{lang_instruction}"
    )

    try:
        res = complete(
            prompt=synthesis_prompt,
            system=synthesis_system,
            channel="WhatsApp",
            employee=context.get("employee", ""),
        )
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"HybridHandler: LLM synthesis failed for {intent_key!r}: {exc}"
        )
        return _fallback(intent_key, raw_data, context)

    if not res.get("success") or not res.get("text"):
        frappe.logger("ai_workplace").warning(
            f"HybridHandler: LLM returned no text for {intent_key!r}"
        )
        return _fallback(intent_key, raw_data, context)

    # ── 5. Build response with feedback buttons ────────────────────────────────
    _log_hybrid(intent_key, tool_name, context, conv, trace_id, res)

    return build_button_message(
        res["text"],
        [
            {"id": "fb_helpful", "title": "👍 Helpful"},
            {"id": "fb_not_helpful", "title": "👎 Not Helpful"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def _fallback(intent_key: str, raw_data: Any, context: dict[str, Any]) -> OutboundMessage:
    """Return a deterministically-formatted response when LLM is unavailable."""
    from ai_workplace.ai.response_formatter import ResponseFormatter

    try:
        text = ResponseFormatter.format_response(intent_key, raw_data)
    except Exception:
        text = str(raw_data) if raw_data else "I could not retrieve that information right now."

    return build_button_message(
        text,
        [
            {"id": "fb_helpful", "title": "👍 Helpful"},
            {"id": "fb_not_helpful", "title": "👎 Not Helpful"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def _log_hybrid(
    intent_key: str,
    tool_name: str,
    context: dict[str, Any],
    conv: Any,
    trace_id: str,
    llm_res: dict[str, Any],
) -> None:
    """Log hybrid call to AI Action Log."""
    try:
        from ai_workplace.conversation.orchestrator import log_ai_action

        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent=intent_key,
            service=tool_name,
            action="hybrid_synthesis",
            result=(llm_res.get("text") or "")[:500],
            status="Success",
        )
    except Exception:
        pass
