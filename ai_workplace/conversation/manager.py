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
    return 60


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
    active_hr_chat_session: Optional[str] = None,
    clear_active_hr_chat_session: bool = False,
    clear_active_fields: bool = False,
) -> "frappe.Document":
    """Update conversation state, fields, and activity timestamp."""
    now = frappe.utils.now_datetime()
    ttl_minutes = get_default_ttl_minutes()

    if clear_active_fields:
        conversation.current_intent = None
        conversation.active_service = None
        conversation.active_record = None
        conversation.draft_payload = None

    if state:
        conversation.current_state = state
    if current_intent is not None:
        conversation.current_intent = current_intent or None
    if active_service is not None:
        conversation.active_service = active_service or None
    if active_record is not None:
        conversation.active_record = active_record or None
    if draft_payload is not None:
        conversation.draft_payload = draft_payload or None
    if preferred_language is not None:
        conversation.preferred_language = preferred_language
    if last_message_id:
        conversation.last_message_id = last_message_id
    if active_hr_chat_session is not None:
        conversation.active_hr_chat_session = active_hr_chat_session or None
    if clear_active_hr_chat_session:
        conversation.active_hr_chat_session = None

    conversation.last_activity_at = now
    conversation.expires_at = now + timedelta(minutes=ttl_minutes)
    conversation.flags.ignore_links = True
    conversation.save(ignore_permissions=True)
    frappe.db.commit()
    return conversation


def conversation_priority_expects_media(conversation: Any) -> bool:
    """
    True when an active multi-step flow should receive inbound media instead of
    HR live chat (e.g. CNIC scan upload during profile completion).
    """
    if (conversation.current_state or "") != ConversationState.PROCESSING:
        return False
    intent = (conversation.current_intent or "").strip()
    if intent.startswith("prof_") or intent == "deliverable_add":
        return True
    if intent in ("att_checkin", "att_checkout", "att_exception"):
        return True
    return False


def conversation_priority_expects_location(conversation: Any) -> bool:
    """True when a pending attendance flow should receive inbound location."""
    if (conversation.current_state or "") != ConversationState.PROCESSING:
        return False
    intent = (conversation.current_intent or "").strip()
    return intent in ("att_checkin", "att_checkout", "att_exception")


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


@frappe.whitelist()
def close_inactive_sessions() -> dict[str, Any]:
    """
    Check for active conversations where expires_at <= now.
    Closes inactive sessions and sends an automated Bye message to the user.
    """
    now = frappe.utils.now_datetime()
    expired_convs = frappe.get_all(
        "WhatsApp Conversation",
        filters={
            "conversation_status": ConversationStatus.ACTIVE,
            "expires_at": ("<=", now),
        },
        fields=[
            "name",
            "whatsapp_identity",
            "wa_id",
            "preferred_language",
            "active_hr_chat_session",
            "erp_user",
            "employee",
            "trace_id",
        ],
    )

    closed_count = 0
    for row in expired_convs:
        try:
            conv = frappe.get_doc("WhatsApp Conversation", row.name)

            # Close active HR chat session if any
            if conv.active_hr_chat_session:
                try:
                    from ai_workplace.services.hr_chat import close_session
                    close_session(conv.active_hr_chat_session, reset_conversation=False)
                except Exception:
                    pass

            # Mark conversation expired & awaiting feedback
            expire_conversation(conv, trace_id=row.trace_id or "")
            conv.current_state = ConversationState.AWAITING_FEEDBACK
            conv.save(ignore_permissions=True)

            # Get recipient phone number
            phone_number = None
            if conv.whatsapp_identity:
                phone_number = frappe.db.get_value(
                    "WhatsApp Identity", conv.whatsapp_identity, "normalized_phone"
                )
            if not phone_number and conv.wa_id:
                phone_number = conv.wa_id

            if phone_number:
                lang = conv.preferred_language or "English"
                if lang == "Urdu":
                    bye_text = (
                        "غیرفعالیت کی وجہ سے آپ کا سیشن ختم کر دیا گیا ہے۔ خدا حافظ! 👋\n\n"
                        "آپ کا دن اچھا گزرے۔\n\n"
                        "⭐ *آج آپ کا تجربہ کیسا رہا؟*\n"
                        "براہ کرم 1 سے 5 تک کی درجہ بندی کریں:\n"
                        "1️⃣ ⭐️ خراب\n"
                        "2️⃣ ⭐️⭐️ مناسب\n"
                        "3️⃣ ⭐️⭐️⭐️ اچھا\n"
                        "4️⃣ ⭐️⭐️⭐️⭐️ بہت اچھا\n"
                        "5️⃣ ⭐️⭐️⭐️⭐️⭐️ بہترین\n\n"
                        "(یا اپنے تاثرات لکھیے!)"
                    )
                elif lang == "Roman Urdu":
                    bye_text = (
                        "Ghair-faaliyat ki wajah se aap ka session close ho gaya hai. Khuda Hafiz! 👋\n\n"
                        "Aap ka din accha guzre.\n\n"
                        "⭐ *Aaj aap ka experience kaisa raha?*\n"
                        "Barah-e-karam 1 se 5 rating dein:\n"
                        "1️⃣ ⭐️ Poor\n"
                        "2️⃣ ⭐️⭐️ Fair\n"
                        "3️⃣ ⭐️⭐️⭐️ Good\n"
                        "4️⃣ ⭐️⭐️⭐️⭐ Very Good\n"
                        "5️⃣ ⭐️⭐️⭐️⭐️⭐️ Excellent\n\n"
                        "(Ya apna feedback likhein!)"
                    )
                else:
                    bye_text = (
                        "Your session has expired due to inactivity. Goodbye! 👋\n\n"
                        "Have a great day!\n\n"
                        "⭐ *How was your experience today?*\n"
                        "Please rate your session from 1 to 5:\n"
                        "1️⃣ ⭐ Poor\n"
                        "2️⃣ ⭐⭐ Fair\n"
                        "3️⃣ ⭐⭐⭐ Good\n"
                        "4️⃣ ⭐⭐⭐⭐ Very Good\n"
                        "5️⃣ ⭐⭐⭐⭐⭐ Excellent\n\n"
                        "(Or reply with any feedback comments!)"
                    )

                from ai_workplace.whatsapp.sender import send_message
                from ai_workplace.whatsapp.outbound import OutboundMessage

                outbound = OutboundMessage(body_text=bye_text)
                send_res = send_message(phone_number=phone_number, outbound=outbound)

                # Create Outbound WhatsApp Message Log
                try:
                    doc_log = frappe.new_doc("WhatsApp Message Log")
                    doc_log.meta_message_id = send_res.get("message_id") or ""
                    doc_log.direction = "Outbound"
                    doc_log.sender = ""
                    doc_log.recipient = phone_number
                    doc_log.whatsapp_id = conv.wa_id or ""
                    doc_log.message_type = "text"
                    doc_log.message = bye_text
                    doc_log.erp_user = conv.erp_user or ""
                    doc_log.employee = conv.employee or ""
                    doc_log.status = "Sent" if send_res.get("success") else "Failed"
                    doc_log.trace_id = conv.trace_id or ""
                    doc_log.sender_type = "System"
                    doc_log.timestamp = now
                    doc_log.flags.ignore_links = True
                    doc_log.insert(ignore_permissions=True)
                except Exception as log_err:
                    frappe.logger("ai_workplace").error(
                        f"Failed to log inactive session bye message: {log_err}"
                    )

            closed_count += 1
            frappe.db.commit()

        except Exception as exc:
            frappe.logger("ai_workplace").error(
                f"Failed to close inactive conversation {row.name}: {exc}"
            )

    return {"status": "success", "closed_count": closed_count}
