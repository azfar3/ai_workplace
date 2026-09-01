"""
Proactive session-start nudges for active employees — employee-first, max one reminder.
"""

from __future__ import annotations

from typing import Any, Optional

import frappe

from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.whatsapp.interactive import build_button_message
from ai_workplace.services.profile_gaps import get_employee_profile_gaps, gap_flow_key, employee_gap_label
from ai_workplace.security.support_pin import get_pin_status

# Gaps that should not trigger session-start nudges (use service menus instead)
_NUDGE_SKIP_KEYS = frozenset({"attendance_checkin", "attendance_missing", "support_pin_not_configured"})


def maybe_send_proactive_nudge(
    conv: Any,
    context: dict[str, Any],
) -> Optional[OutboundMessage]:
    """Return at most one useful reminder after language selection (cooldown applies)."""
    try:
        settings = frappe.get_single("AI Workplace Settings")
        if not settings.proactive_notifications_enabled:
            return None
    except Exception:
        return None

    employee = context.get("employee") or ""
    if not employee:
        return None

    cooldown_key = f"proactive_nudge:{employee}"
    if frappe.cache().get_value(cooldown_key):
        return None

    card = _build_single_reminder(context, settings)
    if not card:
        return None

    hours = int(getattr(settings, "proactive_cooldown_hours", None) or 24)
    frappe.cache().set_value(cooldown_key, 1, expires_in_sec=hours * 3600)
    return card


def _build_single_reminder(context: dict[str, Any], settings: Any) -> Optional[OutboundMessage]:
    employee = context.get("employee") or ""
    lang = context.get("preferred_language", "English")
    gaps_report = get_employee_profile_gaps(employee)
    actionable = [
        g for g in gaps_report.get("all_gaps", [])
        if g.get("key") not in _NUDGE_SKIP_KEYS
        and g.get("update_mode") in ("ticket", "direct", "portal_only")
        and g.get("severity") in ("critical", "high")
    ]

    # Priority: payroll-impacting bank gap
    bank_gap = next((g for g in actionable if g.get("key") == "bank"), None)
    if bank_gap:
        return _reminder_card(
            context,
            title="One HR action needs your attention.",
            body=(
                "Your payroll bank information is incomplete. "
                "Completing it can help avoid delays in salary processing."
            ),
            primary={"id": "svc_gap_bank", "title": "Review Bank Details"},
            secondary={"id": "svc_main_menu", "title": "Later"},
        )

    if actionable:
        top = actionable[0]
        flow = top.get("flow_key") or gap_flow_key(top.get("key", ""))
        btn_id = f"svc_gap_{top['key']}" if top.get("update_mode") != "portal_only" else "svc_update_profile"
        if flow and top.get("update_mode") in ("direct", "ticket"):
            btn_id = f"svc_{flow}"
        return _reminder_card(
            context,
            title="One item may need your attention.",
            body=f"{top.get('label')} — completing this helps keep your HR services running smoothly.",
            primary={"id": btn_id, "title": "Review Next Item"},
            secondary={"id": "svc_main_menu", "title": "Later"},
        )

    if settings and getattr(settings, "proactive_attendance_nudge", 0):
        snap = _attendance_snapshot(employee)
        if not snap.get("checked_in_today") and snap.get("whatsapp_attendance_enabled"):
            return _reminder_card(
                context,
                title="Attendance reminder",
                body="You have not checked in today. Use Check In from the Attendance menu when you arrive.",
                primary={"id": "svc_att_checkin", "title": "Check In"},
                secondary={"id": "svc_main_menu", "title": "Later"},
            )

    return None


def _reminder_card(
    context: dict[str, Any],
    *,
    title: str,
    body: str,
    primary: dict[str, str],
    secondary: dict[str, str],
) -> OutboundMessage:
    text = f"*{title}*\n\n{body}"
    return build_button_message(text, [primary, secondary])


def _attendance_snapshot(employee: str) -> dict:
    try:
        from ai_workplace.services.attendance_guidance import get_attendance_snapshot

        return get_attendance_snapshot(employee)
    except Exception:
        return {"checked_in_today": True, "whatsapp_attendance_enabled": False}
