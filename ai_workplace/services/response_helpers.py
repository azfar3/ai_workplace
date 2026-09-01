"""
ai_workplace/services/response_helpers.py
───────────────────────────────────────────
Helpers for wrapping service responses with navigation buttons.
"""

from __future__ import annotations

from typing import Any

from ai_workplace.whatsapp.interactive import (
    build_show_menu_again_button,
    build_monthly_attendance_options_message,
    build_salary_slip_period_options_message,
)
from ai_workplace.whatsapp.outbound import OutboundMessage


def wrap_with_menu_again(body_text: str, context: dict[str, Any]) -> OutboundMessage:
    """Attach a 'Show Menu' button message after a plain-text service response."""
    msg = OutboundMessage(body_text=body_text)
    menu_btn = build_show_menu_again_button(context)
    if menu_btn:
        msg.follow_up = [menu_btn]
    return msg


def wrap_monthly_attendance_summary(body_text: str, context: dict[str, Any]) -> OutboundMessage:
    """Attach monthly follow-up buttons after the summary."""
    msg = OutboundMessage(body_text=body_text)
    msg.follow_up = [build_monthly_attendance_options_message(context, after_summary=True)]
    return msg


def wrap_monthly_attendance_detail(body_text: str, context: dict[str, Any]) -> OutboundMessage:
    """Attach navigation buttons after last-7-days detail."""
    msg = OutboundMessage(body_text=body_text)
    msg.follow_up = [build_monthly_attendance_options_message(context, after_summary=False)]
    return msg


def wrap_salary_slip_period_options(body_text: str, context: dict[str, Any]) -> OutboundMessage:
    """Attach salary slip period buttons after intro or error."""
    msg = OutboundMessage(body_text=body_text)
    msg.follow_up = [build_salary_slip_period_options_message(context)]
    return msg


def wrap_bank_letter_options(body_text: str, context: dict[str, Any]) -> OutboundMessage:
    """Attach bank selection buttons for bank letter download."""
    from ai_workplace.whatsapp.interactive import build_bank_letter_options_message

    msg = OutboundMessage(body_text=body_text)
    msg.follow_up = [build_bank_letter_options_message(context)]
    return msg
