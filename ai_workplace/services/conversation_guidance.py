"""Persistent guided policy conversations and optional unfinished-task catch-ups.

Guidance data is separate from workflow drafts. Catch-ups are claimed durably
before network I/O; uncertain deliveries are never automatically retried.
"""
from __future__ import annotations

import json
from datetime import timedelta

import frappe

from ai_workplace.conversation_guidance import (
    LEAVE_QUESTIONS, COMPANY_QUESTIONS, COMPANY_SERVICE_QUESTIONS, is_company_question, copy_for, eligible, load_memory, quiet_now,
)
from ai_workplace.whatsapp.outbound import OutboundMessage


def available(conv):
    return bool(conv.meta.has_field("guidance_memory"))


def settings():
    return frappe.get_single("AI Workplace Settings")


def _save(conv, memory, **extra):
    values = {"guidance_memory": json.dumps(memory, ensure_ascii=False), **extra}
    conv.db_set(values, update_modified=False)
    for key, value in values.items():
        setattr(conv, key, value)


def begin_turn(conv, text, context, *, human_owned=False):
    """Cancel stale delivery before routing; handle only our explicit controls."""
    if not available(conv):
        return text, None
    memory = load_memory(conv.get("guidance_memory"))
    copy = copy_for(context.get("preferred_language"))
    now = frappe.utils.now_datetime()
    command = text.strip().lower()
    if memory and (memory.get("employee") != context.get("employee") or memory.get("user") != (context.get("user") or conv.get("erp_user"))):
        memory = {}
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
    if conv.get("followup_status") in {"Pending", "Claimed"}:
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
    from ai_workplace.services.conversation_engagement import (event, reminders_allowed, save_preference, preference, task_control, pause_task, detach)
    if command.startswith('quiet hours '):
        parts = text.split()
        user = context.get('user') or conv.get('erp_user')
        try:
            start, end = int(parts[2]), int(parts[3])
        except (ValueError, IndexError):
            return text, OutboundMessage(body_text='Use “quiet hours 20 9 Asia/Karachi”, with hours from 0 to 23.')
        current = preference(user)
        save_preference(user, current is None or bool(current.get('reminders_enabled')), start, end, parts[4] if len(parts)>4 else None)
        return text, OutboundMessage(body_text='Your account quiet hours have been updated.')
    if command in {"stop reminders", "no reminders", "start reminders", "enable reminders", "reminder settings"}:
        user = context.get("user") or conv.get("erp_user")
        if not user or user == "Guest":
            return text, OutboundMessage(body_text="Sign in to change account reminder preferences.")
        from ai_workplace.services.conversation_engagement import installed
        if not installed('AI Conversation Preference'):
            return text, OutboundMessage(body_text='Account reminder settings will be available after the site migration.')
        current = preference(user)
        if command == "reminder settings":
            enabled = current is None or bool(current.get("reminders_enabled"))
            return text, OutboundMessage(body_text=f"Account reminders: {'on' if enabled else 'off'}. Type ‘stop reminders’ or ‘start reminders’ to change this. Set quiet hours by sending ‘quiet hours 20 9 Asia/Karachi’.")
        enabled = command in {"start reminders", "enable reminders"}
        save_preference(user, enabled, (current or {}).get("quiet_start", 20), (current or {}).get("quiet_end", 9), (current or {}).get("timezone"))
        memory['opted_out'] = not enabled
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
        event(conv, 'preference_changed')
        return text, OutboundMessage(body_text="Account reminders enabled. Site settings still apply." if enabled else "Account reminders disabled across all your conversations.")
    if command in {"guide_dismiss"}:
        event(conv, 'dismissed', memory.get('topic', ''), memory.get('intent', ''))
        memory.update(status="dismissed", opted_out=True)
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
        return text, OutboundMessage(body_text=copy["dismissed"])
    if not settings().get("guided_conversations_enabled"):
        return text, None
    # Human-owned and security flows always retain priority.
    if human_owned or conv.get("active_hr_chat_session") or conv.get("current_state") in {
        "LIVE_HR_CHAT", "WAITING_FOR_SUPPORT_PIN", "NEW", "AWAITING_LANGUAGE",
    }:
        memory["status"] = "suspended"
        _save(conv, memory)
        return text, None
    handled, response = task_control(conv, context, text)
    if handled:
        return text, response
    # Pause a transactional draft only for an explicit, recognized topic change.
    from ai_workplace.advanced_conversation import RESUMABLE_WORKFLOWS
    import re
    if conv.get('current_intent') in RESUMABLE_WORKFLOWS and re.match(r"^(?:what|how|when|where|show|tell|apply|request|i want|svc_)", command):
        from ai_workplace.ai.query_resolver import QueryResolver
        new_intent, meta, confidence = QueryResolver.resolve(text)
        if new_intent and new_intent != 'unknown' and meta and confidence >= 0.75 and meta.get('workflow_intent') != conv.get('current_intent'):
            if pause_task(conv, context):
                detach(conv)
                saved = load_memory(conv.get('guidance_memory'))
                saved['paused_notice'] = 'Your unfinished task is saved. Type “my tasks” when you want to resume it.'
                _save(conv, saved)
                event(conv, 'reply', memory.get('topic', ''), memory.get('intent', ''))
                return text, None
    if memory.get('status') == 'awaiting_user':
        event(conv, 'reply', memory.get('topic', ''), memory.get('intent', ''))
    if command == "guide_later":
        cfg = settings()
        if memory.get("status") != "awaiting_user" or memory.get("opted_out"):
            return text, OutboundMessage(body_text="There is no unfinished conversation to remind you about.")
        if not cfg.get("conversation_followups_enabled") or not _whatsapp(conv) or not reminders_allowed(context.get('user') or conv.get('erp_user')):
            return text, OutboundMessage(body_text="Scheduled reminders are not enabled for this channel.")
        # An explicit request permits one more reminder; passive replies do not.
        memory.update(reminder_sent=False, last_inbound_at=now.isoformat())
        _schedule(conv, memory, cfg, now)
        return text, OutboundMessage(body_text=copy["later_ack"])
    if memory.get("status") != "awaiting_user":
        return text, None
    if command in {"no", "no thanks", "thanks", "thank you", "done", "نہیں", "shukriya"}:
        # Do not consume a leave confirmation: its existing transaction flow owns it.
        if conv.get("current_intent") not in {'leave_apply','att_request_apply','trv_apply','trv_problem'}:
            event(conv, 'completed', memory.get('topic', ''), memory.get('intent', ''))
            memory["status"] = "completed"
            _save(conv, memory)
            return text, OutboundMessage(body_text=copy["dismissed"])
    if memory.get('related_intent') and command in {'yes', 'guide_continue', 'continue'}:
        from ai_workplace.ai.intent_catalog import INTENT_CATALOG
        target = INTENT_CATALOG.get(memory['related_intent'])
        if target and target.get('aliases'):
            return target['aliases'][0], None
    if command in {"guide_continue", "continue", "yes", "ہاں", "haan"}:
        if memory.get("topic") == "leave application":
            # Leave confirmations retain ownership of Yes/No responses.
            if command not in {"guide_continue", "continue"}:
                return text, None
            return text, OutboundMessage(body_text=memory.get("question") or LEAVE_QUESTIONS["awaiting_confirm"])
        if conv.get('current_intent') in {'att_request_apply','trv_apply','trv_problem'}:
            if command not in {'guide_continue','continue'}:
                return text, None
            return text, OutboundMessage(body_text=memory.get('question') or 'Please continue the next step of your request.')
        if "leave" in memory.get("intent", ""):
            from ai_workplace.whatsapp.interactive import build_button_message
            return text, build_button_message(copy["leave_policy"], [
                {"id": "svc_leave_balance", "title": "Leave Balance"},
                {"id": "svc_leave_apply", "title": "Apply for Leave"},
                {"id": "guide_dismiss", "title": copy["dismiss"]},
            ])
        return text, OutboundMessage(body_text=memory.get("question") or copy["policy"])
    if command in (memory.get('options') or {}):
        return memory['options'][command], None
    if memory.get("topic") == "company information":
        company_reply = {
            "services": "What services does MicroMerger provide?",
            "خدمات": "What services does MicroMerger provide?",
            "سروسز": "What services does MicroMerger provide?",
            "ملازمت کے مواقع": "Show me career opportunities at MicroMerger.",
            "کمپنی کا پس منظر": "Tell me about MicroMerger's company background.",
            "service": "What services does MicroMerger provide?",
            "company background": "Tell me about MicroMerger's company background.",
            "background": "Tell me about MicroMerger's history and background.",
            "career opportunities": "Show me career opportunities at MicroMerger.",
            "careers": "Show me career opportunities at MicroMerger.",
            "jobs": "Show me career opportunities at MicroMerger.",
            "history": "Tell me about MicroMerger's history.",
            "erp": "Tell me about MicroMerger's ERP services.",
            "software development": "Tell me about MicroMerger's software development services.",
            "bpo": "Tell me about MicroMerger's BPO services.",
            "ai": "Tell me about MicroMerger's AI services.",
        }.get(command)
        if not company_reply and command not in {'menu','back','cancel'}:
            pause_task(conv, context)
        memory["status"] = "suspended"
        _save(conv, memory)
        return company_reply or text, None
    if memory.get("topic") == "policy guidance":
        # Short answers to our question inherit the policy topic. Explicit new
        # intents still route normally, and service/button IDs are never rewritten.
        from ai_workplace.ai.query_resolver import QueryResolver
        intent, _, _ = QueryResolver.resolve(text)
        if (not intent or intent == "unknown") and not command.startswith(("svc_", "btn_", "guide_")) and command not in {"menu", "back", "cancel", "stop", "home"}:
            text = f"Regarding {memory.get('intent', 'HR policy').replace('_', ' ')}: {text}"
        else:
            if command not in {'menu','back','cancel'}:
                pause_task(conv, context)
            memory["status"] = "suspended"
            _save(conv, memory)
    return text, None


def _whatsapp(conv):
    return bool(conv.get("wa_id")) and not conv.get("wa_id").startswith("WEB-")


def _schedule(conv, memory, cfg, now):
    from ai_workplace.services.conversation_engagement import reminders_allowed, event
    if not cfg.get("conversation_followups_enabled") or not _whatsapp(conv) or memory.get("opted_out") or memory.get("reminder_sent") or not reminders_allowed(conv.get('erp_user')):
        _save(conv, memory)
        return
    delay = max(5, min(int(cfg.get("conversation_followup_minutes") or 60), 12 * 60))
    due = now + timedelta(minutes=delay)
    memory["due_at"] = due.isoformat()
    # Preserve an unfinished draft beyond the default 60-minute session TTL.
    expires = max(frappe.utils.get_datetime(conv.expires_at) if conv.expires_at else now, due + timedelta(hours=12))
    _save(conv, memory, followup_status="Pending", followup_due_at=due, expires_at=expires)
    event(conv, 'reminder_scheduled', memory.get('topic', ''), memory.get('intent', ''))


def finish_turn(conv, context, outbound):
    """Capture existing deterministic leave progress without changing its rules."""
    if not available(conv) or not isinstance(outbound, OutboundMessage) or outbound.skip_send:
        return outbound
    memory = load_memory(conv.get("guidance_memory"))
    if not settings().get("guided_conversations_enabled"):
        return outbound
    if conv.get("current_intent") == "leave_apply" and conv.get("current_state") == "PROCESSING":
        draft = load_memory(conv.get("draft_payload"))
        step = draft.get("step")
        if step in LEAVE_QUESTIONS:
            now = frappe.utils.now_datetime()
            # Only approved workflow values are remembered; never duplicate full
            # message history, free-text reasons, medical information, or PINs.
            details = {k: draft[k] for k in ("leave_type", "from_date", "to_date", "half_day") if k in draft}
            memory.update(topic="leave application", status="awaiting_user", step=step,
                          details=details, question=LEAVE_QUESTIONS[step],
                          employee=context.get("employee"), user=context.get("user") or conv.get("erp_user"),
                          last_inbound_at=now.isoformat())
            _schedule(conv, memory, settings(), now)
            from ai_workplace.services.conversation_engagement import event
            event(conv, 'question', 'leave application', 'leave_apply')
    elif conv.get('current_intent') in {'att_request_apply','trv_apply','trv_problem'} and conv.get('current_state') == 'PROCESSING':
        from ai_workplace.advanced_conversation import RESUMABLE_WORKFLOWS
        from ai_workplace.services.conversation_engagement import event
        draft = load_memory(conv.get('draft_payload'))
        intent = conv.get('current_intent')
        now = frappe.utils.now_datetime()
        memory.update(topic=RESUMABLE_WORKFLOWS[intent][0], intent=intent, step=draft.get('step'), status='awaiting_user',
                      question='Continue the next step of your '+RESUMABLE_WORKFLOWS[intent][0]+'.',
                      employee=context.get('employee'), user=context.get('user') or conv.get('erp_user'), last_inbound_at=now.isoformat())
        _schedule(conv,memory,settings(),now)
        event(conv,'question',memory['topic'],intent)
    elif memory.get("topic") == "leave application":
        memory["status"] = "completed"
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
    elif memory.get("status") == "suspended":
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
    latest = load_memory(conv.get('guidance_memory'))
    if latest.pop('paused_notice', None):
        notice = 'Your unfinished task is saved. Type “my tasks” to resume it.'
        outbound.body_text += '\n\n' + notice
        if outbound.interactive and isinstance(outbound.interactive.get('body'), dict):
            outbound.interactive['body']['text'] = outbound.body_text
        _save(conv, latest)
    return outbound


def guide_policy(conv, context, outbound, intent_key, raw_data, user_query=""):
    """Offer a policy/company next step only when retrieval supplied content."""
    enabled = settings().get("guided_conversations_enabled")
    if not conv or (enabled is not None and not int(enabled)):
        return outbound
    can_persist = available(conv)
    if not isinstance(raw_data, (dict, list)) or not raw_data:
        return outbound
    if isinstance(raw_data, dict) and (raw_data.get("error") or raw_data.get("status") == "error" or raw_data.get("has_leave_policy") is False or raw_data.get("has_expense_structure") is False):
        return outbound
    if isinstance(raw_data, list) and not any(isinstance(row, dict) and (row.get("text") or row.get("content")) for row in raw_data):
        return outbound
    company = is_company_question(user_query)
    if not company and "policy" not in intent_key and "carry_forward" not in intent_key and intent_key != 'search_knowledge':
        return outbound
    memory = load_memory(conv.get("guidance_memory")) if can_persist else {}
    if memory.get("opted_out"):
        return outbound
    copy = copy_for(context.get("preferred_language"))
    language = context.get("preferred_language", "English")
    company_questions = COMPANY_SERVICE_QUESTIONS if "service" in user_query.lower() else COMPANY_QUESTIONS
    question = company_questions.get(language, company_questions["English"]) if company else (copy["leave_policy"] if "leave" in intent_key else copy["policy"])
    # Approved retrieval metadata may supply a more relevant clarification.
    from ai_workplace.conversation_guidance import load_memory as parse_questions
    rows = raw_data if isinstance(raw_data, list) else [raw_data]
    related = None
    for row in rows:
        metadata_questions = parse_questions(row.get('guided_questions')) if isinstance(row, dict) else {}
        candidate = metadata_questions.get(language) or metadata_questions.get('English')
        if isinstance(candidate, str) and candidate.strip():
            question = candidate.strip()[:500]
            related = row.get('related_intent')
            break
    # Do not tack on a second question when synthesis already asked one.
    if "?" not in outbound.body_text and "؟" not in outbound.body_text:
        outbound.body_text += "\n\n" + question
        if outbound.interactive and isinstance(outbound.interactive.get("body"), dict):
            outbound.interactive["body"]["text"] = outbound.body_text
    outbound.follow_up = []
    if not can_persist:
        # Display guidance during rolling deployments; durable resume/reminders
        # still require the migrated fields. Never schedule without persistence.
        return outbound
    now = frappe.utils.now_datetime()
    memory.update(topic="company information" if company else "policy guidance", intent=intent_key, related_intent=related, status="awaiting_user",
                  question=question, employee=context.get("employee"),
                  user=context.get("user") or conv.get("erp_user"), last_inbound_at=now.isoformat())
    _schedule(conv, memory, settings(), now)
    from ai_workplace.services.conversation_engagement import event
    event(conv, 'question', memory.get('topic', ''), intent_key)
    return outbound


def send_due_followups():
    """Claim before sending, with row locks and eligibility checked at delivery."""
    cfg = settings()
    if not cfg.get("guided_conversations_enabled") or not cfg.get("conversation_followups_enabled"):
        return
    now = frappe.utils.now_datetime()
    start = int(cfg.get("followup_quiet_start") if cfg.get("followup_quiet_start") is not None else 20) % 24
    end = int(cfg.get("followup_quiet_end") if cfg.get("followup_quiet_end") is not None else 9) % 24
    if quiet_now(now, start, end):
        return
    rows = frappe.get_all("WhatsApp Conversation", filters={"followup_status": "Pending", "followup_due_at": ["<=", now]}, pluck="name", limit_page_length=100)
    for name in rows:
        try:
            _send_one(name, cfg)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Conversation follow-up failed", message=frappe.get_traceback())


def _send_one(name, cfg):
    # Locking prevents concurrent scheduler workers from delivering twice.
    frappe.db.sql("SELECT name FROM `tabWhatsApp Conversation` WHERE name=%s FOR UPDATE", (name,))
    conv = frappe.get_doc("WhatsApp Conversation", name)
    if conv.get("followup_status") != "Pending":
        frappe.db.commit()
        return
    memory = load_memory(conv.get("guidance_memory"))
    now = frappe.utils.now_datetime()
    from ai_workplace.services.conversation_engagement import reminders_allowed, preference, event
    from zoneinfo import ZoneInfo
    allowed = eligible(conv, memory, now) and _whatsapp(conv) and reminders_allowed(conv.get('erp_user'))
    pref = preference(conv.get('erp_user'))
    if allowed and pref:
        local_now = now.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone())).astimezone(ZoneInfo(pref.get('timezone') or frappe.utils.get_system_timezone()))
        if quiet_now(local_now, int(pref.get('quiet_start') or 0), int(pref.get('quiet_end') or 0)):
            frappe.db.commit()
            return
    # An employee reassignment, disabled user, or active human session revokes delivery.
    if allowed:
        identity = frappe.db.get_value("WhatsApp Identity", conv.whatsapp_identity, ["status", "employee", "erp_user", "normalized_phone"], as_dict=True)
        allowed = bool(identity and identity.status == "Active" and identity.employee == conv.employee and identity.erp_user == conv.erp_user and identity.normalized_phone.lstrip("+") == conv.wa_id.lstrip("+"))
        employee = frappe.db.get_value("Employee", conv.employee, ["status", "user_id"], as_dict=True)
        allowed = allowed and bool(employee and employee.status == "Active" and employee.user_id == conv.erp_user and frappe.db.get_value("User", conv.erp_user, "enabled"))
        from ai_workplace.services.hr_chat import get_active_session_for_identity
        allowed = allowed and not get_active_session_for_identity(whatsapp_identity=conv.whatsapp_identity, employee=conv.employee, wa_id=conv.wa_id)
    if not allowed:
        _save(conv, memory, followup_status="Cancelled", followup_due_at=None)
        frappe.db.commit()
        return
    memory["reminder_sent"] = True
    _save(conv, memory, followup_status="Claimed", followup_due_at=None)
    frappe.db.commit()
    # Recheck immediately before network I/O in case inbound handling cancelled it.
    if frappe.db.get_value("WhatsApp Conversation", name, "followup_status") != "Claimed":
        return
    from ai_workplace.whatsapp.interactive import build_button_message
    from ai_workplace.whatsapp.sender import send_message
    copy = copy_for(conv.preferred_language)
    topic = {"Urdu": "آپ کے نامکمل HR سوال", "Roman Urdu": "aap ke adhooray HR sawal"}.get(conv.preferred_language, memory["topic"])
    outbound = build_button_message(copy["catchup"].format(topic=topic), [
        {"id": "guide_continue", "title": copy["continue"]},
        {"id": "guide_later", "title": copy["later"]},
        {"id": "guide_dismiss", "title": copy["dismiss"]},
    ])
    receiver = frappe.db.get_value("WhatsApp Identity", conv.whatsapp_identity, "receiver_name")
    result = send_message(conv.wa_id, outbound, settings=cfg, receiver_name=receiver, session_name=receiver)
    event(conv, 'reminder_sent' if result.get('success') else 'reminder_failed', memory.get('topic', ''), memory.get('intent', ''))
    from ai_workplace.api.whatsapp_webhook import _create_message_log
    _create_message_log(meta_message_id=result.get("message_id") or "", direction="Outbound",
                        sender=cfg.get("whatsapp_phone_number_id") or "", recipient=conv.wa_id,
                        wa_id=conv.wa_id, message_type=outbound.message_type, message=outbound.log_text(),
                        erp_user=conv.erp_user, employee=conv.employee,
                        status="Sent" if result.get("success") else "Failed",
                        trace_id=conv.get("trace_id") or "", error=result.get("error") or "")
    # Never overwrite a newer inbound turn's cancellation or new reminder.
    frappe.db.sql("UPDATE `tabWhatsApp Conversation` SET followup_status=%s WHERE name=%s AND followup_status='Claimed'", ("Sent" if result.get("success") else "Failed", name))
    frappe.db.commit()


def guide_answer(conv, context, outbound, intent_key, raw_data, user_query=''):
    """Consistent guidance for supported read services; no invented business data."""
    from ai_workplace.conversation_guidance import guidance_category, SERVICE_GUIDANCE
    from ai_workplace.services.conversation_engagement import event
    if not isinstance(outbound, OutboundMessage) or outbound.skip_send or outbound.has_document():
        return outbound
    if not raw_data or isinstance(raw_data, dict) and (raw_data.get('error') or raw_data.get('status') == 'error'):
        event(conv,'knowledge_gap',intent=intent_key)
        return outbound
    # Knowledge answers retain their approved, source-driven guidance.
    if is_company_question(user_query) or 'policy' in intent_key or intent_key == 'search_knowledge' or 'carry_forward' in intent_key:
        return guide_policy(conv, context, outbound, intent_key, raw_data, user_query)
    enabled = settings().get('guided_conversations_enabled')
    if enabled is not None and not int(enabled):
        return outbound
    if conv.get('current_state') in {'PROCESSING','CONFIRMATION','WAITING_FOR_SUPPORT_PIN','LIVE_HR_CHAT'} or conv.get('active_hr_chat_session'):
        return outbound
    category = guidance_category(intent_key, user_query)
    if not category:
        return outbound
    topic, questions, options = SERVICE_GUIDANCE[category]
    memory = load_memory(conv.get('guidance_memory')) if available(conv) else {}
    if memory.get('opted_out'):
        return outbound
    question = questions.get(context.get('preferred_language'), questions['English'])
    if '?' not in outbound.body_text and '؟' not in outbound.body_text:
        outbound.body_text += '\n\n'+question
        if outbound.interactive and isinstance(outbound.interactive.get('body'), dict):
            outbound.interactive['body']['text'] = outbound.body_text
    outbound.follow_up = []
    if available(conv):
        now = frappe.utils.now_datetime()
        memory.update(topic=topic, intent=intent_key, status='awaiting_user', question=question, options=options,
                      employee=context.get('employee'), user=context.get('user') or conv.get('erp_user'), last_inbound_at=now.isoformat())
        _schedule(conv,memory,settings(),now)
        event(conv,'question',topic,intent_key)
    return outbound
