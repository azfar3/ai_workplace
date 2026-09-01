"""
Redact Support PIN and PIN-shaped inbound text before logging.
"""

from __future__ import annotations

import re

REDACTED_PLACEHOLDER = "[SUPPORT PIN REDACTED]"
_PIN_TEXT_PATTERN = re.compile(r"^\d{4}$")


def is_pin_shaped_text(text: str) -> bool:
    if not text:
        return False
    cleaned = text.strip()
    return bool(_PIN_TEXT_PATTERN.match(cleaned))


def redact_message_for_log(text: str, *, force: bool = False) -> str:
    """Return safe text for WhatsApp Message Log and HR inbox."""
    if force or is_pin_shaped_text(text):
        return REDACTED_PLACEHOLDER
    return text


def should_redact_inbound(conversation_state: str) -> bool:
    from ai_workplace.conversation.state import ConversationState

    return conversation_state == ConversationState.WAITING_FOR_SUPPORT_PIN
