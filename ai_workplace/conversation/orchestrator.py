"""
ai_workplace/conversation/orchestrator.py
───────────────────────────────────────────
Conversation Orchestrator — Phase 2.

Central coordinator for Phase 2 message flow:
  Incoming Message
         ↓
  Identity
         ↓
  ERP Context Resolver
         ↓
  Authorization Gateway
         ↓
  Conversation Manager (Session State)
         ↓
  Dynamic Menu / Service Router
         ↓
  Response Builder
         ↓
  AI Action Logging
"""

from __future__ import annotations

from typing import Any, Optional
import frappe

from ai_workplace.context.resolver import get_user_context
from ai_workplace.auth.gateway import authorize
from ai_workplace.conversation.manager import (
    get_or_create_conversation,
    update_conversation,
    cancel_conversation,
)
from ai_workplace.conversation.state import ConversationState
from ai_workplace.conversation.menu import (
    build_menu,
    parse_menu_selection,
    build_invalid_selection_message,
)
from ai_workplace.services.registry import get_available_services_for_context
from ai_workplace.response.builder import (
    build_cancellation_response,
    build_unauthorized_response,
    build_service_placeholder_response,
    build_help_response,
)


def process_message(
    message_text: str,
    identity: Any,
    message_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    wa_id: Optional[str] = None,
) -> str:
    """
    Orchestrate incoming WhatsApp message through context, authorization, state machine, and service routing.

    Parameters
    ----------
    message_text : str
        The user's message body.
    identity : IdentityResult | dict
        Identity resolution object or dict.
    message_id : str, optional
        Meta message ID.
    trace_id : str, optional
        Trace ID for logging.
    wa_id : str, optional
        WhatsApp sender ID.

    Returns
    -------
    str
        Response string to be sent back to WhatsApp user.
    """
    trace_id = trace_id or getattr(identity, "trace_id", "") or ""
    clean_text = (message_text or "").strip()

    # 1. Resolve ERP Context
    context = get_user_context(identity)

    # 2. Retrieve or create Active Conversation Session
    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id)
    update_conversation(conv, last_message_id=message_id)

    # 3. Handle Deterministic Global Commands
    cmd_lower = clean_text.lower()

    if cmd_lower == "cancel":
        cancel_conversation(conv)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="cancel",
            action="cancel_conversation",
            result="Conversation cancelled by user command",
            status="Success",
        )
        return build_cancellation_response(context)

    if cmd_lower in ("menu", "home", "back"):
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service=None,
        )
        menu_text, _ = build_menu(context)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="menu",
            action="display_menu",
            result=menu_text,
            status="Success",
        )
        return menu_text

    # 4. Process State Machine & Routing
    current_state = conv.current_state or ConversationState.NEW

    # NEW or MENU state → Show dynamic menu
    if current_state in (ConversationState.NEW, ConversationState.MENU):
        menu_text, _ = build_menu(context)
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="welcome",
            action="display_menu",
            result=menu_text,
            status="Success",
        )
        return menu_text

    # Try parsing menu selection (works from AWAITING_SELECTION or PROCESSING)
    selected_service = parse_menu_selection(clean_text, context)

    if selected_service:
        svc_key = selected_service["key"]

        # Authorization Gate Check
        auth_res = authorize(identity, context, service=svc_key)

        if auth_res.get("allowed"):
            update_conversation(
                conv,
                state=ConversationState.PROCESSING,
                current_intent=svc_key,
                active_service=svc_key,
            )

            if svc_key == "help":
                services = get_available_services_for_context(context)
                resp_text = build_help_response(context, services)
            else:
                resp_text = build_service_placeholder_response(svc_key, context)

            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=svc_key,
                service=svc_key,
                action="select_service",
                result=resp_text,
                status="Success",
            )
            return resp_text

        else:
            # Unauthorized access attempt
            _log_security_event(
                event_type="Unauthorized Service Access",
                severity="High",
                trace_id=trace_id,
                wa_id=conv.wa_id,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                description=f"Attempted unauthorized access to service: {svc_key}",
            )
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=svc_key,
                service=svc_key,
                action="unauthorized_access",
                result="Access denied",
                status="Blocked",
                error=auth_res.get("reason", "SERVICE_NOT_ALLOWED"),
            )
            unauth_msg = build_unauthorized_response(context)
            menu_msg, _ = build_menu(context)
            return f"{unauth_msg}\n\n{menu_msg}"

    # Invalid Selection
    _log_security_event(
        event_type="Invalid Menu Selection",
        severity="Low",
        trace_id=trace_id,
        wa_id=conv.wa_id,
        erp_user=conv.erp_user or "",
        employee=conv.employee or "",
        description=f"Unrecognized menu selection input: {clean_text!r}",
    )
    log_ai_action(
        trace_id=trace_id,
        conversation_name=conv.name,
        whatsapp_identity=conv.whatsapp_identity,
        erp_user=conv.erp_user or "",
        employee=conv.employee or "",
        intent="unknown",
        action="invalid_selection",
        result="Invalid selection prompt displayed",
        status="Failed",
    )
    return build_invalid_selection_message(context)


# ──────────────────────────────────────────────────────────────────────────────
# Logging Helpers
# ──────────────────────────────────────────────────────────────────────────────

def log_ai_action(
    *,
    trace_id: str,
    conversation_name: str,
    whatsapp_identity: str,
    erp_user: str = "",
    employee: str = "",
    intent: str = "",
    service: str = "",
    action: str = "",
    sources_records: str = "",
    result: str = "",
    status: str = "Success",
    error: str = "",
) -> None:
    """Create an AI Action Log record."""
    try:
        doc = frappe.new_doc("AI Action Log")
        doc.trace_id = trace_id
        doc.whatsapp_conversation = conversation_name
        doc.whatsapp_identity = whatsapp_identity
        doc.erp_user = erp_user
        doc.employee = employee
        doc.intent = intent
        doc.service = service
        doc.action = action
        doc.sources_records = sources_records
        doc.result = result
        doc.status = status
        doc.error = error
        doc.created_at = frappe.utils.now_datetime()
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"AI Workplace: Failed to log AI action: {exc}")


def _log_security_event(
    *,
    event_type: str,
    severity: str,
    trace_id: str = "",
    wa_id: str = "",
    phone_number: str = "",
    erp_user: str = "",
    employee: str = "",
    description: str = "",
) -> None:
    """Create an AI Security Event record."""
    try:
        doc = frappe.new_doc("AI Security Event")
        doc.event_type = event_type
        doc.severity = severity
        doc.whatsapp_id = wa_id
        doc.phone_number = phone_number
        doc.erp_user = erp_user
        doc.employee = employee
        doc.trace_id = trace_id
        doc.description = description
        doc.timestamp = frappe.utils.now_datetime()
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"AI Workplace: Failed to log security event: {exc}")
