"""
ai_workplace/whatsapp/interactive.py
─────────────────────────────────────
Build Meta WhatsApp interactive message payloads (list + button menus).
"""

from __future__ import annotations

from typing import Any

from ai_workplace.response.builder import build_menu_header_text, _translate_service_title
from ai_workplace.whatsapp.outbound import OutboundMessage

def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def build_button_message(
    body: str,
    buttons: list[dict[str, str]],
    *,
    footer: str = "",
) -> OutboundMessage:
    """Build a WhatsApp reply-button message (max 3 buttons)."""
    action_buttons = []
    for btn in buttons[:3]:
        action_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn.get("id", ""),
                "title": _truncate(btn.get("title", ""), 20),
            },
        })
    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": action_buttons},
    }
    if footer:
        interactive["footer"] = {"text": _truncate(footer, 60)}
    return OutboundMessage(body_text=body, interactive=interactive)


def build_live_location_request_message(body: str) -> OutboundMessage:
    """WhatsApp native location request — prompts user to send current GPS location."""
    interactive: dict[str, Any] = {
        "type": "location_request_message",
        "body": {"text": _truncate(body, 1024)},
        "action": {"name": "send_location"},
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def build_service_list_message(
    context: dict[str, Any],
    services: list[dict[str, Any]],
    header_prefix: str = "",
    include_greeting: bool = False,
) -> OutboundMessage:
    """
    Build a WhatsApp interactive list message for the main service menu.
    Meta limits: 10 rows, title 24 chars, description 72 chars.
    """
    lang = context.get("preferred_language", "English")
    header_text = build_menu_header_text(context, include_greeting=include_greeting)
    if header_prefix:
        body = f"{header_prefix}\n\n{header_text}"
    else:
        body = header_text


    rows = []
    for svc in services[:10]:
        key = svc["key"]
        title = _translate_service_title(key, svc["title"], lang)
        description = svc.get("description") or title
        rows.append({
            "id": f"svc_{key}",
            "title": _truncate(title, 24),
            "description": _truncate(description, 72),
        })

    section_title = "Services"
    if lang == "Urdu":
        section_title = "سروسز"
    elif lang == "Roman Urdu":
        section_title = "Services"

    button_label = "View Services"
    if lang == "Urdu":
        button_label = "سروسز دیکھیں"
    elif lang == "Roman Urdu":
        button_label = "Services dekhein"

    interactive = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": _truncate(button_label, 20),
            "sections": [{"title": _truncate(section_title, 24), "rows": rows}],
        },
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def _quick_action_prompt(lang: str) -> str:
    if lang == "Urdu":
        return "فوری اختیارات:"
    if lang == "Roman Urdu":
        return "Fori options:"
    return "Tap a quick option:"


def _browse_all_prompt(lang: str) -> str:
    if lang == "Urdu":
        return "📋 *تمام Staff Services*"
    if lang == "Roman Urdu":
        return "📋 *Tamam Staff Services*"
    return "📋 *All Staff Services*"


def build_quick_action_buttons_message(
    context: dict[str, Any],
    services: list[dict[str, Any]],
    header_prefix: str = "",
) -> OutboundMessage | None:
    """
    Employee-first quick reply buttons: Attendance, Payroll, Chat with HR.
    """
    from ai_workplace.services.registry import ACTIVE_EMPLOYEE_QUICK_ACTION_KEYS

    lang = context.get("preferred_language", "English")
    by_key = {svc["key"]: svc for svc in services}
    quick_services = [by_key[k] for k in ACTIVE_EMPLOYEE_QUICK_ACTION_KEYS if k in by_key]
    if not quick_services:
        quick_services = [svc for svc in services if svc.get("key") != "main_menu"][:3]
    if not quick_services:
        return None

    prompt = _quick_action_prompt(lang)
    if header_prefix:
        body = f"{header_prefix}\n\n{prompt}"
    else:
        body = prompt

    buttons = []
    for svc in quick_services:
        title = _translate_service_title(svc["key"], svc["title"], lang)
        buttons.append({
            "type": "reply",
            "reply": {
                "id": f"svc_{svc['key']}",
                "title": _truncate(title, 20),
            },
        })

    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def build_grouped_service_list_message(
    context: dict[str, Any],
    services: list[dict[str, Any]],
    header_prefix: str = "",
    *,
    rows_override: list[dict[str, Any]] | None = None,
) -> OutboundMessage:
    """Full service list grouped into sections (bank-style browse menu)."""
    lang = context.get("preferred_language", "English")
    browse = _browse_all_prompt(lang)
    if header_prefix:
        body = f"{header_prefix}\n\n{browse}\n\nFind the HR or operational support you need."
    else:
        body = f"{browse}\n\nFind the HR or operational support you need."

    rows = rows_override or []
    if not rows:
        for svc in services[:10]:
            key = svc["key"]
            title = _translate_service_title(key, svc["title"], lang)
            description = svc.get("description") or title
            rows.append({
                "id": f"svc_{key}",
                "title": _truncate(title, 24),
                "description": _truncate(description, 72),
            })

    section_title = "Services"
    if lang == "Urdu":
        section_title = "سروسز"
    elif lang == "Roman Urdu":
        section_title = "Services"

    button_label = "View Services"
    if lang == "Urdu":
        button_label = "سروسز دیکھیں"
    elif lang == "Roman Urdu":
        button_label = "Services dekhein"

    interactive = {
        "type": "list",
        "body": {"text": body},
        "action": {
            "button": _truncate(button_label, 20),
            "sections": [{"title": _truncate(section_title, 24), "rows": rows}],
        },
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def _split_submenu_services(services: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """First 3 actionable items as quick buttons; remainder (+ main menu) in list."""
    non_back = [s for s in services if s.get("key") != "main_menu"]
    back_items = [s for s in services if s.get("key") == "main_menu"]
    quick = non_back[:3]
    remaining = non_back[3:] + back_items
    return quick, remaining


def build_submenu_quick_buttons_message(
    context: dict[str, Any],
    services: list[dict[str, Any]],
    header_prefix: str = "",
) -> OutboundMessage | None:
    """Submenu quick reply buttons for the first 3 options."""
    lang = context.get("preferred_language", "English")
    quick, _remaining = _split_submenu_services(services)
    if not quick:
        return None

    prompt = _quick_action_prompt(lang)
    body = f"{header_prefix}\n\n{prompt}" if header_prefix else prompt

    buttons = []
    for svc in quick[:3]:
        title = _translate_service_title(svc["key"], svc["title"], lang)
        buttons.append({
            "type": "reply",
            "reply": {
                "id": f"svc_{svc['key']}",
                "title": _truncate(title, 20),
            },
        })

    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def build_submenu_remaining_list_message(
    context: dict[str, Any],
    services: list[dict[str, Any]],
) -> OutboundMessage:
    """Remaining submenu options in a list (plus main menu)."""
    lang = context.get("preferred_language", "English")
    _quick, remaining = _split_submenu_services(services)
    rows = []
    for svc in remaining[:10]:
        key = svc["key"]
        title = _translate_service_title(key, svc["title"], lang)
        description = svc.get("description") or title
        rows.append({
            "id": f"svc_{key}",
            "title": _truncate(title, 24),
            "description": _truncate(description, 72),
        })
    return build_grouped_service_list_message(context, services, rows_override=rows)


def build_show_menu_again_button(context: dict[str, Any]) -> OutboundMessage:
    """Single button to return to the main menu."""
    lang = context.get("preferred_language", "English")
    if lang == "Urdu":
        body = "مزید اختیارات کے لیے مین مینو دیکھیں:"
        title = "🏠 مین مینو"
    elif lang == "Roman Urdu":
        body = "Aur options ke liye main menu dekhein:"
        title = "🏠 Main Menu"
    else:
        body = "Need something else? Tap below to open the main menu:"
        title = "🏠 Main Menu"

    interactive = {
        "type": "button",
        "body": {"text": body},
        "action": {
            "buttons": [{
                "type": "reply",
                "reply": {"id": "svc_main_menu", "title": _truncate(title, 20)},
            }],
        },
    }
    return OutboundMessage(body_text=body, interactive=interactive)


def build_yes_no_buttons(
    prompt: str,
    *,
    yes_id: str = "yes",
    no_id: str = "no",
    yes_label: str = "Yes",
    no_label: str = "No",
) -> OutboundMessage:
    """Two-button yes/no prompt."""
    interactive = {
        "type": "button",
        "body": {"text": prompt},
        "action": {
            "buttons": [
                {"type": "reply", "reply": {"id": yes_id, "title": _truncate(yes_label, 20)}},
                {"type": "reply", "reply": {"id": no_id, "title": _truncate(no_label, 20)}},
            ],
        },
    }
    return OutboundMessage(body_text=prompt, interactive=interactive)


def build_deliverable_post_save_buttons(body_text: str) -> OutboundMessage:
    """Submit-for-approval and main-menu actions after a deliverable draft is saved."""
    interactive = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {
                        "id": "dlv_submit_now",
                        "title": _truncate("Submit for Approval", 20),
                    },
                },
                {
                    "type": "reply",
                    "reply": {
                        "id": "svc_main_menu",
                        "title": _truncate("🏠 Main Menu", 20),
                    },
                },
            ],
        },
    }
    return OutboundMessage(body_text=body_text, interactive=interactive)


def build_leave_type_list_message(
    context: dict[str, Any],
    leave_types: list[dict[str, Any]],
    header: str,
) -> OutboundMessage:
    """Interactive list for selecting a leave type during apply flow."""
    rows = []
    for idx, item in enumerate(leave_types[:10]):
        lt = item.get("leave_type") or "Leave"
        remaining = item.get("remaining", "")
        rows.append({
            "id": f"lt_{idx}",
            "title": _truncate(lt, 24),
            "description": _truncate(f"Balance: {remaining} days", 72),
        })

    interactive = {
        "type": "list",
        "body": {"text": header},
        "action": {
            "button": _truncate("Select Leave", 20),
            "sections": [{"title": "Leave Types", "rows": rows}],
        },
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def build_grievance_type_list_message(
    grievance_types: list[str],
    header: str,
) -> OutboundMessage:
    """Interactive list for selecting incident / grievance type."""
    rows = []
    for idx, gt in enumerate(grievance_types[:10]):
        rows.append({
            "id": f"gt_{idx}",
            "title": _truncate(gt, 24),
            "description": _truncate(gt, 72),
        })

    interactive = {
        "type": "list",
        "body": {"text": header},
        "action": {
            "button": _truncate("Select Type", 20),
            "sections": [{"title": "Incident Type", "rows": rows}],
        },
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def build_option_list_message(
    options: list[dict[str, Any] | str],
    header: str,
    *,
    button_label: str = "Select",
    section_title: str = "Options",
    id_prefix: str = "opt",
    label_key: str = "label",
) -> OutboundMessage:
    """Generic interactive list from dict rows or plain strings."""
    rows = []
    for idx, item in enumerate(options[:10]):
        if isinstance(item, dict):
            label = item.get(label_key) or item.get("title") or ""
        else:
            label = str(item)
        rows.append({
            "id": f"{id_prefix}_{idx}",
            "title": _truncate(label, 24),
            "description": _truncate(label, 72),
        })

    interactive = {
        "type": "list",
        "body": {"text": header},
        "action": {
            "button": _truncate(button_label, 20),
            "sections": [{"title": _truncate(section_title, 24), "rows": rows}],
        },
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def build_flow_group_message(context: dict[str, Any], flow_group: str) -> OutboundMessage:
    """Build WhatsApp button message from DB-backed flow menu items."""
    from ai_workplace.services.registry import get_flow_group_prompt, get_flow_menu_items

    lang = context.get("preferred_language", "English")
    prompt = get_flow_group_prompt(flow_group, context)
    items = get_flow_menu_items(flow_group, context)
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": f"svc_{item['key']}",
                "title": _truncate(_translate_service_title(item["key"], item["title"], lang), 20),
            },
        }
        for item in items[:3]
    ]
    interactive = {
        "type": "button",
        "body": {"text": prompt},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=prompt, interactive=interactive)


def build_monthly_attendance_options_message(
    context: dict[str, Any],
    *,
    after_summary: bool = True,
) -> OutboundMessage:
    """Quick buttons after monthly summary or day-wise detail."""
    flow_group = "att_monthly_summary" if after_summary else "att_monthly_detail"
    return build_flow_group_message(context, flow_group)


def build_salary_slip_period_options_message(context: dict[str, Any]) -> OutboundMessage:
    """Three-button period picker for salary slip download."""
    return build_flow_group_message(context, "salary_slip_period")


def build_bank_letter_options_message(context: dict[str, Any]) -> OutboundMessage:
    """Bank selection buttons for bank letter download."""
    return build_flow_group_message(context, "bank_letter_select")
