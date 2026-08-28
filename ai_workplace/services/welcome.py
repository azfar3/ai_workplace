"""
ai_workplace/services/welcome.py
─────────────────────────────────
Welcome message builder — Phase 1.

Keeps all user-facing welcome message strings in one place so that:
  - Future localization can be added without touching the webhook controller.
  - Business logic for "what to say" is separate from "how to send".

Phase 1 supports two responses:
  1. Personalized — for matched ERPNext identities.
  2. Generic      — for guest / ambiguous / inactive identities.

IMPORTANT (security):
  The generic response MUST NOT reveal:
  - Whether the phone number exists in ERPNext.
  - Whether an employee was found but is inactive.
  - Any internal ERPNext information.
"""

from __future__ import annotations

from typing import Any


def build_welcome_message(identity: dict[str, Any]) -> str:
    """
    Build the appropriate welcome message for the given identity result.

    Parameters
    ----------
    identity : dict
        An :class:`~ai_workplace.identity.resolver.IdentityResult` serialized
        to dict, or any dict with at least a "status" key.

    Returns
    -------
    str
        The message body to send via WhatsApp.
    """
    status = identity.get("status", "guest")

    if status == "matched":
        full_name = identity.get("full_name") or "there"
        return _personalized_welcome(full_name)

    # guest | ambiguous | inactive — all receive the same safe generic message.
    return _generic_welcome()


def _personalized_welcome(full_name: str) -> str:
    """
    Welcome {full_name}! 👋

    How can I help you today?
    """
    return f"Welcome {full_name}! 👋\n\nHow can I help you today?"


def _generic_welcome() -> str:
    """
    Hello! 👋

    Welcome. How can I help you today?
    """
    return "Hello! 👋\n\nWelcome. How can I help you today?"
