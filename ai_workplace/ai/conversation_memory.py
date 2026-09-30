"""
ai_workplace/ai/conversation_memory.py
──────────────────────────────────────
Conversation Memory — Fetches recent turn history for active WhatsApp conversations
and converts it into the OpenAI messages-list format consumed by the LLM.

This enables context-aware, multi-turn conversations so the LLM can understand
follow-up questions like "tell me the topics in the published policy" after a
previous turn that mentioned the policy.

Usage::

    from ai_workplace.ai.conversation_memory import get_conversation_history

    history = get_conversation_history(conv, turns=5)
    # Returns: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
"""

from __future__ import annotations

from typing import Any, List, Optional

import frappe


# Maximum character length for a single assistant or user turn kept in memory.
# Long responses are summarized at the end to avoid exceeding context windows.
_MAX_TURN_CHARS = 1200

# Safety cap on context chars sent to the model (applies to the cumulative history block).
_MAX_HISTORY_CHARS = 4000


def get_conversation_history(
    conv: Any,
    turns: int = 5,
) -> List[dict]:
    """
    Fetch the last ``turns`` round-trips (user + assistant) for the active
    conversation from WhatsApp Message Log records and return them as an
    OpenAI-compatible messages list: [{role, content}, ...].

    Oldest messages are placed first so the LLM gets the correct temporal order.
    Messages are capped at ``_MAX_TURN_CHARS`` each and the cumulative history at
    ``_MAX_HISTORY_CHARS`` to avoid blowing the context window.

    Returns an empty list when no history exists (e.g. first message of session).
    """
    if not conv:
        return []

    wa_id = getattr(conv, "wa_id", "") or ""
    if not wa_id:
        return []

    try:
        if not frappe.db.exists("DocType", "WhatsApp Message Log"):
            return []

        # Fetch recent logs for this WhatsApp ID, most-recent first
        logs = frappe.get_all(
            "WhatsApp Message Log",
            filters={
                "whatsapp_id": wa_id,
                "message_type": ["not in", ["status", "unsupported"]],
                "message": ["!=", ""],
            },
            fields=["direction", "message", "timestamp"],
            order_by="timestamp desc",
            limit=turns * 2,  # grab up to turns round-trips (user + bot each)
        )
    except Exception as exc:
        frappe.logger("ai_workplace").warning(
            f"ConversationMemory: Could not fetch message logs for wa_id={wa_id}: {exc}"
        )
        return []

    if not logs:
        return []

    # Reverse so oldest is first (LLM needs chronological order)
    logs = list(reversed(logs))

    messages: List[dict] = []
    cumulative_chars = 0

    for log in logs:
        direction = (log.get("direction") or "").strip()
        raw_text = (log.get("message") or "").strip()
        if not raw_text:
            continue

        # Map direction → role
        role = "user" if direction == "Inbound" else "assistant"

        # Truncate individual turns that are too long
        text = raw_text if len(raw_text) <= _MAX_TURN_CHARS else raw_text[:_MAX_TURN_CHARS] + "…"

        cumulative_chars += len(text)
        if cumulative_chars > _MAX_HISTORY_CHARS:
            break  # Stop adding more history once the cap is reached

        messages.append({"role": role, "content": text})

    return messages


def build_context_summary(history: List[dict], current_query: str) -> str:
    """
    Build a concise plain-text summary of the conversation history that can be
    injected into a prompt string (for non-messages-list callers).

    Returns an empty string when history is empty.
    """
    if not history:
        return ""

    lines = []
    for msg in history[-6:]:  # Last 6 entries (3 turns max)
        role_label = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['content']}")

    if not lines:
        return ""

    return "Recent conversation:\n" + "\n".join(lines)


def reformulate_query_with_context(
    user_query: str,
    history: List[dict],
) -> str:
    """
    Lightweight context-aware query reformulation.

    Given the user's current (possibly elliptic) query and the conversation
    history, produce a self-contained search query that the RAG indexer can
    reliably match against policy chunks.

    This is a *rule-based* reformulation (no LLM call, zero latency) that:
    1. Detects pronoun/referential ambiguity ("the policy", "that", "it", "those").
    2. Extracts any document title or keyword mentioned in recent assistant turns.
    3. Appends those keywords to the query so the search is self-contained.

    If the query appears self-contained already, the original is returned unchanged.
    """
    if not history or not user_query:
        return user_query

    query_lower = user_query.lower()

    # Ambiguous pronoun/deictic expressions that signal we need context injection
    _AMBIGUOUS_TRIGGERS = (
        " the policy",
        " that policy",
        " this policy",
        " the document",
        " it ",
        " that ",
        " those ",
        " them ",
        " its ",
        "included topics",
        "included sections",
        "what topics",
        "what sections",
        "what does it say",
        "tell me more",
        "more detail",
        "expand on",
        "which topics",
    )

    is_ambiguous = any(t in query_lower for t in _AMBIGUOUS_TRIGGERS) or len(query_lower.split()) <= 5

    if not is_ambiguous:
        return user_query

    # Extract keywords from the most recent assistant turn
    injected_keywords: list[str] = []
    for msg in reversed(history):
        if msg["role"] == "assistant":
            content = msg["content"]
            # Pull out anything in *bold* markers (policy names, titles)
            import re
            bold_terms = re.findall(r"\*([^*]{3,60})\*", content)
            injected_keywords.extend(bold_terms[:3])

            # Also grab the first meaningful line as a context clue
            first_line = content.split("\n")[0][:120].strip()
            if first_line and first_line not in injected_keywords:
                injected_keywords.append(first_line)
            break

    if not injected_keywords:
        return user_query

    # Append keywords to make the query self-contained
    keyword_suffix = " ".join(injected_keywords[:3])
    reformulated = f"{user_query} {keyword_suffix}"
    frappe.logger("ai_workplace").info(
        f"ConversationMemory: Reformulated query: {user_query!r} → {reformulated!r}"
    )
    return reformulated
