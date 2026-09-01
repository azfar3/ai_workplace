"""Debug Leave Message / hr_wait_connect flow."""
import frappe


def run(wa_id: str = "923111123678"):
    from ai_workplace.identity.resolver import resolve_identity, get_or_create_whatsapp_identity
    from ai_workplace.context.resolver import get_user_context
    from ai_workplace.conversation.manager import get_or_create_conversation, update_conversation
    from ai_workplace.conversation.state import ConversationState
    from ai_workplace.services.hr_contact_prompt import handle_contact_hr_intro, handle_contact_hr_prompt_reply
    from ai_workplace.conversation.orchestrator import process_message

    phone = f"+{wa_id}" if not wa_id.startswith("+") else wa_id
    identity = resolve_identity(phone)
    identity.whatsapp_identity = get_or_create_whatsapp_identity(identity, wa_id=wa_id)
    ctx = get_user_context(identity)
    conv = get_or_create_conversation(identity, wa_id=wa_id, trace_id="dbg")
    update_conversation(
        conv,
        state=ConversationState.HR_CONTACT_PROMPT,
        current_intent="contact_hr",
        active_service=None,
    )
    print("person_type", ctx.get("person_type"), "employee", ctx.get("employee"))

    for msg in ("Leave Message", "hr_wait_connect", "leave message"):
        try:
            out = handle_contact_hr_prompt_reply(conv, msg, ctx, identity=identity)
            print(f"--- {msg!r} -> state={conv.current_state} skip={getattr(out, 'skip_send', False)}")
            print((out.body_text or "")[:250])
        except Exception:
            import traceback
            print(f"--- {msg!r} FAILED")
            traceback.print_exc()

    update_conversation(conv, state=ConversationState.HR_CONTACT_PROMPT, current_intent="contact_hr")
    try:
        out = process_message(
            "i want to talk about my salary deduction",
            identity,
            message_id="dbg-free",
            trace_id="dbg",
            wa_id=wa_id,
        )
        print("--- free text ->", conv.current_state, (out.body_text or "")[:200])
    except Exception:
        import traceback
        traceback.print_exc()
