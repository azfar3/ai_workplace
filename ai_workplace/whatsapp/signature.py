"""
ai_workplace/whatsapp/signature.py
───────────────────────────────────
Meta webhook signature validation (X-Hub-Signature-256).

Meta signs every POST webhook with HMAC-SHA256 using the Meta App Secret.
The signature is sent in the X-Hub-Signature-256 header as:
    sha256=<hex_digest>

This module validates that signature in a timing-safe manner.

Security requirements:
  - Validation must happen BEFORE any payload processing.
  - Must use a constant-time comparison to prevent timing attacks.
  - App Secret must come from AI Workplace Settings, never hardcoded.
  - On failure: log a security event, return False; do NOT process the message.
"""

from __future__ import annotations

import hashlib
import hmac

import frappe


def validate_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Validate the Meta webhook HMAC-SHA256 signature.

    Parameters
    ----------
    raw_body : bytes
        The raw request body (must be bytes, not decoded string).
    signature_header : str
        Value of the X-Hub-Signature-256 header, e.g. "sha256=abc123...".
    app_secret : str
        Meta App Secret from AI Workplace Settings.

    Returns
    -------
    bool
        True if the signature is valid, False otherwise.
    """
    if not app_secret:
        frappe.logger("ai_workplace").error(
            "AI Workplace: Meta App Secret is not configured.  "
            "Cannot validate webhook signature."
        )
        return False

    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    received_hex = signature_header[len("sha256="):]

    # Compute expected signature.
    expected_hex = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Timing-safe comparison.
    return hmac.compare_digest(expected_hex, received_hex)


def get_app_secret() -> str:
    """
    Retrieve the Meta App Secret from AI Workplace Settings.

    Returns empty string if not configured. Never raises.
    """
    try:
        settings = frappe.get_single("AI Workplace Settings")
        return (
            settings.get_password("meta_app_secret")
            or settings.get("meta_app_secret")
            or ""
        )
    except Exception as exc:
        frappe.logger("ai_workplace").error(
            f"AI Workplace: Failed to read Meta App Secret: {exc}"
        )
        return ""
