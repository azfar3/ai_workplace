"""
Policies & Help — browse and download applicable HR policies on WhatsApp.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

import frappe
from frappe.utils import getdate, today

from ai_workplace.services.response_helpers import wrap_with_menu_again
from ai_workplace.services.travel import load_policy_pdf_bytes
from ai_workplace.whatsapp.interactive import _truncate
from ai_workplace.whatsapp.outbound import OutboundMessage

PORTAL_URL = "https://portal.micromerger.com"
MAX_POLICY_ROWS = 10


def get_applicable_policies(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return published policies scoped to the employee (same rules as HRMS Portal)."""
    erp_user = context.get("erp_user") or ""
    prev_user = frappe.session.user
    try:
        if erp_user:
            frappe.set_user(erp_user)
        elif context.get("employee"):
            user_id = frappe.db.get_value("Employee", context["employee"], "user_id")
            if user_id:
                frappe.set_user(user_id)
        from hrms.api.employee import get_policies

        return get_policies() or []
    except Exception:
        frappe.log_error(title="WhatsApp policies load failed", message=frappe.get_traceback())
        return []
    finally:
        frappe.set_user(prev_user)


def build_policies_list_message(context: dict[str, Any]) -> OutboundMessage:
    """Interactive list of applicable policies for the employee."""
    lang = context.get("preferred_language", "English")
    policies = get_applicable_policies(context)

    if not policies:
        if lang == "Urdu":
            body = "📚 *پالیسیاں*\n\nفی الحال آپ کے لیے کوئی شائع شدہ پالیسی دستیاب نہیں۔"
        else:
            body = "📚 *Policies*\n\nNo published policies are currently available for your profile."
        return wrap_with_menu_again(body, context)

    rows = []
    for policy in policies[:MAX_POLICY_ROWS]:
        subject = (policy.get("subject") or policy.get("name") or "Policy").strip()
        version = policy.get("version")
        title = subject[:24]
        if version:
            title = f"{title[:20]} v{version}"[:24]
        desc_bits = []
        if policy.get("published_from"):
            desc_bits.append(str(policy.get("published_from")))
        if policy.get("policy_document"):
            desc_bits.append("PDF")
        rows.append(
            {
                "id": f"pol_sel_{policy.get('name')}",
                "title": title,
                "description": " · ".join(desc_bits)[:72] or "View policy",
            }
        )

    if lang == "Urdu":
        header = "📚 *اپنی پالیسیاں*\n\nپالیسی منتخب کریں:"
    else:
        header = "📚 *Your Policies*\n\nSelect a policy to view or download:"

    outbound = OutboundMessage(
        body_text=header,
        interactive={
            "type": "list",
            "body": {"text": header},
            "action": {
                "button": _truncate("View Policies", 20),
                "sections": [{"title": "Policies", "rows": rows}],
            },
        },
    )
    menu = wrap_with_menu_again("", context)
    outbound.follow_up = [menu]
    return outbound


def build_policy_detail_outbound(context: dict[str, Any], policy_name: str) -> OutboundMessage:
    """Send policy PDF when attached, otherwise a text summary."""
    lang = context.get("preferred_language", "English")
    policies = get_applicable_policies(context)
    policy = next((p for p in policies if p.get("name") == policy_name), None)

    if not policy:
        body = "Policy not found or you do not have access to it."
        if lang == "Urdu":
            body = "پالیسی نہیں ملی یا آپ کو رسائی نہیں ہے۔"
        return wrap_with_menu_again(body, context)

    subject = policy.get("subject") or policy_name
    version = policy.get("version")
    version_part = f" (v{version})" if version else ""
    doc_url = _resolve_policy_document_url(policy)

    if doc_url:
        try:
            pdf_bytes, filename = load_policy_pdf_bytes(doc_url)
            caption = f"📄 *{subject}*{version_part}"
            document = OutboundMessage(
                body_text=caption,
                document_caption=caption,
                document_bytes=pdf_bytes,
                document_filename=filename,
                document_mimetype="application/pdf",
            )
            document.follow_up = [wrap_with_menu_again("", context)]
            return document
        except Exception:
            frappe.log_error(title="WhatsApp policy PDF failed", message=frappe.get_traceback())

    summary = _html_to_text(policy.get("notifiction") or "")
    if not summary:
        summary = f"Policy *{subject}*{version_part} is published."
        if policy.get("published_from"):
            summary += f"\nEffective from: {policy.get('published_from')}"

    summary = f"📄 *{subject}*{version_part}\n\n{summary[:3500]}"
    if lang == "Urdu":
        summary += f"\n\nمکمل تفصیل کے لیے {PORTAL_URL} پر جائیں۔"
    else:
        summary += f"\n\nFor the full policy, visit {PORTAL_URL}."

    return wrap_with_menu_again(summary, context)


def _resolve_policy_document_url(policy: dict[str, Any]) -> str:
    encoded = policy.get("policy_document") or ""
    if not encoded:
        return ""
    if encoded.startswith("/") or encoded.startswith("http"):
        return encoded
    try:
        import base64

        decoded = base64.b64decode(encoded).decode("utf-8")
        if decoded.startswith("http"):
            path = decoded.split(".com", 1)[-1]
            return path if path.startswith("/") else f"/{path.lstrip('/')}"
        return decoded
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
