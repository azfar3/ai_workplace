"""
ai_workplace/conversation/manager.py
──────────────────────────────────────
Conversation Manager — Phase 2.

Manages session lifecycle, active conversation retrieval, TTL expiration,
state persistence, and transaction updates for WhatsApp Conversation records.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import frappe

from ai_workplace.conversation.state import ConversationStatus, ConversationState
from ai_workplace.identity.resolver import get_or_create_whatsapp_identity


def get_default_ttl_minutes() -> int:
    """Read conversation TTL in minutes from AI Workplace Settings."""
    try:
        settings = frappe.get_single("AI Workplace Settings")
        ttl = settings.get("conversation_ttl_minutes")
        if ttl and int(ttl) > 0:
            return int(ttl)
    except Exception:
        pass
    return 30


def get_or_create_conversation(
    identity: Any,
    wa_id: str = "",
    trace_id: str = "",
) -> "frappe.Document":
    """
    Get existing active conversation for identity or create a new one. Handles TTL expiry.

    Parameters
    ----------
    identity : IdentityResult | dict
        Identity object or dictionary.
    wa_id : str
        WhatsApp sender ID.
    trace_id : str
        Request trace ID.

    Returns
    -------
    WhatsApp Conversation document.
    """
    # 1. Ensure WhatsApp Identity record exists
    wa_identity_doc = get_or_create_whatsapp_identity(identity, wa_id=wa_id)

    if isinstance(identity, dict):
        erp_user = identity.get("user")
        employee = identity.get("employee")
        pref_lang = identity.get("preferred_language", "English")
    else:
        erp_user = identity.user
        employee = identity.employee
        pref_lang = getattr(identity, "preferred_language", "English")

    now = frappe.utils.now_datetime()
    ttl_minutes = get_default_ttl_minutes()
    expires_at = now + timedelta(minutes=ttl_minutes)

    # 2. Look up existing active conversation for this identity
    active_conv_name = frappe.db.get_value(
        "WhatsApp Conversation",
        {
            "whatsapp_identity": wa_identity_doc,
            "conversation_status": ConversationStatus.ACTIVE,
        },
        "name",
    )

    if active_conv_name:
        conv = frappe.get_doc("WhatsApp Conversation", active_conv_name)
        # Check Expiry
        if conv.expires_at and conv.expires_at < now:
            expire_conversation(conv, trace_id=trace_id)
            # Fall through to create a new session
        else:
            # Re-use active session
            conv.last_activity_at = now
            conv.expires_at = expires_at
            if trace_id:
                conv.trace_id = trace_id
            if erp_user and not conv.erp_user:
                conv.erp_user = erp_user
            if employee and not conv.employee:
                conv.employee = employee
            conv.flags.ignore_links = True
            conv.save(ignore_permissions=True)
            frappe.db.commit()
            return conv

    # 3. Create brand new conversation session
    conv = frappe.new_doc("WhatsApp Conversation")
    conv.whatsapp_identity = wa_identity_doc
    conv.wa_id = wa_id or getattr(identity, "normalized_phone", "")
    conv.erp_user = erp_user or None
    conv.employee = employee or None
    conv.conversation_status = ConversationStatus.ACTIVE
    conv.current_state = ConversationState.NEW
    conv.preferred_language = pref_lang or "English"
    conv.started_at = now
    conv.last_activity_at = now
    conv.expires_at = expires_at
    conv.trace_id = trace_id
    conv.flags.ignore_links = True
    conv.insert(ignore_permissions=True)
    frappe.db.commit()
    return conv


def update_conversation(
    conversation: "frappe.Document",
    state: Optional[str] = None,
    current_intent: Optional[str] = None,
    active_service: Optional[str] = None,
    active_record: Optional[str] = None,
    draft_payload: Optional[str] = None,
    preferred_language: Optional[str] = None,
    last_message_id: Optional[str] = None,
) -> "frappe.Document":
    """Update conversation state, fields, and activity timestamp."""
    now = frappe.utils.now_datetime()
    ttl_minutes = get_default_ttl_minutes()

    if state:
        conversation.current_state = state
    if current_intent is not None:
        conversation.current_intent = current_intent
    if active_service is not None:
        conversation.active_service = active_service
    if active_record is not None:
        conversation.active_record = active_record
    if draft_payload is not None:
        conversation.draft_payload = draft_payload
    if preferred_language is not None:
        conversation.preferred_language = preferred_language
    if last_message_id:
        conversation.last_message_id = last_message_id

    conversation.last_activity_at = now
    conversation.expires_at = now + timedelta(minutes=ttl_minutes)
    conversation.flags.ignore_links = True
    conversation.save(ignore_permissions=True)
    frappe.db.commit()
    return conversation


def expire_conversation(
    conversation: "frappe.Document",
    trace_id: str = "",
) -> "frappe.Document":
    """Mark conversation as Expired."""
    conversation.conversation_status = ConversationStatus.EXPIRED
    conversation.current_state = ConversationState.CANCELLED
    conversation.flags.ignore_links = True
    conversation.save(ignore_permissions=True)
    frappe.db.commit()

    # Log security event for conversation expiry
    try:
        sec = frappe.new_doc("AI Security Event")
        sec.event_type = "Expired Conversation"
        sec.severity = "Low"
        sec.whatsapp_id = conversation.wa_id
        sec.trace_id = trace_id or conversation.trace_id
        sec.description = f"Conversation {conversation.name} expired due to inactivity."
        sec.timestamp = frappe.utils.now_datetime()
        sec.flags.ignore_links = True
        sec.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return conversation


def cancel_conversation(conversation: "frappe.Document") -> "frappe.Document":
    """Cancel conversation session."""
    conversation.conversation_status = ConversationStatus.CANCELLED
    conversation.current_state = ConversationState.CANCELLED
    conversation.flags.ignore_links = True
    conversation.save(ignore_permissions=True)
    frappe.db.commit()
    return conversation


def complete_conversation(conversation: "frappe.Document") -> "frappe.Document":
    """Complete conversation session."""
    conversation.conversation_status = ConversationStatus.COMPLETED
    conversation.current_state = ConversationState.COMPLETED
    conversation.flags.ignore_links = True
    conversation.save(ignore_permissions=True)
    frappe.db.commit()
    return conversation
