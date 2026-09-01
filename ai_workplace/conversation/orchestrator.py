"""
ai_workplace/conversation/orchestrator.py
───────────────────────────────────────────
Conversation Orchestrator — Phase 2.
"""

from __future__ import annotations

from typing import Any, Optional, Union

import frappe
from frappe import _

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
from ai_workplace.services.response_helpers import (
    wrap_with_menu_again,
    wrap_monthly_attendance_summary,
    wrap_monthly_attendance_detail,
    wrap_salary_slip_period_options,
    wrap_bank_letter_options,
)
from ai_workplace.services.language import (
    parse_language_selection,
    persist_language,
    build_language_selection_message,
    build_language_saved_message,
)
from ai_workplace.response.builder import (
    build_cancellation_response,
    build_unauthorized_response,
    build_service_placeholder_response,
    build_help_response,
    build_unregistered_response,
    build_welcome_header,
)
from ai_workplace.whatsapp.interactive import build_show_menu_again_button
from ai_workplace.whatsapp.outbound import OutboundMessage

# Document menu aliases → canonical payroll/HR handlers
SERVICE_ALIASES: dict[str, str] = {
    "doc_salary_slip": "pay_download_slip",
    "doc_tax_cert": "pay_tax_deduction",
    "doc_experience_letter": "pay_experience_letter",
    "doc_bank_letter": "pay_bank_letter",
    "doc_my_requests": "prof_my_requests",
    "staff_hr_guidance": "pol_view_policies",
    "staff_supervisor": "supervisor_reporting",
    "staff_contact_hr": "contact_hr",
}


def _resolve_service_key(service_key: str) -> str:
    key = (service_key or "").strip().lower()
    return SERVICE_ALIASES.get(key, key)


def is_greeting_message(text: str) -> bool:
    """
    Check if user message is a greeting keyword or session restart command.
    """
    if not text:
        return False
    cleaned = text.strip().lower()
    for p in ["!", ".", ",", "?", "-", "_", ":", ";"]:
        cleaned = cleaned.replace(p, " ")
    cleaned = " ".join(cleaned.split())

    greetings_exact = {
        "hi",
        "hello",
        "hey",
        "heya",
        "hola",
        "salam",
        "salaam",
        "aoa",
        "assalam",
        "start",
        "restart",
        "reset",
    }
    greetings_phrases = {
        "assalam o alikum",
        "assalam o alaykum",
        "assalam o alaikum",
        "assalam alaikum",
        "assalamu alaikum",
        "assalamu alaykum",
        "assalam o aleikum",
    }

    if cleaned in greetings_exact or cleaned in greetings_phrases:
        return True

    tokens = cleaned.split()
    if tokens and tokens[0] in greetings_exact:
        return True

    for phrase in greetings_phrases:
        if cleaned.startswith(phrase):
            return True

    return False


def _download_bank_letter_outbound(conv, context, identity, trace_id, bank_name, service_key):
    """Generate bank letter PDF and return WhatsApp outbound message."""
    from ai_workplace.services.employee_letters import (
        build_letter_download_error,
        build_letter_download_outbound,
        generate_bank_letter_pdf,
    )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent="pay_bank_letter",
        active_service=None,
    )
    emp_id = context.get("employee") or ""
    try:
        pdf_bytes, filename = generate_bank_letter_pdf(emp_id, bank_name)
        caption = f"🏦 Your *Bank Letter* ({bank_name}) is attached."
        outbound = build_letter_download_outbound(context, pdf_bytes, filename, caption)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent=service_key,
            service="pay_bank_letter",
            action="download_bank_letter",
            result=outbound.log_text(),
            status="Success",
        )
        return outbound
    except Exception:
        err = build_letter_download_error(context, "Bank Letter")
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent=service_key,
            service="pay_bank_letter",
            action="download_bank_letter",
            result=err,
            status="Failed",
        )
        return wrap_with_menu_again(err, context)


def process_inbound_media(
    identity: Any,
    file_url: str,
    filename: str = "",
    message_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    wa_id: Optional[str] = None,
) -> Optional[OutboundMessage]:
    """
    Route inbound WhatsApp media to an active multi-step flow when applicable.
    Returns None when the media should be acknowledged without a bot reply.
    """
    if not (file_url or "").strip():
        return None

    context = get_user_context(identity)
    if not context.get("allowed_services"):
        return OutboundMessage(body_text=build_unregistered_response(context))

    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id or "")
    update_conversation(conv, last_message_id=message_id)

    if conv.preferred_language:
        context["preferred_language"] = conv.preferred_language

    current_state = conv.current_state or ConversationState.NEW
    if current_state == ConversationState.PROCESSING and conv.current_intent == "deliverable_add":
        from ai_workplace.services.deliverables import handle_deliverable_add_attachment

        return handle_deliverable_add_attachment(conv, context, file_url, filename=filename)

    if current_state == ConversationState.PROCESSING and (conv.current_intent or "").startswith("prof_"):
        from ai_workplace.services.profile_completion import handle_profile_flow_media

        return handle_profile_flow_media(conv, context, file_url, filename=filename)

    return OutboundMessage(
        body_text=_(
            "File received. To add a deliverable attachment, start *Add Deliverable* "
            "from the Deliverables menu first.\n\nType *menu* to open the main menu."
        )
    )


def process_inbound_media_failure(
    identity: Any,
    *,
    message_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    wa_id: Optional[str] = None,
    error: str = "",
) -> Optional[OutboundMessage]:
    """Notify the user when media could not be downloaded during an active profile flow."""
    import json

    context = get_user_context(identity)
    if not context.get("allowed_services"):
        return None

    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id or "")
    update_conversation(conv, last_message_id=message_id)

    if conv.preferred_language:
        context["preferred_language"] = conv.preferred_language

    intent = conv.current_intent or ""
    if (conv.current_state or "") != ConversationState.PROCESSING or not intent.startswith("prof_"):
        return None

    try:
        draft = json.loads(conv.draft_payload or "{}")
    except Exception:
        draft = {}

    step = draft.get("step", "")
    if step in ("front_scan", "back_scan", "scan", "start") and draft.get("flow") in (
        "prof_cnic_add",
        "prof_photo_upload",
        "prof_doc_upload",
        "prof_education_ticket",
        "prof_work_history_ticket",
    ):
        frappe.logger("ai_workplace").warning(
            f"Profile media upload failed at step {step} for {intent}: {error}"
        )
        return OutboundMessage(
            body_text=_(
                "We could not download your file. Please send the photo or document again "
                "as a direct attachment (not forwarded)."
            )
        )
    return None


def process_inbound_location(
    identity: Any,
    location: dict[str, Any],
    message_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    wa_id: Optional[str] = None,
    context_message_id: Optional[str] = None,
) -> Optional[OutboundMessage]:
    """Route inbound WhatsApp location to pending attendance flows."""
    from ai_workplace.services.attendance_location import process_inbound_location as _process

    context = get_user_context(identity)
    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id or "")
    outbound = _process(
        identity,
        location,
        message_id=message_id or "",
        trace_id=trace_id or "",
        wa_id=wa_id or "",
        context_message_id=context_message_id or "",
    )
    if outbound:
        log_ai_action(
            trace_id=trace_id or "",
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent=conv.current_intent or "att_location",
            service="attendance_location",
            action="process_location",
            result=outbound.log_text() if hasattr(outbound, "log_text") else str(outbound),
            status="Success",
        )
    return outbound


def process_message(
    message_text: str,
    identity: Any,
    message_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    wa_id: Optional[str] = None,
    skip_pin_check: bool = False,
) -> Union[OutboundMessage, str]:
    """
    Orchestrate incoming WhatsApp message through context, language, menu, and routing.
    Returns OutboundMessage (text or interactive).
    """
    trace_id = trace_id or getattr(identity, "trace_id", "") or ""
    clean_text = (message_text or "").strip()

    context = get_user_context(identity)

    if not context.get("allowed_services"):
        return OutboundMessage(body_text=build_unregistered_response(context))

    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id)
    update_conversation(conv, last_message_id=message_id)

    # Sync language from active conversation record
    if conv.preferred_language:
        context["preferred_language"] = conv.preferred_language

    cmd_lower = clean_text.lower()
    current_state = conv.current_state or ConversationState.NEW

    # ── Global: cancel ────────────────────────────────────────────────────────
    if cmd_lower == "cancel":
        if current_state == ConversationState.LIVE_HR_CHAT and conv.active_hr_chat_session:
            from ai_workplace.services.hr_chat import close_session

            close_session(conv.active_hr_chat_session, reset_conversation=False)
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
        return OutboundMessage(body_text=build_cancellation_response(context))

    # ── Contact HR prompt (wait / phone / email) ───────────────────────────────
    if current_state == ConversationState.HR_CONTACT_PROMPT:
        from ai_workplace.services.hr_contact_prompt import (
            handle_contact_hr_prompt_reply,
            is_contact_hr_menu_resubmit,
            build_contact_hr_options_message,
        )

        if cmd_lower in (
            "menu",
            "home",
            "back",
            "main menu",
            "main_menu",
            "cancel",
        ):
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                current_intent=None,
                active_service=None,
                draft_payload=None,
                clear_active_hr_chat_session=True,
            )
            menu_out, _unused = build_menu(context)
            return menu_out

        if is_contact_hr_menu_resubmit(clean_text):
            return build_contact_hr_options_message(context)

        return handle_contact_hr_prompt_reply(
            conv,
            clean_text,
            context,
            identity=identity,
            trace_id=trace_id,
            meta_message_id=message_id or "",
        )

    # ── Guest HR intake (public users: name → email → query) ─────────────────
    if current_state == ConversationState.HR_GUEST_INTAKE:
        from ai_workplace.services.hr_guest_intake import handle_guest_intake_message

        if cmd_lower in (
            "menu",
            "home",
            "back",
            "main menu",
            "main_menu",
            "cancel",
        ):
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                current_intent=None,
                active_service=None,
                draft_payload=None,
                clear_active_hr_chat_session=True,
            )
            menu_out, _unused = build_menu(context)
            return menu_out

        return handle_guest_intake_message(
            conv,
            clean_text,
            context,
            meta_message_id=message_id or "",
        )

    # ── Live HR chat routing ──────────────────────────────────────────────────
    if current_state == ConversationState.LIVE_HR_CHAT:
        from ai_workplace.services.hr_chat import close_session, handle_live_hr_inbound

        end_chat_commands = (
            "end chat",
            "end",
            "close chat",
            "close",
            "exit chat",
            "exit",
        )
        if cmd_lower in end_chat_commands:
            session_name = conv.active_hr_chat_session
            if session_name:
                close_session(session_name)
            menu_out, _unused = build_menu(context)
            menu_out.body_text = frappe._("Chat ended.\n\n") + menu_out.body_text
            return menu_out

        return handle_live_hr_inbound(
            conv,
            clean_text,
            meta_message_id=message_id or "",
            trace_id=trace_id,
        )

    # ── Support PIN verification ─────────────────────────────────────────────
    if current_state == ConversationState.WAITING_FOR_SUPPORT_PIN:
        from ai_workplace.security.pin_flow import (
            handle_waiting_for_pin,
            get_resume_service_key,
            clear_resume_service_key,
        )

        pin_out = handle_waiting_for_pin(conv, clean_text, context, wa_id=wa_id or "")
        if pin_out is not None:
            resume_key = get_resume_service_key(conv)
            if resume_key:
                clear_resume_service_key(conv)
                service_out = process_message(
                    f"svc_{resume_key}",
                    identity,
                    message_id=message_id,
                    trace_id=trace_id,
                    wa_id=wa_id,
                    skip_pin_check=True,
                )
                if isinstance(pin_out, OutboundMessage):
                    if isinstance(service_out, OutboundMessage):
                        pin_out.follow_up.append(service_out)
                    else:
                        pin_out.follow_up.append(OutboundMessage(body_text=str(service_out)))
                return pin_out
            return pin_out

    # ── PIN setup buttons (Open HRMIS Portal / I Have Set My PIN) ────────────
    from ai_workplace.security.pin_flow import handle_pin_setup_action

    pin_setup_out = handle_pin_setup_action(conv, clean_text, context)
    if pin_setup_out is not None:
        return pin_setup_out

    # ── Global: Greetings / Session Restart (hi, hello, assalam o alikum, etc.) ────
    if is_greeting_message(clean_text) or cmd_lower in ("restart", "reset", "start"):
        update_conversation(
            conv,
            state=ConversationState.AWAITING_LANGUAGE,
            clear_active_fields=True,
        )
        welcome_header = build_welcome_header(context)
        outbound = build_language_selection_message(context, welcome_text=welcome_header)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="greeting",
            action="restart_session_and_prompt_language",
            result=outbound.log_text(),
            status="Success",
        )
        return outbound


    # ── Global: explicit language change command ──────────────────────────────
    if cmd_lower in ("language", "change language", "lang", "zaban"):
        update_conversation(conv, state=ConversationState.AWAITING_LANGUAGE)
        outbound = build_language_selection_message(context)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="language",
            action="display_language_menu",
            result=outbound.log_text(),
            status="Success",
        )
        return outbound

    # ── Step 1: Language selection (first contact or AWAITING_LANGUAGE) ─────────
    if current_state == ConversationState.NEW:
        update_conversation(conv, state=ConversationState.AWAITING_LANGUAGE)
        welcome_header = build_welcome_header(context)
        outbound = build_language_selection_message(context, welcome_text=welcome_header)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="language",
            action="display_welcome_and_language_menu",
            result=outbound.log_text(),
            status="Success",
        )
        return outbound

    if current_state == ConversationState.AWAITING_LANGUAGE:
        selected_lang = parse_language_selection(clean_text)
        if selected_lang:
            persist_language(
                whatsapp_identity=conv.whatsapp_identity,
                language=selected_lang,
                conversation=conv,
            )
            context["preferred_language"] = selected_lang
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                preferred_language=selected_lang,
            )
            saved_note = build_language_saved_message(selected_lang, context)
            menu_out, _unused = build_menu(context, header_prefix=saved_note)

            from ai_workplace.services.proactive import maybe_send_proactive_nudge

            nudge = maybe_send_proactive_nudge(conv, context)
            if nudge:
                menu_out.follow_up.insert(0, nudge)

            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent="language",
                action="language_selected",
                result=menu_out.log_text(),
                status="Success",
            )
            return menu_out

        welcome_header = build_welcome_header(context)
        outbound = build_language_selection_message(context, welcome_text=welcome_header)
        return outbound


    # ── Step: Processing multi-step workflows ────────────────────────────────
    if current_state == ConversationState.PROCESSING and conv.current_intent == "leave_apply":
        from ai_workplace.services.leave_apply import handle_leave_apply_message

        return handle_leave_apply_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "concern_report":
        from ai_workplace.services.concern_report import handle_concern_report_message

        return handle_concern_report_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "deliverable_add":
        from ai_workplace.services.deliverables import handle_deliverable_add_message

        return handle_deliverable_add_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "deliverable_submit":
        from ai_workplace.services.deliverables import handle_deliverable_submit_message

        return handle_deliverable_submit_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "hr_ai_agent":
        from ai_workplace.services.hr_agent import handle_hr_agent_message

        return handle_hr_agent_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "trv_apply":
        from ai_workplace.services.travel import handle_travel_authorization_message

        return handle_travel_authorization_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent == "onboarding_agent":
        from ai_workplace.services.onboarding import handle_onboarding_message

        return handle_onboarding_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and conv.current_intent in (
        "att_checkin",
        "att_checkout",
        "att_exception",
    ):
        from ai_workplace.services.attendance_location import handle_attendance_flow_message

        return handle_attendance_flow_message(conv, clean_text, context)

    if current_state == ConversationState.PROCESSING and (conv.current_intent or "").startswith("prof_"):
        from ai_workplace.services.profile_completion import handle_profile_flow_message

        return handle_profile_flow_message(conv, clean_text, context)

    from ai_workplace.services.deliverables import (
        handle_submit_for_approval_request,
        is_submit_for_approval_trigger,
    )

    if is_submit_for_approval_trigger(clean_text):
        auth_res = authorize(identity, context, service="dlv_submit")
        if auth_res.get("allowed"):
            outbound = handle_submit_for_approval_request(conv, context)
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent="deliverables",
                service="deliverables",
                action="start_submit_deliverable",
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
        return OutboundMessage(body_text=build_unauthorized_response(context))

    if current_state == ConversationState.PROCESSING and conv.current_intent == "guest_number_changed":
        import json
        draft = {}
        if conv.draft_payload:
            try:
                draft = json.loads(conv.draft_payload)
            except Exception:
                draft = {}

        step = draft.get("step", "awaiting_emp_id")
        if step == "awaiting_emp_id":
            emp_id = clean_text.strip().upper()
            draft["emp_id"] = emp_id
            draft["step"] = "awaiting_cnic"
            update_conversation(
                conv,
                state=ConversationState.PROCESSING,
                draft_payload=json.dumps(draft),
            )
            return OutboundMessage(
                body_text=f"Thank you. You entered Employee ID *{emp_id}*.\n\nPlease enter the last 4 digits of your CNIC for identity verification:"
            )

        elif step == "awaiting_cnic":
            emp_id = draft.get("emp_id", "EMP-UNKNOWN")
            cnic_last4 = clean_text.strip()
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                current_intent=None,
                active_service=None,
                draft_payload=None,
            )
            res_msg = (
                f"✅ *Request Submitted Successfully*\n\n"
                f"Your request to update the registered WhatsApp number for Employee ID *{emp_id}* "
                f"(CNIC Ending: {cnic_last4}) has been received and routed to HR for verification.\n\n"
                f"🔒 HR will verify your records and contact you shortly.\n\n"
                f"Type 'menu' to return to the main menu."
            )
            return OutboundMessage(body_text=res_msg)

    # ── Global: return to main menu ───────────────────────────────────────────
    if cmd_lower in (
        "menu",
        "home",
        "back",
        "main menu",
        "main_menu",
        "svc_menu",
        "svc_back",
        "svc_main_menu",
        "0",
        "svc_0",
        "back to main menu",
        "اصلی مینو",
        "🔙 main menu",
        "🔙 اصلی مینو",
    ) or clean_text.lower() in ("svc_main_menu", "main_menu"):
        if current_state == ConversationState.LIVE_HR_CHAT and conv.active_hr_chat_session:
            from ai_workplace.services.hr_chat import close_session

            close_session(conv.active_hr_chat_session)
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service=None,
        )
        menu_out, _unused = build_menu(context)
        log_ai_action(
            trace_id=trace_id,
            conversation_name=conv.name,
            whatsapp_identity=conv.whatsapp_identity,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            intent="menu",
            action="display_menu",
            result=menu_out.log_text(),
            status="Success",
        )
        return menu_out

    # ── Step 2: Service selection from clickable menu or active submenu ───────
    active_parent = conv.active_service
    selected_service = None
    if active_parent:
        selected_service = parse_menu_selection(clean_text, context, parent_key=active_parent)

    if not selected_service:
        selected_service = parse_menu_selection(clean_text, context)

    if not selected_service and clean_text.lower().startswith("svc_dlv_"):
        selected_service = {"key": clean_text[4:].lower(), "title": clean_text[4:]}

    if not selected_service and clean_text.lower().startswith("dlv_pick_"):
        if (conv.current_state or "") == ConversationState.PROCESSING and conv.current_intent == "deliverable_submit":
            from ai_workplace.services.deliverables import handle_deliverable_submit_message

            return handle_deliverable_submit_message(conv, clean_text, context)
        selected_service = {"key": clean_text.lower(), "title": clean_text}

    if not selected_service and clean_text.startswith("svc_att_"):
        svc_key = clean_text[4:]
        selected_service = {"key": svc_key, "title": svc_key}

    if not selected_service and clean_text.startswith("att_exc_"):
        selected_service = {"key": clean_text, "title": clean_text}

    if not selected_service and clean_text.startswith("svc_gap_"):
        gap_key = clean_text[8:]
        selected_service = {"key": f"gap_{gap_key}", "title": gap_key}

    if not selected_service and clean_text.startswith("svc_prof_"):
        svc_key = clean_text[4:]
        selected_service = {"key": svc_key, "title": svc_key}

    if not selected_service and clean_text.startswith("pol_sel_"):
        selected_service = {"key": clean_text, "title": clean_text}

    if not selected_service and clean_text.startswith("svc_pay_"):
        svc_key = clean_text[4:]
        selected_service = {"key": svc_key, "title": svc_key}

    if not selected_service and clean_text.startswith("svc_"):
        svc_key = clean_text[4:].lower()
        selected_service = {"key": svc_key, "title": svc_key}

    if not selected_service and len(clean_text) >= 3 and not clean_text.isdigit():
        from ai_workplace.services.keyword_router import match_keyword_service

        kw_service = match_keyword_service(clean_text)
        if kw_service:
            selected_service = {"key": kw_service, "title": kw_service}

    if selected_service:
        svc_key = _resolve_service_key(selected_service["key"])
        if svc_key in ("main_menu", "back_to_main", "menu"):
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                current_intent=None,
                active_service=None,
            )
            menu_out, _unused = build_menu(context)
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent="menu",
                action="display_menu",
                result=menu_out.log_text(),
                status="Success",
            )
            return menu_out

        auth_res = authorize(identity, context, service=svc_key)

        if auth_res.get("allowed"):
            if not skip_pin_check:
                from ai_workplace.security.pin_flow import maybe_gate_service

                pin_gate = maybe_gate_service(conv, context, svc_key)
                if pin_gate:
                    log_ai_action(
                        trace_id=trace_id,
                        conversation_name=conv.name,
                        whatsapp_identity=conv.whatsapp_identity,
                        erp_user=conv.erp_user or "",
                        employee=conv.employee or "",
                        intent=svc_key,
                        service=svc_key,
                        action="pin_gate",
                        result=pin_gate.log_text(),
                        status="Success",
                    )
                    return pin_gate


            from ai_workplace.conversation.handlers import register_all_handlers
            from ai_workplace.conversation.router import ServiceRegistry
            
            # Ensure handlers are registered
            if not ServiceRegistry._handlers:
                register_all_handlers()
                
            outbound = ServiceRegistry.dispatch(conv, svc_key, clean_text, context, trace_id)
            if outbound:
                return outbound

            # Now, attempt to dynamically render submenu if it has children
            from ai_workplace.services.registry import get_available_services_for_context
            children = get_available_services_for_context(context, parent_key=svc_key)
            if children:
                update_conversation(
                    conv,
                    state=ConversationState.AWAITING_SELECTION,
                    current_intent=None,
                    active_service=svc_key,
                )
                menu_out, _unused = build_menu(context, parent_key=svc_key)
                log_ai_action(
                    trace_id=trace_id,
                    conversation_name=conv.name,
                    whatsapp_identity=conv.whatsapp_identity,
                    erp_user=conv.erp_user or "",
                    employee=conv.employee or "",
                    intent=svc_key,
                    action="display_submenu",
                    result=menu_out.log_text(),
                    status="Success",
                )
                return menu_out

            
            # Standard leaf service execution/placeholder
            update_conversation(
                conv,
                state=ConversationState.AWAITING_SELECTION,
                current_intent=svc_key,
                active_service=None,
            )
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
            return wrap_with_menu_again(resp_text, context)

        _log_security_event(
            event_type="Unauthorized Service Access",
            severity="High",
            trace_id=trace_id,
            wa_id=conv.wa_id,
            erp_user=conv.erp_user or "",
            employee=conv.employee or "",
            description=f"Attempted unauthorized access to service: {svc_key}",
        )
        unauth_msg = build_unauthorized_response(context)
        menu_out, _unused = build_menu(context)
        menu_out.body_text = f"{unauth_msg}\n\n{menu_out.body_text}"
        return menu_out


    # ── AI Feedback Button Handlers ──────────────────────────────────────────
    if clean_text in ("fb_helpful", "👍 helpful"):
        try:
            doc = frappe.new_doc("AI Feedback Log")
            doc.feedback_type = "HELPFUL"
            doc.query = "Interactive Feedback"
            doc.employee = context.get("employee")
            doc.user = context.get("user")
            doc.whatsapp_identity = conv.whatsapp_identity
            doc.insert(ignore_permissions=True)
        except Exception:
            pass
        return OutboundMessage(
            body_text="Thank you for your feedback! 😊\n\nIs there anything else I can help you with today? Feel free to ask another question or type *menu*."
        )

    if clean_text in ("fb_not_helpful", "👎 not helpful"):
        try:
            doc = frappe.new_doc("AI Feedback Log")
            doc.feedback_type = "NOT_HELPFUL"
            doc.feedback_reason = "IRRELEVANT"
            doc.query = "Interactive Negative Feedback"
            doc.employee = context.get("employee")
            doc.user = context.get("user")
            doc.whatsapp_identity = conv.whatsapp_identity
            doc.insert(ignore_permissions=True)
        except Exception:
            pass
        return OutboundMessage(
            body_text="Thank you for your feedback! An HR representative will review this topic to improve our responses.\n\nIs there anything else I can help you with today? Feel free to ask another question or type *menu*."
        )

    # =========================================================================
    # PHASE 5: DETERMINISTIC QUERY RESOLVER -> HYBRID RAG -> LLM FALLBACK
    # =========================================================================
    if not clean_text.isdigit() and len(clean_text) >= 3:
        from ai_workplace.ai.query_resolver import QueryResolver
        from ai_workplace.ai.response_formatter import ResponseFormatter
        from ai_workplace.ai.tools import run_tool
        
        intent_key, meta, confidence = QueryResolver.resolve(clean_text)
        
        if intent_key and intent_key != "unknown" and meta:
            # Check permissions
            if meta.get("requires_authentication") and not context.get("employee"):
                return OutboundMessage(body_text="You must be an authenticated employee to access this feature.")
                
            tool_name = meta.get("tool")
            response_mode = meta.get("response_mode", "deterministic")
            
            # Tier 0: Zero AI (Deterministic ERP)
            if response_mode == "deterministic" and tool_name:
                raw_data = run_tool(tool_name, context)
                formatted_response = ResponseFormatter.format_response(intent_key, raw_data)
                
                log_ai_action(
                    trace_id=trace_id,
                    conversation_name=conv.name,
                    whatsapp_identity=conv.whatsapp_identity,
                    intent=intent_key,
                    action=f"run_deterministic_{tool_name}",
                    result=formatted_response,
                    status="Success",
                )
                return OutboundMessage(body_text=formatted_response)
                
            # Tier 1/2: Hybrid RAG or LLM Synthesis
            elif response_mode == "hybrid" or meta.get("llm_allowed", False):
                # Call HR Agent to handle it natively with LLM + Tools
                from ai_workplace.services.hr_agent import handle_hr_agent_message
                update_conversation(conv, state=ConversationState.PROCESSING, current_intent="hr_ai_agent")
                return handle_hr_agent_message(conv, clean_text, context)
                
            # Navigation / Clarification
            elif response_mode == "clarification":
                return OutboundMessage(
                    body_text="Sure. What would you like to see?\n\n1️⃣ Leave balance\n2️⃣ Leave history\n3️⃣ Leave applications\n4️⃣ Leave policy"
                )
                
            # Escalation
            elif response_mode == "escalate":
                return OutboundMessage(
                    body_text=ResponseFormatter.format_generic_error()
                )
        
        # If no deterministic intent matched, use LLM as final fallback (if enabled)
        from ai_workplace.ai.router import is_ai_chat_enabled
        if is_ai_chat_enabled():
            from ai_workplace.services.hr_agent import handle_hr_agent_message
            update_conversation(conv, state=ConversationState.PROCESSING, current_intent="hr_ai_agent")
            return handle_hr_agent_message(conv, clean_text, context)
        
        # If LLM disabled, fallback to menu
        lang = context.get("preferred_language", "English")
        if lang == "Urdu":
            hint = "براہ کرم نیچے سے سروس منتخب کریں۔ آپ \"تنخواہ\"، \"رخصت\"، \"حاضری\"، \"سفر\" یا \"HR\" بھی لکھ سکتے ہیں۔"
        elif lang == "Roman Urdu":
            hint = "Neeche se service choose karein. Aap \"salary slip\", \"leave\", \"attendance\", \"travel\" ya \"HR\" bhi likh sakte hain."
        else:
            hint = "Choose a service below. You can also type common requests such as \"salary slip\", \"leave\", \"attendance\", \"travel\" or \"HR\"."
        menu_out, _unused = build_menu(context, header_prefix=hint)
        return menu_out

    # ── Invalid selection → refresh clickable menu ────────────────────────────
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
