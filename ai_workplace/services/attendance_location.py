"""
WhatsApp location-based attendance check-in / check-out.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional

import frappe
from frappe.utils import format_time, formatdate, getdate, now_datetime, today

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.utils.geofence import is_within_radius
from ai_workplace.whatsapp.interactive import build_button_message, build_live_location_request_message
from ai_workplace.whatsapp.outbound import OutboundMessage

ATTENDANCE_INTENTS = frozenset({"att_checkin", "att_checkout", "att_exception"})
EXCEPTION_REASONS = [
    ("Field Visit", "Field Visit"),
    ("Official Travel", "Official Travel"),
    ("Assigned Meeting", "Assigned Meeting"),
    ("Temporary Duty Location", "Temporary Duty"),
    ("Worksite Visit", "Worksite Visit"),
    ("Location/GPS Problem", "GPS Problem"),
    ("Other", "Other"),
]


def get_whatsapp_attendance_settings() -> dict[str, Any]:
    try:
        settings = frappe.get_single("AI Workplace Settings")
        return {
            "enabled": bool(settings.get("whatsapp_attendance_enabled")),
            "pending_ttl_minutes": int(settings.get("whatsapp_attendance_pending_ttl_minutes") or 10),
            "privacy_notice": (
                settings.get("whatsapp_attendance_privacy_notice")
                or "Your location will only be used to verify this attendance event."
            ),
        }
    except Exception:
        return {
            "enabled": False,
            "pending_ttl_minutes": 10,
            "privacy_notice": "Your location will only be used to verify this attendance event.",
        }


def employee_can_mark_checkin(user_id: str | None) -> bool:
    """True when the ERP user may create Employee Checkin (same gate as HRMIS portal)."""
    if not user_id:
        return True
    try:
        if frappe.has_permission("Employee Checkin", ptype="create", user=user_id):
            return True
        emp_status = frappe.db.get_value("Employee", {"user_id": user_id}, "status")
        if emp_status == "Active":
            return True
        return False
    except Exception:
        return True


def get_attendance_eligibility(employee_id: str, user_id: str | None = None) -> dict[str, Any]:
    """Return eligibility snapshot for WhatsApp location attendance."""
    result: dict[str, Any] = {
        "eligible": False,
        "reason": "",
        "mode": "",
        "mobile_attendance": None,
        "employee_status": "",
    }
    if not employee_id:
        result["reason"] = "Employee not found."
        return result

    emp = frappe.db.get_value(
        "Employee",
        employee_id,
        ["name", "status", "no_attendance", "user_id", "mobile_attendance", "employee_name"],
        as_dict=True,
    )
    if not emp:
        result["reason"] = "Employee not found."
        return result

    result["employee_status"] = emp.status or ""
    if emp.status != "Active":
        result["reason"] = "Your employee account is not active. Contact HR."
        return result

    if emp.no_attendance:
        result["mode"] = "No Attendance Required"
        result["reason"] = "Attendance is not required for your profile."
        return result

    settings = get_whatsapp_attendance_settings()
    if not settings["enabled"]:
        result["reason"] = "WhatsApp attendance is not enabled. Contact HR."
        return result

    effective_user = user_id or emp.user_id
    if not effective_user:
        result["reason"] = "Your employee account is not linked to a portal user. Contact HR."
        return result

    if not employee_can_mark_checkin(effective_user):
        result["reason"] = "You do not have permission to mark attendance on the portal. Contact HR."
        return result

    mobile_attendance = None
    if emp.mobile_attendance:
        mobile_attendance = frappe.db.get_value(
            "Mobile Attendance",
            emp.mobile_attendance,
            [
                "name",
                "name1",
                "location_display_name",
                "allow_outside_geofence_exception",
                "geofence_is_must",
                "lat",
                "lang",
                "radius",
            ],
            as_dict=True,
        )

    result["eligible"] = True
    result["mode"] = "WhatsApp Location"
    result["mobile_attendance"] = mobile_attendance
    return result


def store_location_request_message_id(conv: Any, message_id: str) -> None:
    """Persist outbound location-request wamid so inbound replies can be correlated."""
    if not message_id:
        return
    try:
        draft = json.loads(conv.draft_payload or "{}")
    except Exception:
        return
    if draft.get("flow") != "att_location" or draft.get("step") != "awaiting_location":
        return
    draft["location_request_message_id"] = message_id
    update_conversation(conv, draft_payload=json.dumps(draft))


def validate_live_location_share(
    location: dict[str, Any],
    draft: dict[str, Any],
    context_message_id: str = "",
) -> tuple[bool, str]:
    """
    Reject map-pinned or searched places; accept only current GPS shares.

    WhatsApp does not expose a definitive live-GPS flag. We use:
    - absence of name/address (pinned places usually include these)
    - reply context must match our location-request message when available
    """
    name = (location.get("location_name") or "").strip()
    address = (location.get("location_address") or "").strip()
    if name or address:
        return False, (
            "Please share your *current location*, not a place selected on the map.\n\n"
            "Tap the *Send location* button above, then choose "
            "*Send your current location* (do not drop a pin on the map)."
        )

    expected = (draft.get("location_request_message_id") or "").strip()
    if expected and context_message_id and context_message_id != expected:
        return False, (
            "This location was not sent in reply to the attendance request.\n\n"
            "Tap *Check In* or *Check Out* again, then use the *Send location* button "
            "and choose *Send your current location*."
        )

    return True, ""


def get_location_display_name(mobile_attendance: dict | None) -> str:
    if not mobile_attendance:
        return "Shared Location"
    return (
        mobile_attendance.get("location_display_name")
        or mobile_attendance.get("name1")
        or mobile_attendance.get("name")
        or "Assigned Location"
    )


def get_today_checkin_state(employee_id: str) -> dict[str, Any]:
    curr_date = today()
    logs = frappe.db.get_all(
        "Employee Checkin",
        filters={"employee": employee_id, "time": ["between", [f"{curr_date} 00:00:00", f"{curr_date} 23:59:59"]]},
        fields=["name", "time", "log_type"],
        order_by="time asc",
    )
    last = logs[-1] if logs else None
    last_in = next((l for l in reversed(logs) if l.log_type == "IN"), None)
    last_out = next((l for l in reversed(logs) if l.log_type == "OUT"), None)

    return {
        "logs": logs,
        "last_log": last,
        "last_log_type": last.log_type if last else None,
        "last_in_time": last_in.time if last_in else None,
        "last_out_time": last_out.time if last_out else None,
        "has_in_today": bool(last_in),
        "checked_in_open": bool(last_in and (not last_out or last_out.time < last_in.time)),
        "checked_out_today": bool(last_in and last_out and last_out.time >= last_in.time),
    }


def is_duplicate_whatsapp_message(message_id: str) -> bool:
    if not message_id:
        return False
    if frappe.db.exists("Employee Checkin", {"custom_whatsapp_message_id": message_id}):
        return True
    return False


def validate_pending_request(draft: dict) -> tuple[bool, str]:
    started = draft.get("pending_started_at")
    if not started:
        return True, ""
    ttl = get_whatsapp_attendance_settings()["pending_ttl_minutes"]
    try:
        started_dt = frappe.utils.get_datetime(started)
    except Exception:
        return False, "Your attendance request has expired. Please start again."
    if now_datetime() > started_dt + timedelta(minutes=ttl):
        return False, (
            "Your Check-In request has expired.\n"
            "Please start Check-In again so we can verify your current location and time."
        )
    return True, ""


def validate_geofence(
    employee_lat: float,
    employee_lon: float,
    mobile_attendance: dict | None,
) -> dict[str, Any]:
    if not mobile_attendance:
        return {
            "inside": True,
            "distance_m": 0.0,
            "geofence_result": "Not Required",
            "location_name": "Shared Location",
            "center_lat": 0.0,
            "center_lon": 0.0,
            "radius_m": 0.0,
        }

    geofence_required = bool(mobile_attendance.get("geofence_is_must"))
    try:
        center_lat = float(mobile_attendance.get("lat") or 0)
        center_lon = float(mobile_attendance.get("lang") or 0)
    except (TypeError, ValueError):
        center_lat, center_lon = 0.0, 0.0

    radius_m = float(mobile_attendance.get("radius") or 0)
    location_name = get_location_display_name(mobile_attendance)

    if not geofence_required or (center_lat == 0 and center_lon == 0):
        return {
            "inside": True,
            "distance_m": 0.0,
            "geofence_result": "Not Required",
            "location_name": location_name,
            "center_lat": center_lat,
            "center_lon": center_lon,
            "radius_m": radius_m,
        }

    if radius_m <= 0:
        radius_m = 200.0

    inside, distance_m = is_within_radius(employee_lat, employee_lon, center_lat, center_lon, radius_m)
    return {
        "inside": inside,
        "distance_m": round(distance_m, 1),
        "geofence_result": "Inside" if inside else "Outside",
        "location_name": location_name,
        "center_lat": center_lat,
        "center_lon": center_lon,
        "radius_m": radius_m,
    }


def format_display_time(dt) -> str:
    if not dt:
        return "N/A"
    try:
        return format_time(dt)
    except Exception:
        return str(dt)


def format_display_date(dt) -> str:
    if not dt:
        return formatdate(today())
    try:
        return formatdate(getdate(dt))
    except Exception:
        return formatdate(today())


def start_location_request(conv: Any, context: dict[str, Any], log_type: str) -> OutboundMessage:
    employee = context.get("employee") or ""
    eligibility = get_attendance_eligibility(employee, user_id=context.get("user"))
    if not eligibility.get("eligible"):
        return OutboundMessage(body_text=eligibility.get("reason") or "Attendance is not available.")

    state = get_today_checkin_state(employee)
    if log_type == "IN":
        if state.get("checked_in_open"):
            in_time = format_display_time(state.get("last_in_time"))
            return build_button_message(
                f"ℹ️ You are already checked in today.\n\nCheck-In Time: *{in_time}*",
                [
                    {"id": "svc_att_today", "title": "Today's Attendance"},
                    {"id": "svc_main_menu", "title": "Main Menu"},
                ],
            )
        intent = "att_checkin"
        action_label = "Check-In"
    else:
        if not state.get("has_in_today"):
            return OutboundMessage(body_text="Please check in first before checking out.")
        if state.get("checked_out_today") and not state.get("checked_in_open"):
            out_time = format_display_time(state.get("last_out_time"))
            return build_button_message(
                f"ℹ️ You are already checked out today.\n\nCheck-Out Time: *{out_time}*",
                [
                    {"id": "svc_att_today", "title": "Today's Attendance"},
                    {"id": "svc_main_menu", "title": "Main Menu"},
                ],
            )
        intent = "att_checkout"
        action_label = "Check-Out"

    settings = get_whatsapp_attendance_settings()
    draft = {
        "flow": "att_location",
        "step": "awaiting_location",
        "log_type": log_type,
        "pending_started_at": str(now_datetime()),
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent=intent,
        draft_payload=json.dumps(draft),
    )
    body = (
        f"Tap the *Send location* button below to share your *current GPS location* "
        f"for {action_label}.\n\n"
        f"Important: choose *Send your current location* — do not pick a place "
        f"from the map or drop a pin.\n\n"
        f"_{settings['privacy_notice']}_"
    )
    return build_live_location_request_message(body)


def handle_attendance_flow_message(conv: Any, text: str, context: dict[str, Any]) -> OutboundMessage:
    """Handle text/button replies during attendance exception or retry flows."""
    draft = json.loads(conv.draft_payload or "{}")
    step = draft.get("step", "")
    clean = (text or "").strip()

    if clean.lower() in ("cancel", "menu", "main menu"):
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        return OutboundMessage(body_text="Attendance cancelled. Type *menu* for main menu.")

    if step == "awaiting_exception_reason":
        reason = _match_exception_reason(clean)
        if not reason:
            return OutboundMessage(body_text=_exception_reason_prompt())
        draft["exception_reason"] = reason
        if clean.startswith("att_exc_"):
            return _submit_exception_request(conv, context, draft)
        draft["step"] = "awaiting_exception_confirm"
        update_conversation(conv, draft_payload=json.dumps(draft))
        return OutboundMessage(
            body_text=f"Submit geofence exception request for *{reason}*?\n\nType *yes* to confirm or *cancel*."
        )

    if step == "awaiting_exception_confirm" and clean.lower() in ("yes", "y", "confirm"):
        return _submit_exception_request(conv, context, draft)

    if step == "awaiting_location":
        return OutboundMessage(
            body_text="Please share your location using WhatsApp's location share (Attach → Location), not typed text."
        )

    return OutboundMessage(body_text="Type *menu* to return to the main menu.")


def _match_exception_reason(text: str) -> str:
    low = text.lower().strip()
    mapping = {
        "1": "Field Visit",
        "field visit": "Field Visit",
        "2": "Official Travel",
        "official travel": "Official Travel",
        "3": "Assigned Meeting",
        "assigned meeting": "Assigned Meeting",
        "4": "Temporary Duty Location",
        "temporary duty": "Temporary Duty Location",
        "5": "Worksite Visit",
        "worksite visit": "Worksite Visit",
        "6": "Location/GPS Problem",
        "gps problem": "Location/GPS Problem",
        "location/gps problem": "Location/GPS Problem",
        "7": "Other",
        "other": "Other",
        "att_exc_field": "Field Visit",
        "att_exc_travel": "Official Travel",
        "att_exc_meeting": "Assigned Meeting",
        "att_exc_duty": "Temporary Duty Location",
        "att_exc_worksite": "Worksite Visit",
        "att_exc_gps": "Location/GPS Problem",
        "att_exc_other": "Other",
    }
    return mapping.get(low, "")


def _exception_reason_prompt() -> str:
    lines = ["Select exception reason (reply with number or name):\n"]
    for idx, (label, _) in enumerate(EXCEPTION_REASONS, 1):
        lines.append(f"{idx}. {label}")
    return "\n".join(lines)


def process_inbound_location(
    identity: Any,
    location: dict[str, Any],
    message_id: str = "",
    trace_id: str = "",
    wa_id: str = "",
    context_message_id: str = "",
) -> Optional[OutboundMessage]:
    from ai_workplace.context.resolver import get_user_context
    from ai_workplace.conversation.manager import get_or_create_conversation

    context = get_user_context(identity)
    if not context.get("allowed_services"):
        return OutboundMessage(body_text="This service is not available for your account.")

    conv = get_or_create_conversation(identity, wa_id=wa_id or "", trace_id=trace_id or "")
    update_conversation(conv, last_message_id=message_id)

    intent = conv.current_intent or ""
    if (conv.current_state or "") != ConversationState.PROCESSING or intent not in ATTENDANCE_INTENTS:
        return OutboundMessage(
            body_text=(
                "Location received, but no attendance check-in/out is pending.\n"
                "Start *Check In* or *Check Out* from the Attendance menu first."
            )
        )

    try:
        draft = json.loads(conv.draft_payload or "{}")
    except Exception:
        draft = {}

    if draft.get("step") != "awaiting_location":
        return OutboundMessage(body_text="Location is not expected at this step. Type *menu* for main menu.")

    ok, expiry_msg = validate_pending_request(draft)
    if not ok:
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        return OutboundMessage(body_text=expiry_msg)

    if is_duplicate_whatsapp_message(message_id):
        return OutboundMessage(body_text="This location was already processed.")

    live_ok, live_msg = validate_live_location_share(location, draft, context_message_id)
    if not live_ok:
        return build_button_message(
            live_msg,
            [
                {"id": "svc_att_retry_location", "title": "Try Again"},
                {"id": "svc_main_menu", "title": "Main Menu"},
            ],
        )

    lat = location.get("latitude")
    lon = location.get("longitude")
    if lat is None or lon is None:
        return OutboundMessage(body_text="We couldn't read your location. Please try sharing it again.")

    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return OutboundMessage(body_text="Invalid location received. Please share your location again.")

    employee = context.get("employee") or ""
    eligibility = get_attendance_eligibility(employee, user_id=context.get("user"))
    if not eligibility.get("eligible"):
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        return OutboundMessage(body_text=eligibility.get("reason") or "Attendance is not available.")

    mobile_attendance = eligibility.get("mobile_attendance")
    geofence = validate_geofence(lat_f, lon_f, mobile_attendance)
    log_type = draft.get("log_type") or ("IN" if intent == "att_checkin" else "OUT")

    if not geofence["inside"]:
        draft.update({
            "latitude": lat_f,
            "longitude": lon_f,
            "location_name": location.get("location_name") or "",
            "location_address": location.get("location_address") or "",
            "distance_m": geofence["distance_m"],
            "assigned_location": geofence["location_name"],
            "log_type": log_type,
        })
        if mobile_attendance and mobile_attendance.get("allow_outside_geofence_exception"):
            draft["step"] = "awaiting_exception_reason"
            update_conversation(conv, current_intent="att_exception", draft_payload=json.dumps(draft))
            dist_km = geofence["distance_m"] / 1000 if geofence["distance_m"] >= 1000 else None
            dist_text = f"{dist_km:.1f} km" if dist_km else f"{geofence['distance_m']:.0f} m"
            return build_button_message(
                (
                    f"⚠️ You appear to be outside your assigned attendance location.\n\n"
                    f"Assigned Location:\n*{geofence['location_name']}*\n\n"
                    f"Distance:\n*{dist_text}*\n\n"
                    f"Please share your location again or request an attendance exception."
                ),
                [
                    {"id": "svc_att_retry_location", "title": "Share Location Again"},
                    {"id": "svc_att_request_exception", "title": "Request Exception"},
                    {"id": "svc_main_menu", "title": "Main Menu"},
                ],
            )
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        dist_km = geofence["distance_m"] / 1000 if geofence["distance_m"] >= 1000 else None
        dist_text = f"{dist_km:.1f} km" if dist_km else f"{geofence['distance_m']:.0f} m"
        return OutboundMessage(
            body_text=(
                f"⚠️ You are outside your assigned attendance location ({geofence['location_name']}).\n"
                f"Distance: {dist_text}\n\nContact HR for assistance."
            )
        )

    try:
        checkin_name = create_whatsapp_checkin(
            employee=employee,
            log_type=log_type,
            latitude=lat_f,
            longitude=lon_f,
            location_name=location.get("location_name") or geofence["location_name"],
            location_address=location.get("location_address") or "",
            message_id=message_id,
            mobile_attendance=mobile_attendance or {},
            geofence=geofence,
            context=context,
        )
    except frappe.ValidationError as exc:
        update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
        return OutboundMessage(body_text=str(exc))
    except Exception:
        frappe.log_error(title="WhatsApp attendance checkin failed", message=frappe.get_traceback())
        return build_button_message(
            "We couldn't complete your attendance due to a temporary system issue.\n\nYour attendance has not been recorded.",
            [
                {"id": "svc_att_checkin" if log_type == "IN" else "svc_att_checkout", "title": "Try Again"},
                {"id": "svc_contact_hr", "title": "Contact HR"},
            ],
        )

    update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
    server_time = now_datetime()
    if log_type == "IN":
        body = (
            f"✅ *Check-In Successful*\n\n"
            f"Time: *{format_display_time(server_time)}*\n"
            f"Date: *{format_display_date(server_time)}*\n"
            f"Location: *{geofence['location_name']}*"
        )
    else:
        state_after = get_today_checkin_state(employee)
        body = (
            f"✅ *Check-Out Successful*\n\n"
            f"Check-In: *{format_display_time(state_after.get('last_in_time'))}*\n"
            f"Check-Out: *{format_display_time(server_time)}*\n\n"
            f"Have a safe journey."
        )
    return build_button_message(
        body,
        [
            {"id": "svc_att_today", "title": "Today's Attendance"},
            {"id": "svc_main_menu", "title": "Main Menu"},
        ],
    )


def create_whatsapp_checkin(
    *,
    employee: str,
    log_type: str,
    latitude: float,
    longitude: float,
    location_name: str,
    location_address: str,
    message_id: str,
    mobile_attendance: dict | None,
    geofence: dict,
    context: dict,
) -> str:
    server_time = now_datetime()

    state = get_today_checkin_state(employee)
    if log_type == "IN" and state.get("checked_in_open"):
        frappe.throw("You are already checked in today.")
    if log_type == "OUT" and not state.get("has_in_today"):
        frappe.throw("Please check in first before checking out.")
    if log_type == "OUT" and state.get("checked_out_today") and not state.get("checked_in_open"):
        frappe.throw("You are already checked out today.")

    if message_id and frappe.db.exists("Employee Checkin", {"custom_whatsapp_message_id": message_id}):
        existing = frappe.db.get_value("Employee Checkin", {"custom_whatsapp_message_id": message_id}, "name")
        return existing

    prev_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        doc = frappe.new_doc("Employee Checkin")
        doc.employee = employee
        doc.log_type = log_type
        doc.time = server_time
        doc.latitude = latitude
        doc.longitude = longitude
        doc.device_id = f"WhatsApp:{message_id or 'manual'}"

        if frappe.db.has_column("Employee Checkin", "date"):
            doc.date = getdate(server_time)
        if frappe.db.has_column("Employee Checkin", "location") and location_address:
            doc.location = location_address
        elif frappe.db.has_column("Employee Checkin", "location") and location_name:
            doc.location = location_name

        project = frappe.db.get_value("Employee", employee, "project")
        if project and frappe.db.has_column("Employee Checkin", "project"):
            doc.project = project

        _set_if_column(doc, "custom_log_from", "WhatsApp")
        _set_if_column(doc, "custom_whatsapp_message_id", message_id)
        _set_if_column(doc, "custom_server_received_at", server_time)
        _set_if_column(doc, "custom_distance_from_work_location", geofence.get("distance_m"))
        _set_if_column(doc, "custom_geofence_result", geofence.get("geofence_result"))
        _set_if_column(doc, "custom_assigned_mobile_attendance", (mobile_attendance or {}).get("name"))

        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    finally:
        frappe.set_user(prev_user)


def _set_if_column(doc: Any, fieldname: str, value: Any) -> None:
    if value in (None, "") or not frappe.db.has_column("Employee Checkin", fieldname):
        return
    doc.set(fieldname, value)


def _submit_exception_request(conv: Any, context: dict[str, Any], draft: dict) -> OutboundMessage:
    employee = context.get("employee") or ""
    server_time = now_datetime()
    reason = draft.get("exception_reason") or "Other"
    log_type = draft.get("log_type") or "IN"

    prev_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        doc = frappe.new_doc("Attendance Request")
        doc.employee = employee
        doc.from_date = getdate(server_time)
        doc.to_date = getdate(server_time)
        doc.reason = "On Duty"
        doc.explanation = f"WhatsApp geofence exception: {reason} ({log_type})"
        doc.company = frappe.db.get_value("Employee", employee, "company")

        if frappe.db.has_column("Attendance Request", "from_time"):
            doc.from_time = server_time.strftime("%H:%M:%S")
        if frappe.db.has_column("Attendance Request", "to_time"):
            doc.to_time = server_time.strftime("%H:%M:%S")

        _set_if_column_ar(doc, "custom_geofence_exception", 1)
        _set_if_column_ar(doc, "custom_exception_reason", reason)
        _set_if_column_ar(doc, "custom_checkin_latitude", draft.get("latitude"))
        _set_if_column_ar(doc, "custom_checkin_longitude", draft.get("longitude"))
        _set_if_column_ar(doc, "custom_whatsapp_message_id", draft.get("whatsapp_message_id", ""))

        project = frappe.db.get_value("Employee", employee, "project")
        if project and frappe.db.has_column("Attendance Request", "project"):
            doc.project = project

        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        req_name = doc.name
    except Exception:
        frappe.log_error(title="WhatsApp attendance exception failed", message=frappe.get_traceback())
        return OutboundMessage(body_text="Could not submit exception request. Please contact HR.")
    finally:
        frappe.set_user(prev_user)

    update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=None, draft_payload=None)
    return OutboundMessage(
        body_text=(
            f"✅ Exception request submitted: *{req_name}*\n"
            f"Reason: {reason}\n"
            "Status: Pending HR/Supervisor Review\n\n"
            "Your attendance was not marked automatically."
        )
    )


def _set_if_column_ar(doc: Any, fieldname: str, value: Any) -> None:
    if value in (None, "") or not frappe.db.has_column("Attendance Request", fieldname):
        return
    doc.set(fieldname, value)


def handle_attendance_menu_action(conv: Any, context: dict[str, Any], svc_key: str) -> OutboundMessage:
    if svc_key == "att_checkin":
        return start_location_request(conv, context, "IN")
    if svc_key == "att_checkout":
        return start_location_request(conv, context, "OUT")
    if svc_key == "att_retry_location":
        draft = json.loads(conv.draft_payload or "{}")
        log_type = draft.get("log_type") or "IN"
        return start_location_request(conv, context, log_type)
    if svc_key == "att_request_exception":
        draft = json.loads(conv.draft_payload or "{}")
        draft["step"] = "awaiting_exception_reason"
        update_conversation(conv, current_intent="att_exception", draft_payload=json.dumps(draft))
        return OutboundMessage(body_text=_exception_reason_prompt())
    return OutboundMessage(body_text="Unknown attendance action.")
