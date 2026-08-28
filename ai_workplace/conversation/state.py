"""
ai_workplace/conversation/state.py
───────────────────────────────────
Conversation State & Status Definitions — Phase 2.
"""

from __future__ import annotations


class ConversationStatus:
    ACTIVE = "Active"
    EXPIRED = "Expired"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

    ALL = (ACTIVE, EXPIRED, COMPLETED, CANCELLED)


class ConversationState:
    NEW = "NEW"
    MENU = "MENU"
    AWAITING_SELECTION = "AWAITING_SELECTION"
    PROCESSING = "PROCESSING"
    CONFIRMATION = "CONFIRMATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    ALL = (
        NEW,
        MENU,
        AWAITING_SELECTION,
        PROCESSING,
        CONFIRMATION,
        COMPLETED,
        CANCELLED,
    )
