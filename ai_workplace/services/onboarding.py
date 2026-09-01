"""
Onboarding playbook loader and conversation mode for new hires.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import frappe

from ai_workplace.ai.prompts.onboarding import ONBOARDING
from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message


def get_onboarding_playbook(employee: str) -> Optional[dict[str, Any]]:
    if not employee or not frappe.db.exists("DocType", "AI Onboarding Playbook"):
        return None
    doj = frappe.db.get_value("Employee", employee, "date_of_joining")
    if not doj:
        return None
    days = (frappe.utils.getdate() - frappe.utils.getdate(doj)).days
    playbooks = frappe.get_all(
        "AI Onboarding Playbook",
        filters={"is_active": 1},
        fields=["name", "playbook_name", "day_from", "day_to", "checklist_json", "system_prompt"],
    )
    for pb in playbooks:
        if int(pb.day_from or 0) <= days <= int(pb.day_to or 30):
            checklist = []
            if pb.checklist_json:
                try:
                    checklist = json.loads(pb.checklist_json)
                except Exception:
                    checklist = []
            return {
                "name": pb.name,
                "playbook_name": pb.playbook_name,
                "system_prompt": pb.system_prompt or ONBOARDING,
                "checklist": checklist,
                "day": days,
            }
    return None


def start_onboarding_agent(
    conv: Any,
    context: dict[str, Any],
    playbook: dict[str, Any],
    gaps: dict[str, Any],
) -> OutboundMessage:
    name = gaps.get("employee_name") or "there"
    checklist = playbook.get("checklist") or _default_checklist()
    draft = {
        "playbook": playbook.get("name"),
        "step_index": 0,
        "checklist": checklist,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent="onboarding_agent",
        draft_payload=json.dumps(draft),
    )
    first = checklist[0] if checklist else {"title": "Complete your profile", "action": "svc_update_profile"}
    body = (
        f"🎉 *Welcome to MicroMerger, {name}!*\n\n"
        f"I'm your onboarding assistant (Day {playbook.get('day', 0)}).\n\n"
        f"*Step 1:* {first.get('title', 'Get started')}\n\n"
        f"{first.get('description', '')}"
    ).strip()
    buttons = [{"id": first.get("action", "svc_update_profile"), "title": first.get("button", "Start")[:20]}]
    buttons.append({"id": "svc_main_menu", "title": "Main Menu"})
    return build_button_message(body, buttons[:3])


def handle_onboarding_message(conv: Any, text: str, context: dict[str, Any]) -> OutboundMessage:
    draft = json.loads(conv.draft_payload or "{}")
    checklist = draft.get("checklist") or _default_checklist()
    idx = int(draft.get("step_index", 0))

    if text.lower() in ("next", "continue", "yes", "ok", "onboarding_next", "svc_onboarding_next"):
        idx += 1

    if idx >= len(checklist):
        update_conversation(conv, state=ConversationState.PROCESSING, current_intent="hr_ai_agent", draft_payload=None)
        return OutboundMessage(
            body_text="🎉 Onboarding checklist complete! Type any HR question or *menu* for services."
        )

    step = checklist[idx]
    draft["step_index"] = idx
    update_conversation(conv, draft_payload=json.dumps(draft))
    body = f"*Step {idx + 1}:* {step.get('title', '')}\n{step.get('description', '')}"
    buttons = [{"id": step.get("action", "svc_update_profile"), "title": step.get("button", "Continue")[:20]}]
    if idx + 1 < len(checklist):
        buttons.append({"id": "svc_onboarding_next", "title": "Next Step"})
    buttons.append({"id": "svc_main_menu", "title": "Main Menu"})
    return build_button_message(body, buttons[:3])


def _default_checklist() -> list[dict[str, str]]:
    return [
        {
            "title": "Set Support PIN in HRMIS Portal",
            "description": "Required before accessing secure WhatsApp services.",
            "action": "svc_open_hrmis",
            "button": "Open Portal",
        },
        {
            "title": "Complete your profile",
            "description": "Add CNIC, bank, and contact details.",
            "action": "svc_update_profile",
            "button": "Update Profile",
        },
        {
            "title": "Review company policies",
            "description": "Ask the AI assistant about leave, attendance, and HR policies.",
            "action": "svc_pol_ai_assistant",
            "button": "Ask AI",
        },
    ]


def seed_default_onboarding_playbook() -> None:
    if not frappe.db.exists("DocType", "AI Onboarding Playbook"):
        return
    name = "default_new_hire"
    if frappe.db.exists("AI Onboarding Playbook", name):
        return
    doc = frappe.get_doc(
        {
            "doctype": "AI Onboarding Playbook",
            "playbook_name": name,
            "is_active": 1,
            "day_from": 0,
            "day_to": 30,
            "checklist_json": json.dumps(_default_checklist()),
            "system_prompt": ONBOARDING,
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
