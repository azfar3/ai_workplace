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
    AWAITING_LANGUAGE = "AWAITING_LANGUAGE"
    LIVE_HR_CHAT = "LIVE_HR_CHAT"
    HR_GUEST_INTAKE = "HR_GUEST_INTAKE"
    HR_CONTACT_PROMPT = "HR_CONTACT_PROMPT"
    WAITING_FOR_SUPPORT_PIN = "WAITING_FOR_SUPPORT_PIN"
    AWAITING_FEEDBACK = "AWAITING_FEEDBACK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    ALL = (
        NEW,
        MENU,
        AWAITING_SELECTION,
        PROCESSING,
        CONFIRMATION,
        AWAITING_LANGUAGE,
        LIVE_HR_CHAT,
        HR_GUEST_INTAKE,
        HR_CONTACT_PROMPT,
        WAITING_FOR_SUPPORT_PIN,
        AWAITING_FEEDBACK,
        COMPLETED,
        CANCELLED,
    )
