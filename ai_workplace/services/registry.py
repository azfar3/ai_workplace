"""
ai_workplace/services/registry.py
───────────────────────────────────
Service Registry — Phase 2.

Lightweight service registry for Phase 2 service routing.
Prepared for extension in future phases.
"""

from __future__ import annotations

from typing import Any, Optional

SERVICES: dict[str, dict[str, Any]] = {
    "hr": {
        "key": "hr",
        "title": "My HR",
        "mode": "navigation_only",
        "description": "HR Self-Service (Leave, Attendance, Payroll)",
        "placeholder": "HR service selected.\n\nHR services will be available here.",
        "aliases": ["1", "hr", "my hr", "1️⃣ my hr", "human resources"],
    },
    "policy": {
        "key": "policy",
        "title": "My Policies",
        "mode": "navigation_only",
        "description": "Company Policy & Knowledge Standard Operating Procedures",
        "placeholder": "Policy assistance is being prepared.",
        "aliases": ["2", "policy", "policies", "my policies", "2️⃣ my policies"],
    },
    "travel": {
        "key": "travel",
        "title": "My Travel",
        "mode": "navigation_only",
        "description": "Travel Claims & Itinerary",
        "placeholder": "Travel service selected.\n\nTravel services will be available here.",
        "aliases": ["3", "travel", "my travel", "3️⃣ my travel"],
    },
    "consultant": {
        "key": "consultant",
        "title": "My Work",
        "mode": "navigation_only",
        "description": "Consultant / Contractor Timesheets & Work",
        "placeholder": "My Work selected.\n\nConsultant services will be available here.",
        "aliases": ["1", "work", "my work", "1️⃣ my work", "consultant"],
    },
    "help": {
        "key": "help",
        "title": "Help",
        "mode": "available",
        "description": "System Help & Assistance",
        "placeholder": "You can use the menu to access available workplace services.",
        "aliases": ["4", "help", "4️⃣ help", "?", "info"],
    },
}


def get_service_info(service_key: str) -> Optional[dict[str, Any]]:
    """Return registration info for a service by key."""
    return SERVICES.get((service_key or "").strip().lower())


def get_available_services_for_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return ordered list of available service dicts matching allowed_services in context.
    """
    allowed = [s.lower() for s in context.get("allowed_services", [])]
    results = []
    for key in allowed:
        if key in SERVICES:
            results.append(SERVICES[key])
    return results
