"""
ai_workplace/conversation/menu.py
───────────────────────────────────
Dynamic Menu & Selection Parser — Phase 2.
"""

from __future__ import annotations

from typing import Any, Optional

from ai_workplace.services.registry import get_available_services_for_context
from ai_workplace.response.builder import (
    build_welcome_menu_response,
    build_invalid_selection_response,
)
from ai_workplace.whatsapp.interactive import (
    build_service_list_message,
    build_quick_action_buttons_message,
    build_grouped_service_list_message,
    build_submenu_quick_buttons_message,
    build_submenu_remaining_list_message,
)
from ai_workplace.whatsapp.outbound import OutboundMessage


def build_menu(
    context: dict[str, Any],
    header_prefix: str = "",
    include_greeting: bool = False,
    parent_key: Optional[str] = None,
) -> tuple[OutboundMessage, list[dict[str, Any]]]:
    """
    Build clickable list menu (top-level or submenu) and return available service list.
    """
    services = get_available_services_for_context(context, parent_key=parent_key)
    if not parent_key:
        quick_out = build_quick_action_buttons_message(context, services, header_prefix=header_prefix)
        list_out = build_grouped_service_list_message(context, services)
        if quick_out:
            quick_out.follow_up = [list_out]
            return quick_out, services

    quick_out = build_submenu_quick_buttons_message(context, services, header_prefix=header_prefix)
    list_out = build_submenu_remaining_list_message(context, services)
    if quick_out and list_out:
        quick_out.follow_up = [list_out]
        return quick_out, services

    outbound = build_service_list_message(
        context,
        services,
        header_prefix=header_prefix,
        include_greeting=include_greeting,
    )
    return outbound, services


def build_menu_text_fallback(
    context: dict[str, Any],
    parent_key: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Plain-text menu fallback for tests and interactive failure."""
    services = get_available_services_for_context(context, parent_key=parent_key)
    menu_text = build_welcome_menu_response(context, services)
    return menu_text, services


def parse_menu_selection(
    user_input: str,
    context: dict[str, Any],
    parent_key: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """
    Parse user selection from text, number, or interactive id (svc_hr).
    """
    if not user_input:
        return None

    clean_input = user_input.strip().lower()
    services = get_available_services_for_context(context, parent_key=parent_key)

    # Interactive list/button ids: svc_hr, svc_policy, ...
    if clean_input.startswith("svc_"):
        key = clean_input[4:]
        for service in services:
            if service["key"].lower() == key:
                return service
        return None

    # Numeric selection (1-indexed)
    if clean_input.isdigit():
        idx = int(clean_input) - 1
        if 0 <= idx < len(services):
            return services[idx]
        return None

    # Textual / alias matching — avoid loose substring matches on menu keys.
    for service in services:
        key = service["key"].lower()
        title = service["title"].lower()
        aliases = [a.lower() for a in service.get("aliases", [])]

        if clean_input == key or clean_input == title or clean_input in aliases:
            return service

    return None



def build_invalid_selection_message(context: dict[str, Any]) -> OutboundMessage:
    """Invalid selection notice + refreshed clickable menu."""
    services = get_available_services_for_context(context)
    error_text = build_invalid_selection_response(context, services)
    err_prefix = error_text.split("\n\n")[0]
    return build_service_list_message(context, services, header_prefix=err_prefix)

