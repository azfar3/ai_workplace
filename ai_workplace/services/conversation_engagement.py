"""Account preferences, resumable task snapshots and aggregate engagement events."""
from __future__ import annotations

import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from ai_workplace.advanced_conversation import RESUMABLE_WORKFLOWS
from ai_workplace.conversation_guidance import load_memory
from ai_workplace.whatsapp.outbound import OutboundMessage


def _frappe():
    import frappe
    return frappe


def installed(doctype):
    return bool(_frappe().db.exists('DocType', doctype))


def preference(user):
    frappe = _frappe()
    if not user or user == 'Guest' or not installed('AI Conversation Preference'):
        return None
    return frappe.db.get_value('AI Conversation Preference', {'user': user}, ['reminders_enabled','quiet_start','quiet_end','timezone'], as_dict=True)


def reminders_allowed(user):
    value = preference(user)
    return value is None or bool(int(value.get('reminders_enabled') or 0))


def save_preference(user, enabled, quiet_start=20, quiet_end=9, timezone=None):
    frappe = _frappe()
    if not user or user == 'Guest':
        frappe.throw('Sign in to change account reminder preferences.', frappe.PermissionError)
    if not 0 <= int(quiet_start) <= 23 or not 0 <= int(quiet_end) <= 23:
        frappe.throw('Quiet hours must be between 0 and 23.')
    timezone = timezone or frappe.utils.get_system_timezone()
    ZoneInfo(timezone)  # Reject invalid timezones before saving.
    name = frappe.db.get_value('AI Conversation Preference', {'user': user}, 'name')
    doc = frappe.get_doc('AI Conversation Preference', name) if name else frappe.new_doc('AI Conversation Preference')
    doc.update(dict(user=user, reminders_enabled=int(bool(enabled)), quiet_start=int(quiet_start), quiet_end=int(quiet_end), timezone=timezone))
    doc.save(ignore_permissions=True)
    if not enabled:
        frappe.db.set_value('WhatsApp Conversation', {'erp_user': user, 'followup_status': ['in', ['Pending','Claimed']]}, {'followup_status': 'Cancelled', 'followup_due_at': None}, update_modified=False)
    return dict(reminders_enabled=int(bool(enabled)), quiet_start=int(quiet_start), quiet_end=int(quiet_end), timezone=timezone)


def event(conv, kind, topic='', intent='', token_count=0, cost=0):
    # Observability must never turn a successful ERP transaction into an error.
    frappe = _frappe()
    frappe.db.savepoint('conversation_event')
    try:
        _record_event(conv, kind, topic, intent, token_count, cost)
    except Exception:
        frappe.db.rollback(save_point='conversation_event')
        frappe.log_error(title='Conversation engagement recording failed', message=frappe.get_traceback())


def _record_event(conv, kind, topic='', intent='', token_count=0, cost=0):
    """No message text, employee values or policy content is stored in metrics."""
    frappe = _frappe()
    if not installed('AI Conversation Event'):
        return
    import hashlib
    message = conv.get('last_message_id') or ''
    # Idempotent for webhook retries. Scheduled sends have their own stable key.
    seed = f"{conv.name}:{message}:{kind}:{topic}:{intent}"
    if not message:
        seed += ':' + str(frappe.utils.now_datetime())
    key = hashlib.sha256(seed.encode()).hexdigest()
    if frappe.db.exists('AI Conversation Event', {'message_key': key}):
        return
    doc = frappe.new_doc('AI Conversation Event')
    doc.update(dict(conversation=conv.name, topic=topic[:100], intent=intent[:100], event=kind,
                    channel='Web' if (conv.get('wa_id') or '').startswith('WEB-') else 'WhatsApp',
                    message_key=key, token_count=max(0, int(token_count or 0)), cost=max(0, float(cost or 0))))
    doc.insert(ignore_permissions=True, ignore_if_duplicate=True)


def _owner_filters(conv, context):
    return dict(erp_user=context.get('user') or conv.get('erp_user'), employee=context.get('employee'),
                whatsapp_identity=conv.get('whatsapp_identity'), channel='Web' if (conv.get('wa_id') or '').startswith('WEB-') else 'WhatsApp')


def pause_task(conv, context):
    frappe = _frappe()
    if not installed('AI Conversation Task') or not context.get('employee') or not (context.get('user') or conv.get('erp_user')):
        return None
    intent = conv.get('current_intent')
    memory = load_memory(conv.get('guidance_memory'))
    if intent not in RESUMABLE_WORKFLOWS and memory.get('status') != 'awaiting_user':
        return None
    # All security and human-owned conversations are excluded, regardless of memory.
    if conv.get('active_hr_chat_session') or conv.get('current_state') in {'WAITING_FOR_SUPPORT_PIN','LIVE_HR_CHAT','HR_GUEST_INTAKE','HR_CONTACT_PROMPT'}:
        return None
    topic = RESUMABLE_WORKFLOWS[intent][0] if intent in RESUMABLE_WORKFLOWS else memory.get('topic', 'HR question')
    filters = dict(_owner_filters(conv, context), status='Paused', intent=intent or memory.get('intent') or '', conversation=conv.name, source_message_id=conv.get('last_message_id'))
    name = frappe.db.get_value('AI Conversation Task', filters, 'name')
    doc = frappe.get_doc('AI Conversation Task', name) if name else frappe.new_doc('AI Conversation Task')
    draft = conv.get('draft_payload') if intent in RESUMABLE_WORKFLOWS else None
    # Existing private workflow data stays in a System-Manager-only task record;
    # it is never included in shared knowledge, analytics or LLM prompts.
    doc.update(dict(**_owner_filters(conv, context), conversation=conv.name, topic=topic, intent=filters['intent'],
                    active_service=conv.get('active_service'), state=conv.get('current_state'), draft_payload=draft,
                    question=memory.get('question') or 'Continue the next step of your request.',
                    guidance_payload=json.dumps(memory), status='Paused', expires_at=frappe.utils.now_datetime()+timedelta(days=7),
                    source_message_id=conv.get('last_message_id')))
    doc.save(ignore_permissions=True)
    # Bound retained task count per user/channel. Old tasks are deleted, not exposed.
    old = frappe.get_all('AI Conversation Task', filters=_owner_filters(conv, context), pluck='name', order_by='modified desc', limit_start=10, limit_page_length=100)
    for old_name in old:
        frappe.delete_doc('AI Conversation Task', old_name, ignore_permissions=True)
    event(conv, 'paused', topic, filters['intent'])
    return doc.name


def detach(conv):
    """Leave a draft safely parked; do not run the workflow's cancel/submit code."""
    values = dict(current_state='AWAITING_SELECTION', current_intent=None, active_service=None, draft_payload=None,
                  followup_status='Cancelled', followup_due_at=None)
    memory = load_memory(conv.get('guidance_memory'))
    memory['status'] = 'suspended'
    values['guidance_memory'] = json.dumps(memory)
    conv.db_set(values, update_modified=False)
    for key, value in values.items():
        setattr(conv, key, value)


def task_control(conv, context, text):
    """Returns (handled, response); restore always stops before processing input."""
    frappe = _frappe()
    command = text.strip().lower()
    if command not in {'pause','pause task','my tasks','unfinished tasks','resume','resume task'} and not command.startswith('resume '):
        return False, None
    if not installed('AI Conversation Task'):
        return True, OutboundMessage(body_text='Task resume will be available after the site migration.')
    if command in {'pause','pause task'}:
        name = pause_task(conv, context)
        if name:
            detach(conv)
        return True, OutboundMessage(body_text='Your task is saved. Type “my tasks” to resume it.' if name else 'There is no task to pause.')
    filters = dict(_owner_filters(conv, context), status='Paused', expires_at=['>', frappe.utils.now_datetime()])
    tasks = frappe.get_all('AI Conversation Task', filters=filters, fields=['name','topic','intent'], order_by='modified desc', limit_page_length=10)
    if command in {'my tasks','unfinished tasks'} or command in {'resume','resume task'} and len(tasks) != 1:
        lines = ['Your unfinished tasks:'] + [f'{i}. {row.topic}' for i,row in enumerate(tasks, 1)]
        return True, OutboundMessage(body_text='\n'.join(lines)+'\n\nType “resume 1” to continue.' if tasks else 'You have no unfinished tasks.')
    index = 0
    if command.startswith('resume ') and command != 'resume task':
        try:
            index = int(command.split()[1]) - 1
        except (ValueError, IndexError):
            words = command[7:].replace('my ', '').replace('previous ', '').strip()
            matches = [i for i,row in enumerate(tasks) if words in row.topic.lower()]
            if len(matches) != 1:
                return True, OutboundMessage(body_text='Type “my tasks”, then “resume” followed by its number.')
            index = matches[0]
    if index < 0 or index >= len(tasks):
        return True, OutboundMessage(body_text='That task is unavailable. Type “my tasks” for the current list.')
    frappe.db.sql('SELECT name FROM `tabAI Conversation Task` WHERE name=%s FOR UPDATE', (tasks[index].name,))
    task = frappe.get_doc('AI Conversation Task', tasks[index].name)
    if task.status != 'Paused' or any(task.get(key) != value for key,value in _owner_filters(conv,context).items()) or frappe.utils.get_datetime(task.expires_at) <= frappe.utils.now_datetime():
        return True, OutboundMessage(body_text='That task is no longer available.')
    if task.intent in RESUMABLE_WORKFLOWS:
        from ai_workplace.auth.gateway import authorize
        service = RESUMABLE_WORKFLOWS[task.intent][1]
        if not authorize(None, context, service=service).get('allowed'):
            return True, OutboundMessage(body_text='You no longer have access to this service.')
        from ai_workplace.security.authorization import requires_pin
        if requires_pin(task.intent):
            from ai_workplace.security.authorization import authorize_whatsapp_service
            if not authorize_whatsapp_service(context, task.intent, conversation_name=conv.name).get('allowed'):
                return True, OutboundMessage(body_text='Open this service from the menu to verify your PIN, then type “resume” to restore this saved task.')
    if conv.get('current_intent') in RESUMABLE_WORKFLOWS:
        pause_task(conv, context)
    values = dict(current_state=task.state if task.intent in RESUMABLE_WORKFLOWS else 'AWAITING_SELECTION',
                  current_intent=task.intent if task.intent in RESUMABLE_WORKFLOWS else None,
                  active_service=task.active_service, draft_payload=task.draft_payload,
                  guidance_memory=task.guidance_payload, followup_status='Cancelled', followup_due_at=None)
    conv.db_set(values, update_modified=False)
    for key,value in values.items():
        setattr(conv,key,value)
    task.conversation=conv.name
    task.status='Resumed'
    task.save(ignore_permissions=True)
    event(conv,'resumed',task.topic,task.intent)
    # Never process 'resume' as a Yes, form field, or confirmation.
    if task.intent == 'leave_apply':
        from ai_workplace.services.leave_apply import resume_leave_prompt
        return True, resume_leave_prompt(conv, context)
    return True, OutboundMessage(body_text=f'Resumed: {task.topic}.\n\n{task.question}')


def cleanup():
    frappe = _frappe()
    if installed('AI Conversation Task'):
        frappe.db.delete('AI Conversation Task', {'expires_at': ['<', frappe.utils.now_datetime()]})
    if installed('AI Conversation Event'):
        frappe.db.delete('AI Conversation Event', {'creation': ['<', frappe.utils.now_datetime()-timedelta(days=90)]})



def complete_task(conv, context, intent):
    frappe = _frappe()
    frappe.db.savepoint('conversation_completion')
    try:
        if installed('AI Conversation Task'):
            frappe.db.set_value('AI Conversation Task', dict(_owner_filters(conv,context), conversation=conv.name, intent=intent, status='Resumed'), 'status', 'Completed', update_modified=False)
        event(conv,'completed',RESUMABLE_WORKFLOWS.get(intent, ('HR service',))[0],intent)
    except Exception:
        frappe.db.rollback(save_point='conversation_completion')
        frappe.log_error(title='Conversation completion tracking failed', message=frappe.get_traceback())
