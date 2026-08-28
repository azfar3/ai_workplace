"""
ai_workplace/conversation/menu.py
───────────────────────────────────
Dynamic Menu & Selection Parser — Phase 2.

Handles dynamic menu construction and deterministic user selection matching.
Does NOT use AI for menu parsing.
"""

from __future__ import annotations

from typing import Any, Optional

from ai_workplace.services.registry import get_available_services_for_context, get_service_info
from ai_workplace.response.builder import (
    build_welcome_menu_response,
    build_invalid_selection_response,
)


def build_menu(context: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """
    Build dynamic menu response text and return available service list.

    Returns
    -------
    tuple[str, list[dict]]
        (menu_text, available_services)
    """
    services = get_available_services_for_context(context)
    menu_text = build_welcome_menu_response(context, services)
    return menu_text, services


def parse_menu_selection(
    user_input: str,
    context: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Parse user selection input deterministically against available services in context.

    Parameters
    ----------
    user_input : str
        Raw user input text (e.g. "1", "2", "HR", "My Policies", "help").
    context : dict
        User ERP context.

    Returns
    -------
    dict | None
        Selected service dictionary if matched, None otherwise.
    """
    if not user_input:
        return None

    clean_input = user_input.strip().lower()
    services = get_available_services_for_context(context)

    # 1. Check numeric selection (1-indexed)
    if clean_input.isdigit():
        idx = int(clean_input) - 1
        if 0 <= idx < len(services):
            return services[idx]
        return None

    # 2. Check textual / alias matching
    for service in services:
        key = service["key"].lower()
        title = service["title"].lower()
        aliases = [a.lower() for a in service.get("aliases", [])]

        if clean_input == key or clean_input == title or clean_input in aliases:
            return service

        # Partial matching for common terms like "hr", "policies", "travel"
        if key in clean_input or clean_input in title:
            return service

    return None


def build_invalid_selection_message(context: dict[str, Any]) -> str:
    """Build invalid selection message + menu redisplay."""
    services = get_available_services_for_context(context)
    return build_invalid_selection_response(context, services)
