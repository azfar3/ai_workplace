"""Debug Chat with HR flow."""
import frappe


def run():
    from ai_workplace.services.hr_contact_prompt import build_contact_hr_options_message
    from ai_workplace.context.resolver import get_user_context
    from ai_workplace.conversation.orchestrator import process_message
    from ai_workplace.identity.resolver import resolve_identity
    from ai_workplace.conversation.menu import parse_menu_selection

    phone = "+923111123678"
    identity = resolve_identity(phone)
    print("identity status:", identity.status, "employee:", identity.employee)
    ctx = get_user_context(identity)
    print("person_type:", ctx.get("person_type"))
    print("allowed:", ctx.get("allowed_services"))

    out = build_contact_hr_options_message(ctx)
    print("build OK, body len:", len(out.body_text or ""))
    print("interactive body len:", len(out.interactive.get("body", {}).get("text", "")))

    wa_id = phone.lstrip("+")
    try:
        resp = process_message("svc_contact_hr", identity, message_id="dbg-chr", trace_id="dbg", wa_id=wa_id)
        print("OK:", (resp.body_text or "")[:200])
    except Exception:
        import traceback
        traceback.print_exc()
