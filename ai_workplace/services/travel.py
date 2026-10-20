"""
ai_workplace/services/travel.py
─────────────────────────────────
Travel & Claims self-service for WhatsApp:
- trv_approved: Approved travel authorisations
- trv_upcoming: Upcoming scheduled travel
- trv_claim_status: Employee expense claim status
- trv_vehicle_info: Employee vehicle / commute details
- trv_sop: Travel SOP / DSA policy PDF
- trv_problem: Redirect to confidential concern report
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Optional

import frappe
from frappe import _
from frappe.utils import flt, formatdate, get_first_day, get_last_day, getdate, today

from ai_workplace.conversation.manager import update_conversation
from ai_workplace.conversation.state import ConversationState
from ai_workplace.services.response_helpers import wrap_with_parent_menu
from ai_workplace.whatsapp.interactive import build_yes_no_buttons
from ai_workplace.whatsapp.outbound import OutboundMessage

TRAVEL_SOP_KEYWORDS = ("travel", "dsa", "daily subsistence", "field visit", "ta/da")
EXCLUDED_TRAVEL_STATES = ("Rejected", "Cancelled")
MAX_TRAVEL_ROWS = 8
MAX_CLAIM_ROWS = 8


def get_employee_monthly_travel_days(employee_id: Optional[str]) -> dict[str, Any]:
    """Return travel days used and remaining for the current calendar month."""
    result: dict[str, Any] = {
        "has_travel_days_policy": False,
        "reason": "",
        "message": "",
    }
    try:
        if not employee_id or not _employee_exists(employee_id):
            result.update(reason="NO_EMPLOYEE", message="No active employee record was found.")
            return result

        reference_date = getdate(today())
        assignment = frappe.get_all(
            "Expense Claim Structure Assigment",
            filters={"employee": employee_id, "from_date": ["<=", reference_date]},
            fields=["name", "expense_claim_structure", "from_date", "travel_days"],
            order_by="from_date desc, creation desc",
            limit=1,
        )
        if not assignment:
            result.update(
                reason="NO_ASSIGNED_POLICY",
                message="No active travel or expense claim policy is assigned to your profile.",
            )
            return result

        assignment = assignment[0]
        month_start = get_first_day(reference_date)
        month_end = get_last_day(reference_date)
        used_days = frappe.db.sql(
            """
            SELECT IFNULL(SUM(total_days), 0)
            FROM `tabEmployee Expense Claim`
            WHERE docstatus = 1
              AND month_end_date BETWEEN %s AND %s
              AND employee = %s
            """,
            (month_start, month_end, employee_id),
        )[0][0]
        allowed_days = flt(assignment.get("travel_days"))
        used_days = flt(used_days)

        return {
            "has_travel_days_policy": True,
            "reason": "",
            "message": "",
            "month": reference_date.strftime("%B %Y"),
            "allowed_days": allowed_days,
            "used_days": used_days,
            "remaining_days": max(0, allowed_days - used_days),
            "assignment_name": assignment.get("name"),
            "assignment_effective_from": str(assignment.get("from_date") or ""),
            "policy_name": assignment.get("expense_claim_structure") or "",
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Monthly Travel Days Tool Error")
        result.update(reason="LOOKUP_FAILED", message="Your monthly travel-day summary could not be retrieved right now.")
        return result


def get_employee_city_dsa(
    employee_id: Optional[str], query: str = "", travel_date: Optional[str] = None
) -> dict[str, Any]:
    """Resolve an employee's DSA for a city using the active assignment and city level."""
    result: dict[str, Any] = {
        "has_city_dsa": False,
        "reason": "",
        "message": "",
    }
    try:
        if not employee_id or not _employee_exists(employee_id):
            result.update(reason="NO_EMPLOYEE", message="No active employee record was found.")
            return result

        city_name = _find_expense_claim_city(query)
        if not city_name:
            requested_city = _extract_requested_city(query)
            if requested_city:
                result.update(
                    reason="CITY_NOT_CONFIGURED",
                    message=(
                        f"{requested_city} is not configured in the Expense Claim City list. "
                        "Please ask HR to add the city and its DSA level."
                    ),
                    city=requested_city,
                )
                return result
            result.update(
                reason="CITY_NOT_PROVIDED",
                message="Please tell me the city for which you need the DSA amount.",
            )
            return result

        effective_date = getdate(travel_date) if travel_date else getdate(today())
        assignment = frappe.get_all(
            "Expense Claim Structure Assigment",
            filters={"employee": employee_id, "from_date": ["<=", effective_date]},
            fields=["name", "expense_claim_structure", "from_date"],
            order_by="from_date desc, creation desc",
            limit=1,
        )
        if not assignment:
            result.update(
                reason="NO_ASSIGNED_POLICY",
                message="No active travel or expense claim policy is assigned to your profile.",
                city=city_name,
            )
            return result

        assignment = assignment[0]
        structure_name = assignment.get("expense_claim_structure")
        if not structure_name or not frappe.db.exists("Expense Claim Structure", structure_name):
            result.update(
                reason="STRUCTURE_NOT_FOUND",
                message="Your assigned expense claim structure could not be found.",
                city=city_name,
            )
            return result

        level_row = frappe.db.sql(
            """
            SELECT level
            FROM `tabExpense Claim City Table`
            WHERE parent = %s AND effective_from <= %s
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (city_name, effective_date),
            as_dict=True,
        )
        city_level = (
            level_row[0].get("level")
            if level_row
            else frappe.db.get_value("Expense Claim City", city_name, "level")
        )
        if not city_level:
            result.update(
                reason="CITY_LEVEL_NOT_FOUND",
                message="No DSA level is configured for this city on the requested date.",
                city=city_name,
            )
            return result

        amount = frappe.db.get_value(
            "Expense Claim Structure DSA",
            {"parent": structure_name, "level": city_level},
            "amount",
        )
        if amount is None:
            result.update(
                reason="DSA_RATE_NOT_FOUND",
                message="Your assigned expense claim structure has no DSA rate for this city's level.",
                city=city_name,
                city_level=city_level,
                policy_name=structure_name,
            )
            return result

        return {
            "has_city_dsa": True,
            "reason": "",
            "message": "",
            "city": city_name,
            "travel_date": str(effective_date),
            "city_level": city_level,
            "dsa_amount": flt(amount),
            "currency": frappe.db.get_default("currency") or "PKR",
            "assignment_name": assignment.get("name"),
            "policy_name": structure_name,
            "assignment_effective_from": str(assignment.get("from_date") or ""),
        }
    except Exception:
        frappe.log_error(frappe.get_traceback(), "City DSA Tool Error")
        result.update(reason="LOOKUP_FAILED", message="The city DSA amount could not be retrieved right now.")
        return result


def _find_expense_claim_city(query: str) -> Optional[str]:
    """Return the configured city named in a natural-language question."""
    normalized_query = re.sub(r"\s+", " ", (query or "").casefold()).strip()
    if not normalized_query:
        return None

    cities = frappe.get_all("Expense Claim City", fields=["city"])
    for row in sorted(cities, key=lambda item: len(item.get("city") or ""), reverse=True):
        city = (row.get("city") or "").strip()
        if city and re.search(r"(?<!\w)" + re.escape(city.casefold()) + r"(?!\w)", normalized_query):
            return city
    return None


def _extract_requested_city(query: str) -> Optional[str]:
    """Extract a city written after the usual city-DSA question phrases."""
    match = re.search(
        r"\b(?:city\s+|for\s+(?:city\s+)?|in\s+|at\s+|to\s+|of\s+)([a-z][a-z .'-]{1,60})",
        query or "",
        re.IGNORECASE,
    )
    if not match:
        return None

    city = re.split(r"\b(?:on|for|today|tomorrow)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
    city = city.strip(" .,!?:;-'\"")
    return city.title() if city else None


def get_employee_travel_expense_policy_details(employee_id: Optional[str]) -> dict[str, Any]:
    """Fetch the employee's assigned Expense Claim Structure policy/rates."""
    res: dict[str, Any] = {
        "has_travel_expense_policy": False,
        "reason": "NO_ASSIGNED_POLICY",
        "message": "No assigned travel or expense claim policy was found for this employee. Please contact HR.",
    }
    try:
        if not employee_id or not _employee_exists(employee_id):
            res["reason"] = "NO_EMPLOYEE"
            return res

        today_date = getdate(today())
        assignments = frappe.get_all(
            "Expense Claim Structure Assigment",
            filters={
                "employee": employee_id,
                "from_date": ["<=", today_date],
            },
            fields=[
                "name",
                "expense_claim_structure",
                "from_date",
                "dsa_per_month",
                "travel_days",
                "total_dsa_allowed",
                "project",
                "contract",
                "province",
            ],
            order_by="from_date desc, creation desc",
            limit=1,
        )
        if not assignments:
            return res

        assignment = assignments[0]
        structure_name = assignment.get("expense_claim_structure")
        if not structure_name or not frappe.db.exists("Expense Claim Structure", structure_name):
            res["reason"] = "STRUCTURE_NOT_FOUND"
            res["assignment_name"] = assignment.get("name")
            return res

        structure = frappe.get_doc("Expense Claim Structure", structure_name)
        res.update(
            {
                "has_travel_expense_policy": True,
                "reason": "",
                "message": "",
                "assignment_name": assignment.get("name"),
                "policy_name": structure_name,
                "effective_from": str(assignment.get("from_date") or ""),
                "project": assignment.get("project") or "",
                "contract": assignment.get("contract") or "",
                "province": assignment.get("province") or "",
                "monthly_limits": {
                    "dsa_ta_per_month": assignment.get("dsa_per_month") or 0,
                    "total_dsa_ta_allowed": assignment.get("total_dsa_allowed") or 0,
                    "travel_days": assignment.get("travel_days") or 0,
                },
                "expense_percentages": {
                    "accommodation_percent": structure.get("accoumudation") or 0,
                    "breakfast_percent": structure.get("brakfast") or 0,
                    "lunch_percent": structure.get("lunch") or 0,
                    "dinner_percent": structure.get("dinner") or 0,
                    "others_percent": structure.get("others") or 0,
                },
                "same_day_trip": {
                    "hours_threshold": structure.get("hours") or 0,
                    "amount_percent": structure.get("amount") or 0,
                    "same_day_dsa": bool(structure.get("same_day_dsa")),
                },
                "flags": {
                    "actual_amount": bool(structure.get("actual_amount")),
                    "group_travel": bool(structure.get("group_travel")),
                    "old_logic": bool(structure.get("old_logic")),
                },
                "personal_vehicle_amount_per_km": structure.get("personal_vehicle_amount_per_km") or 0,
                "hardship_and_tribal_amount": structure.get("hard_ship_and_tribal_amount") or 0,
                "dsa_days_limit": structure.get("dsa_days_limit") or 0,
                "dsa_rates": [
                    {
                        "level": row.get("level"),
                        "amount": row.get("amount") or 0,
                    }
                    for row in structure.get("dsa", [])
                    if row.get("level")
                ],
                "travel_rates": [
                    {
                        "type": row.get("type"),
                        "amount_per_day": row.get("amount") or 0,
                        "rate_per_km": row.get("rate_per_km") or 0,
                    }
                    for row in structure.get("travel", [])
                    if row.get("type")
                ],
            }
        )
        return res
    except Exception as exc:
        frappe.log_error("Travel/Expense Policy Tool Error", str(exc))
        return res


def get_approved_travel_requests(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Return approved travel authorisation forms for the employee."""
    if not employee_id or not _employee_exists(employee_id):
        return []

    parents = frappe.db.get_all(
        "Travel Authorisation Request Form",
        filters={
            "employee": employee_id,
            "docstatus": ["!=", 2],
            "workflow_state": "Approved",
        },
        fields=["name", "purpose_of_travel", "posting_date", "project"],
        order_by="posting_date desc",
        limit=MAX_TRAVEL_ROWS,
    )
    return [_enrich_travel_request(row) for row in parents]


def get_upcoming_travel_trips(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Return upcoming travel legs (from_date >= today) for the employee."""
    if not employee_id or not _employee_exists(employee_id):
        return []

    curr = today()
    rows = frappe.db.sql(
        """
        SELECT
            p.name AS request_name,
            p.purpose_of_travel,
            COALESCE(
                NULLIF(p.workflow_state, ''),
                CASE p.docstatus
                    WHEN 0 THEN 'Draft'
                    WHEN 1 THEN 'Submitted'
                    ELSE 'Unknown'
                END
            ) AS workflow_state,
            t.from_date,
            t.to_date,
            t.source,
            t.destination,
            t.mode_of_travel,
            t.vehicle_type
        FROM `tabTravel Authorisation Request Form Table` t
        INNER JOIN `tabTravel Authorisation Request Form` p ON p.name = t.parent
        WHERE p.employee = %(employee)s
          AND p.docstatus != 2
          AND IFNULL(p.workflow_state, '') NOT IN %(excluded)s
          AND t.from_date >= %(today)s
        ORDER BY t.from_date ASC
        LIMIT %(limit)s
        """,
        {
            "employee": employee_id,
            "today": curr,
            "excluded": tuple(EXCLUDED_TRAVEL_STATES),
            "limit": MAX_TRAVEL_ROWS,
        },
        as_dict=True,
    )
    return rows or []


def get_travel_expense_claims(employee_id: Optional[str]) -> list[dict[str, Any]]:
    """Return recent employee expense claims linked to travel."""
    if not employee_id or not _employee_exists(employee_id):
        return []

    claims = frappe.db.get_all(
        "Employee Expense Claim",
        filters={"employee": employee_id, "docstatus": ["!=", 2]},
        fields=[
            "name",
            "posting_date",
            "purpose_of_travel",
            "status",
            "custom_status",
            "overall_status",
            "grand_total",
        ],
        order_by="posting_date desc",
        limit=MAX_CLAIM_ROWS,
    )
    for claim in claims:
        claim["display_status"] = _resolve_claim_status(claim)
    return claims


def get_employee_vehicle_info(employee_id: Optional[str]) -> dict[str, Any]:
    """Return commute / vehicle fields from the Employee record."""
    empty = {
        "type_of_commute": "",
        "vehicle_number": "",
        "vehicle_details": "",
        "pass_number": "",
        "upcoming_vehicle_types": [],
    }
    if not employee_id or not _employee_exists(employee_id):
        return empty

    emp = frappe.db.get_value(
        "Employee",
        employee_id,
        ["type_of_commute", "vehicle_number", "vehicle_informationcolormodelbrand", "pass_number"],
        as_dict=True,
    ) or {}

    vehicle_types = frappe.db.sql(
        """
        SELECT DISTINCT t.vehicle_type
        FROM `tabTravel Authorisation Request Form Table` t
        INNER JOIN `tabTravel Authorisation Request Form` p ON p.name = t.parent
        WHERE p.employee = %(employee)s
          AND p.docstatus != 2
          AND IFNULL(p.workflow_state, '') = 'Approved'
          AND IFNULL(t.vehicle_type, '') != ''
          AND t.from_date >= %(today)s
        ORDER BY t.from_date ASC
        LIMIT 5
        """,
        {"employee": employee_id, "today": today()},
    )
    upcoming_types = [row[0] for row in vehicle_types if row and row[0]]

    return {
        "type_of_commute": emp.get("type_of_commute") or "",
        "vehicle_number": emp.get("vehicle_number") or "",
        "vehicle_details": emp.get("vehicle_informationcolormodelbrand") or "",
        "pass_number": emp.get("pass_number") or "",
        "upcoming_vehicle_types": upcoming_types,
    }


def find_travel_sop_policy() -> Optional[dict[str, Any]]:
    """Find the most recent published travel / DSA policy notification."""
    if not getattr(frappe, "db", None):
        return None

    today_date = getdate(today())
    records = frappe.get_all(
        "System Notifications",
        filters={
            "is_published": 1,
            "notification_type": "Policy",
            "published_from": ["<=", today_date],
        },
        fields=[
            "name",
            "subject",
            "policy_document",
            "published_from",
            "published_to",
            "version",
        ],
        order_by="published_from desc",
        limit=50,
    )

    for rec in records:
        if rec.get("published_to") and getdate(rec["published_to"]) < today_date:
            continue
        if not rec.get("policy_document"):
            continue
        subject = (rec.get("subject") or "").lower()
        if any(keyword in subject for keyword in TRAVEL_SOP_KEYWORDS):
            return rec

    for rec in records:
        if rec.get("published_to") and getdate(rec["published_to"]) < today_date:
            continue
        if rec.get("policy_document"):
            return rec
    return None


def load_policy_pdf_bytes(policy_document_url: str) -> tuple[bytes, str]:
    """Read policy PDF bytes from a File attachment URL."""
    file_doc = frappe.get_doc("File", {"file_url": policy_document_url})
    path = file_doc.get_full_path()
    with open(path, "rb") as handle:
        pdf_bytes = handle.read()
    filename = file_doc.file_name or os.path.basename(policy_document_url) or "Travel_SOP.pdf"
    return pdf_bytes, filename


def build_approved_travel_response(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    employee_id = context.get("employee")
    requests = get_approved_travel_requests(employee_id)

    if lang == "Urdu":
        if not requests:
            return "✅ *منظور شدہ سفر*\n\nفی الحال کوئی منظور شدہ سفری درخواست نہیں ملی۔"
        lines = [_format_approved_travel_block_ur(req) for req in requests]
        return "✅ *منظور شدہ سفر*\n\n" + "\n\n".join(lines)

    if lang == "Roman Urdu":
        if not requests:
            return "✅ *Approved Travel*\n\nFilhaal koi approved travel request nahi mili."
        lines = [_format_approved_travel_block_ru(req) for req in requests]
        return "✅ *Approved Travel*\n\n" + "\n\n".join(lines)

    if not requests:
        return "✅ *Approved Travel*\n\nYou have no approved travel authorisations on record."
    lines = [_format_approved_travel_block_en(req) for req in requests]
    return "✅ *Approved Travel*\n\n" + "\n\n".join(lines)


def build_upcoming_travel_response(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    employee_id = context.get("employee")
    trips = get_upcoming_travel_trips(employee_id)

    if lang == "Urdu":
        if not trips:
            return "🔜 *آنے والا سفر*\n\nآج سے آگے کوئی شیڈول شدہ سفر نہیں ملا۔"
        lines = [_format_upcoming_trip_block_ur(trip) for trip in trips]
        return "🔜 *آنے والا سفر*\n\n" + "\n\n".join(lines)

    if lang == "Roman Urdu":
        if not trips:
            return "🔜 *Upcoming Travel*\n\nAaj se aage koi scheduled travel nahi mila."
        lines = [_format_upcoming_trip_block_ru(trip) for trip in trips]
        return "🔜 *Upcoming Travel*\n\n" + "\n\n".join(lines)

    if not trips:
        return "🔜 *Upcoming Travel*\n\nYou have no scheduled travel from today onwards."
    lines = [_format_upcoming_trip_block_en(trip) for trip in trips]
    return "🔜 *Upcoming Travel*\n\n" + "\n\n".join(lines)


def build_claim_status_response(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    employee_id = context.get("employee")
    claims = get_travel_expense_claims(employee_id)

    if lang == "Urdu":
        if not claims:
            return "🔄 *سفری کلیم کی صورتحال*\n\nکوئی سفری expense claim نہیں ملی۔"
        lines = [_format_claim_block_ur(claim) for claim in claims]
        return "🔄 *سفری کلیم کی صورتحال*\n\n" + "\n\n".join(lines)

    if lang == "Roman Urdu":
        if not claims:
            return "🔄 *Travel Claim Status*\n\nKoi travel expense claim nahi mili."
        lines = [_format_claim_block_ru(claim) for claim in claims]
        return "🔄 *Travel Claim Status*\n\n" + "\n\n".join(lines)

    if not claims:
        return "🔄 *Travel Claim Status*\n\nNo travel expense claims were found for your record."
    lines = [_format_claim_block_en(claim) for claim in claims]
    return "🔄 *Travel Claim Status*\n\n" + "\n\n".join(lines)


def build_vehicle_info_response(context: dict[str, Any]) -> str:
    lang = context.get("preferred_language", "English")
    employee_id = context.get("employee")
    info = get_employee_vehicle_info(employee_id)

    if lang == "Urdu":
        return _build_vehicle_info_ur(info)
    if lang == "Roman Urdu":
        return _build_vehicle_info_ru(info)
    return _build_vehicle_info_en(info)


def build_travel_sop_outbound(context: dict[str, Any]) -> OutboundMessage:
    """Send travel SOP policy PDF when available, otherwise a helpful text fallback."""
    lang = context.get("preferred_language", "English")
    policy = find_travel_sop_policy()

    if not policy or not policy.get("policy_document"):
        body = _travel_sop_not_found(lang)
        return wrap_with_parent_menu(body, context, "travel")

    try:
        pdf_bytes, filename = load_policy_pdf_bytes(policy["policy_document"])
    except Exception:
        frappe.log_error(title="WhatsApp travel SOP PDF failed", message=frappe.get_traceback())
        return wrap_with_parent_menu(_travel_sop_error(lang), context, "travel")

    subject = policy.get("subject") or "Travel SOP"
    version = policy.get("version")
    version_part = f" (v{version})" if version else ""
    caption = _travel_sop_caption(lang, subject, version_part)

    document = OutboundMessage(
        body_text=caption,
        document_caption=caption,
        document_bytes=pdf_bytes,
        document_filename=filename,
        document_mimetype="application/pdf",
    )
    menu = wrap_with_parent_menu("", context, "travel")
    document.follow_up = [menu]
    return document


def start_travel_problem_report(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Start confidential concern report flow for travel incidents."""
    from ai_workplace.services.concern_report import start_concern_report

    outbound = start_concern_report(conv, context)
    lang = context.get("preferred_language", "English")

    if lang == "Urdu":
        prefix = (
            "🚨 *سفری مسئلہ رپورٹ*\n\n"
            "سفری واقعات، DSA یا ٹرانسپورٹ سے متعلق مسائل یہاں رپورٹ کریں۔\n"
            "یہ رپورٹ خفیہ Concern workflow میں جائے گی۔\n"
        )
    elif lang == "Roman Urdu":
        prefix = (
            "🚨 *Travel Problem Report*\n\n"
            "Travel incidents, DSA ya transport se mutaliq masail yahan report karein.\n"
            "Yeh report confidential Concern workflow mein jayegi.\n"
        )
    else:
        prefix = (
            "🚨 *Travel Problem Report*\n\n"
            "Report travel incidents, DSA issues, or transport problems here.\n"
            "This will be handled through the confidential Concern workflow.\n"
        )

    outbound.body_text = f"{prefix}\n{outbound.body_text}"
    if outbound.interactive:
        interactive = dict(outbound.interactive)
        body = interactive.get("body") or {}
        if isinstance(body, dict) and body.get("text"):
            body = dict(body)
            body["text"] = f"{prefix}\n{body['text']}"
            interactive["body"] = body
            outbound.interactive = interactive
    return outbound


def _employee_exists(employee_id: str) -> bool:
    return bool(getattr(frappe, "db", None) and frappe.db.exists("Employee", employee_id))


def _enrich_travel_request(row: dict[str, Any]) -> dict[str, Any]:
    legs = frappe.get_all(
        "Travel Authorisation Request Form Table",
        filters={"parent": row["name"]},
        fields=["from_date", "to_date", "source", "destination", "mode_of_travel", "vehicle_type"],
        order_by="idx asc",
    )
    row["legs"] = legs
    return row


def _resolve_claim_status(claim: dict[str, Any]) -> str:
    workflow_state = frappe.db.get_value("Employee Expense Claim", claim["name"], "workflow_state")
    for candidate in (workflow_state, claim.get("overall_status"), claim.get("custom_status"), claim.get("status")):
        if candidate:
            return str(candidate)
    return "Unknown"


def _format_date(value: Any) -> str:
    if not value:
        return "—"
    return formatdate(getdate(value), "dd-MMM-YYYY")


def _format_approved_travel_block_en(req: dict[str, Any]) -> str:
    purpose = (req.get("purpose_of_travel") or "Travel").strip()
    project = req.get("project") or "—"
    lines = [f"📌 *{purpose}*", f"Ref: {req['name']} | Project: {project}"]
    for leg in req.get("legs") or []:
        route = f"{leg.get('source') or '?'} → {leg.get('destination') or '?'}"
        mode = leg.get("mode_of_travel") or "—"
        dates = f"{_format_date(leg.get('from_date'))} to {_format_date(leg.get('to_date'))}"
        lines.append(f"   • {dates}: {route} ({mode})")
    if not req.get("legs"):
        lines.append(f"   • Posted: {_format_date(req.get('posting_date'))}")
    return "\n".join(lines)


def _format_approved_travel_block_ru(req: dict[str, Any]) -> str:
    return _format_approved_travel_block_en(req)


def _format_approved_travel_block_ur(req: dict[str, Any]) -> str:
    return _format_approved_travel_block_en(req)


def _format_upcoming_trip_block_en(trip: dict[str, Any]) -> str:
    route = f"{trip.get('source') or '?'} → {trip.get('destination') or '?'}"
    mode = trip.get("mode_of_travel") or "—"
    vehicle = trip.get("vehicle_type") or ""
    vehicle_part = f" | Vehicle: {vehicle}" if vehicle else ""
    status = trip.get("workflow_state") or "Unknown"
    dates = f"{_format_date(trip.get('from_date'))} to {_format_date(trip.get('to_date'))}"
    purpose = (trip.get("purpose_of_travel") or "Travel").strip()
    return (
        f"📅 *{dates}*\n"
        f"   {route} ({mode}){vehicle_part}\n"
        f"   📊 Status: *{status}* | Ref: {trip.get('request_name')}\n"
        f"   {purpose[:80]}"
    )


def _format_upcoming_trip_block_ru(trip: dict[str, Any]) -> str:
    return _format_upcoming_trip_block_en(trip)


def _format_upcoming_trip_block_ur(trip: dict[str, Any]) -> str:
    return _format_upcoming_trip_block_en(trip)


def _format_claim_block_en(claim: dict[str, Any]) -> str:
    purpose = (claim.get("purpose_of_travel") or "Expense claim").strip()
    status = claim.get("display_status") or "—"
    posted = _format_date(claim.get("posting_date"))
    total = claim.get("grand_total")
    total_part = f" | Total: {total}" if total is not None else ""
    return f"📄 *{purpose[:60]}*\n   Ref: {claim['name']} | {posted}\n   Status: *{status}*{total_part}"


def _format_claim_block_ru(claim: dict[str, Any]) -> str:
    return _format_claim_block_en(claim)


def _format_claim_block_ur(claim: dict[str, Any]) -> str:
    return _format_claim_block_en(claim)


def _build_vehicle_info_en(info: dict[str, Any]) -> str:
    commute = info.get("type_of_commute") or "Not recorded"
    lines = ["🚙 *Vehicle / Commute Info*", "", f"Commute type: *{commute}*"]
    if info.get("vehicle_number"):
        lines.append(f"Vehicle number: {info['vehicle_number']}")
    if info.get("vehicle_details"):
        lines.append(f"Vehicle details: {info['vehicle_details']}")
    if info.get("pass_number"):
        lines.append(f"Pass number: {info['pass_number']}")
    upcoming = info.get("upcoming_vehicle_types") or []
    if upcoming:
        lines.append("")
        lines.append("Upcoming approved travel vehicle type(s):")
        for vehicle_type in upcoming:
            lines.append(f"   • {vehicle_type}")
    if commute in ("Own Car", "Own Bike") and not info.get("vehicle_number"):
        lines.append("")
        lines.append("💡 Update your vehicle details on the employee portal or contact HR.")
    else:
        lines.append("")
        lines.append("💡 For company-arranged transport or driver details, contact HR / Admin.")
    return "\n".join(lines)


def _build_vehicle_info_ru(info: dict[str, Any]) -> str:
    commute = info.get("type_of_commute") or "Record nahi"
    lines = ["🚙 *Vehicle / Commute Info*", "", f"Commute type: *{commute}*"]
    if info.get("vehicle_number"):
        lines.append(f"Vehicle number: {info['vehicle_number']}")
    if info.get("vehicle_details"):
        lines.append(f"Vehicle details: {info['vehicle_details']}")
    if info.get("pass_number"):
        lines.append(f"Pass number: {info['pass_number']}")
    upcoming = info.get("upcoming_vehicle_types") or []
    if upcoming:
        lines.append("")
        lines.append("Aane wale approved travel vehicle type(s):")
        for vehicle_type in upcoming:
            lines.append(f"   • {vehicle_type}")
    lines.append("")
    lines.append("💡 Company transport ya driver ki tafseel ke liye HR se rabta karein.")
    return "\n".join(lines)


def _build_vehicle_info_ur(info: dict[str, Any]) -> str:
    commute = info.get("type_of_commute") or "درج نہیں"
    lines = ["🚙 *گاڑی / سفر کی معلومات*", "", f"Commute type: *{commute}*"]
    if info.get("vehicle_number"):
        lines.append(f"Vehicle number: {info['vehicle_number']}")
    if info.get("vehicle_details"):
        lines.append(f"Vehicle details: {info['vehicle_details']}")
    if info.get("pass_number"):
        lines.append(f"Pass number: {info['pass_number']}")
    upcoming = info.get("upcoming_vehicle_types") or []
    if upcoming:
        lines.append("")
        lines.append("آنے والے منظور شدہ سفر کی گاڑی:")
        for vehicle_type in upcoming:
            lines.append(f"   • {vehicle_type}")
    lines.append("")
    lines.append("💡 کمپنی ٹرانسپورٹ یا ڈرائیور کی تفصیل کے لیے HR سے رابطہ کریں۔")
    return "\n".join(lines)


def _travel_sop_not_found(lang: str) -> str:
    if lang == "Urdu":
        return "📖 *Travel SOP*\n\nفی الحال کوئی Travel / DSA policy دستیاب نہیں۔ HR سے رابطہ کریں۔"
    if lang == "Roman Urdu":
        return "📖 *Travel SOP*\n\nFilhaal koi Travel / DSA policy available nahi. HR se rabta karein."
    return "📖 *Travel SOP*\n\nNo Travel / DSA policy document is currently available. Please contact HR."


def _travel_sop_error(lang: str) -> str:
    if lang == "Urdu":
        return "معذرت، Travel SOP PDF نہیں بھیجی جا سکی۔ دوبارہ کوشش کریں یا HR سے رابطہ کریں۔"
    if lang == "Roman Urdu":
        return "Maazrat, Travel SOP PDF send nahi ho saki. Dobara koshish karein ya HR se rabta karein."
    return "Sorry, we couldn't send the Travel SOP PDF. Please try again or contact HR."


def _travel_sop_caption(lang: str, subject: str, version_part: str) -> str:
    if lang == "Urdu":
        return f"📖 *{subject}*{version_part}"
    if lang == "Roman Urdu":
        return f"📖 *{subject}*{version_part}"
    return f"📖 *{subject}*{version_part}"


_DATE_HINT = "e.g. 01-Sep-2026 or 2026-09-01"
_CANCEL_WORDS = frozenset({"cancel", "menu", "stop", "exit", "back"})

TRAVEL_MODES = [
    {"id": "trv_mode_personal", "title": "Personal Vehicle"},
    {"id": "trv_mode_rented", "title": "Rented Vehicle"},
    {"id": "trv_mode_air", "title": "By Air"},
]


def start_travel_authorization(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    """Begin step-by-step Travel Authorisation Request workflow."""
    employee_id = context.get("employee") or conv.employee or ""
    if not employee_id:
        return wrap_with_parent_menu(
            _("Travel Authorisation request is only available for linked employees."),
            context,
            "travel",
        )

    # Validate Expense Claim Structure Assignment upfront
    has_assignment = frappe.db.exists("Expense Claim Structure Assigment", {"employee": employee_id})
    if not has_assignment:
        employee_name = context.get("full_name") or conv.employee or "your account"
        return wrap_with_parent_menu(
            _(
                "⚠️ *Travel Request Not Allowed*\n\n"
                "No active Expense Claim Structure Assignment was found for *{0}* in ERPNext.\n\n"
                "Please contact HR to assign an Expense Claim Structure before submitting travel authorisation requests."
            ).format(employee_name),
            context,
            "travel",
        )

    draft = {
        "step": "awaiting_purpose",
        "employee": employee_id,
    }
    update_conversation(
        conv,
        state=ConversationState.PROCESSING,
        current_intent="trv_apply",
        active_service="travel",
        draft_payload=json.dumps(draft),
    )

    header = _(
        "🚗 *Request Travel Authorisation*\n\n"
        "Submit a travel authorisation for approval step by step.\n\n"
        "Step 1 of 5 — Enter the *Purpose of Travel*\n"
        "(e.g., 'Field visit for project monitoring in Islamabad'):"
    )
    return OutboundMessage(body_text=header)


def handle_travel_authorization_message(
    conv: Any,
    message_text: str,
    context: dict[str, Any],
) -> OutboundMessage:
    """Process step-by-step inputs for Travel Authorisation Request."""
    draft = _load_draft(conv)
    step = draft.get("step", "")
    text = (message_text or "").strip()
    clean = text.lower()

    if clean in _CANCEL_WORDS:
        return _cancel_travel_flow(conv, context)

    if step == "awaiting_purpose":
        return _handle_travel_purpose(conv, context, draft, text)
    if step == "awaiting_mode":
        return _handle_travel_mode(conv, context, draft, text)
    if step == "awaiting_from_date":
        return _handle_travel_from_date(conv, context, draft, text)
    if step == "awaiting_to_date":
        return _handle_travel_to_date(conv, context, draft, text)
    if step == "awaiting_route":
        return _handle_travel_route(conv, context, draft, text)
    if step == "awaiting_confirm":
        return _handle_travel_confirm(conv, context, draft, text)

    return wrap_with_parent_menu(_("Something went wrong. Type 'menu' to start again."), context, "travel")


def _load_draft(conv: Any) -> dict[str, Any]:
    if not conv.draft_payload:
        return {}
    try:
        return json.loads(conv.draft_payload)
    except Exception:
        return {}


def _save_draft(conv: Any, draft: dict[str, Any]) -> None:
    update_conversation(conv, draft_payload=json.dumps(draft))


def _cancel_travel_flow(conv: Any, context: dict[str, Any]) -> OutboundMessage:
    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="travel",
        draft_payload=None,
    )
    return wrap_with_parent_menu(_("Travel Authorisation request cancelled."), context, "travel")


def _handle_travel_purpose(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    purpose = text.strip()
    if len(purpose) < 3:
        return OutboundMessage(body_text=_("Please enter a valid purpose (at least 3 characters)."))

    draft["purpose"] = purpose
    draft["step"] = "awaiting_mode"
    _save_draft(conv, draft)

    header = _(
        "✅ Purpose: *{0}*\n\n"
        "Step 2 of 5 — Select *Mode of Travel*:"
    ).format(purpose)

    buttons = [
        {"type": "reply", "reply": {"id": m["id"], "title": m["title"]}}
        for m in TRAVEL_MODES[:3]
    ]
    interactive = {
        "type": "button",
        "body": {"text": header},
        "action": {"buttons": buttons},
    }
    return OutboundMessage(body_text=header, interactive=interactive)


def _map_mode_of_travel(val: str) -> str:
    v = (val or "").lower().strip()
    if "air" in v or "flight" in v or "plane" in v or "trv_mode_air" in v:
        return "By Air"
    if "rent" in v or "taxi" in v or "cab" in v or "trv_mode_rented" in v:
        return "Rented Vehicle"
    return "Personal Vehicle"


def _resolve_travel_mode(text: str) -> str:
    clean = text.strip().lower()
    for m in TRAVEL_MODES:
        if clean == m["id"] or clean == m["title"].lower() or m["title"].lower() in clean or clean in m["title"].lower():
            return m["title"]
    return _map_mode_of_travel(text)


def _handle_travel_mode(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    mode = _resolve_travel_mode(text)

    draft["mode"] = mode
    draft["step"] = "awaiting_from_date"
    _save_draft(conv, draft)

    return OutboundMessage(
        body_text=_(
            "✅ Travel Mode: *{0}*\n\n"
            "Step 3 of 5 — Enter *From Date*\n"
            "Format: {1}"
        ).format(mode, _DATE_HINT)
    )


def _parse_user_date(text: str) -> Optional[Any]:
    raw = (text or "").strip()
    if not raw:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return getdate(datetime.strptime(raw, fmt).date())
        except Exception:
            continue
    try:
        return getdate(raw)
    except Exception:
        return None


def _handle_travel_from_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    from_date = _parse_user_date(text)
    if not from_date:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter From Date as {0}.").format(_DATE_HINT)
        )

    draft["from_date"] = str(from_date)
    draft["step"] = "awaiting_to_date"
    _save_draft(conv, draft)

    return OutboundMessage(
        body_text=_(
            "✅ From Date: *{0}*\n\n"
            "Step 4 of 5 — Enter *To Date*\n"
            "Format: {1}"
        ).format(formatdate(from_date, "dd MMM YYYY"), _DATE_HINT)
    )


def _handle_travel_to_date(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    to_date = _parse_user_date(text)
    if not to_date:
        return OutboundMessage(
            body_text=_("Invalid date. Please enter To Date as {0}.").format(_DATE_HINT)
        )

    from_date = getdate(draft.get("from_date"))
    if to_date < from_date:
        return OutboundMessage(body_text=_("To Date cannot be before From Date. Please try again."))

    draft["to_date"] = str(to_date)
    draft["step"] = "awaiting_route"
    _save_draft(conv, draft)

    return OutboundMessage(
        body_text=_(
            "✅ To Date: *{0}*\n\n"
            "Step 5 of 5 — Enter *Source & Destination*\n"
            "(e.g., 'Lahore to Islamabad'):"
        ).format(formatdate(to_date, "dd MMM YYYY"))
    )


def _handle_travel_route(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    route_raw = text.strip()
    if len(route_raw) < 2:
        return OutboundMessage(body_text=_("Please enter origin and destination locations."))

    source, destination = "Field Location", route_raw
    if " to " in route_raw.lower():
        parts = route_raw.lower().split(" to ", 1)
        source = parts[0].strip().title()
        destination = parts[1].strip().title()
    elif " - " in route_raw:
        parts = route_raw.split(" - ", 1)
        source = parts[0].strip().title()
        destination = parts[1].strip().title()

    draft["source"] = source
    draft["destination"] = destination
    draft["step"] = "awaiting_confirm"
    _save_draft(conv, draft)

    summary = _build_travel_summary(draft)
    return build_yes_no_buttons(
        summary + "\n\n" + _("Submit this Travel Authorisation for approval?"),
        yes_id="trv_submit",
        no_id="trv_cancel",
        yes_label=_("Submit"),
        no_label=_("Cancel"),
    )


def _build_travel_summary(draft: dict[str, Any]) -> str:
    from_date = formatdate(draft.get("from_date"), "dd MMM YYYY")
    to_date = formatdate(draft.get("to_date"), "dd MMM YYYY")
    source = draft.get("source") or "?"
    dest = draft.get("destination") or "?"
    return _(
        "📋 *Travel Authorisation Summary*\n\n"
        "• *Purpose:* {purpose}\n"
        "• *Mode of Travel:* {mode}\n"
        "• *Dates:* {from_date} to {to_date}\n"
        "• *Route:* {source} → {dest}"
    ).format(
        purpose=draft.get("purpose"),
        mode=draft.get("mode"),
        from_date=from_date,
        to_date=to_date,
        source=source,
        dest=dest,
    )


def _handle_travel_confirm(conv: Any, context: dict[str, Any], draft: dict, text: str) -> OutboundMessage:
    clean = text.strip().lower()
    if clean in ("trv_cancel", "no", "cancel"):
        return _cancel_travel_flow(conv, context)

    if clean not in ("trv_submit", "yes", "submit", "confirm"):
        summary = _build_travel_summary(draft)
        return build_yes_no_buttons(
            summary + "\n\n" + _("Submit this Travel Authorisation for approval?"),
            yes_id="trv_submit",
            no_id="trv_cancel",
            yes_label=_("Submit"),
            no_label=_("Cancel"),
        )

    try:
        doc_name = _create_travel_authorisation(draft, context)
    except Exception as exc:
        frappe.logger("ai_workplace").error(f"Travel authorization submission failed: {exc}")
        update_conversation(
            conv,
            state=ConversationState.AWAITING_SELECTION,
            current_intent=None,
            active_service="travel",
            draft_payload=None,
        )
        return wrap_with_parent_menu(
            _("Could not submit Travel Authorisation:\n\n{0}").format(str(exc)),
            context,
            "travel",
        )

    update_conversation(
        conv,
        state=ConversationState.AWAITING_SELECTION,
        current_intent=None,
        active_service="travel",
        draft_payload=None,
    )
    return wrap_with_parent_menu(
        _(
            "✅ *Travel Authorisation Submitted*\n\n"
            "Reference: *{0}*\n"
            "Status: *Pending Approval*\n\n"
            "Your travel authorisation request has been submitted for approval."
        ).format(doc_name),
        context,
        "travel",
    )


def _create_travel_authorisation(draft: dict[str, Any], context: dict[str, Any]) -> str:
    employee_id = draft.get("employee") or context.get("employee")
    if not employee_id:
        frappe.throw(_("Employee not found."))

    erp_user = context.get("user") or ""
    previous_user = frappe.session.user
    try:
        if erp_user and frappe.db.exists("User", erp_user):
            frappe.set_user(erp_user)

        employee = frappe.get_cached_doc("Employee", employee_id)
        doc = frappe.new_doc("Travel Authorisation Request Form")
        doc.employee = employee_id
        doc.employee_name = employee.employee_name
        doc.company = employee.company
        doc.department = employee.get("department")
        doc.designation = employee.get("designation")
        doc.purpose_of_travel = draft.get("purpose") or ""
        mode_val = _map_mode_of_travel(draft.get("mode") or "")
        doc.mode_of_travel = mode_val
        doc.posting_date = today()
        doc.workflow_state = "Pending"

        from_d = getdate(draft.get("from_date"))
        to_d = getdate(draft.get("to_date"))
        delta_days = (to_d - from_d).days + 1
        doc.total_days = max(delta_days, 1)

        doc.append(
            "travel_information",
            {
                "from_date": draft.get("from_date"),
                "to_date": draft.get("to_date"),
                "source": draft.get("source") or "Field Location",
                "destination": draft.get("destination") or "Destination",
                "mode_of_travel": mode_val,
            },
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except Exception as exc:
        frappe.log_error(
            title="Travel Authorisation Submission Failed",
            message=f"Failed to submit Travel Authorisation for employee '{employee_id}': {exc}\n\nDraft: {json.dumps(draft, default=str)}\n\nTraceback:\n{frappe.get_traceback()}"
        )
        raise exc
    finally:
        frappe.set_user(previous_user)
