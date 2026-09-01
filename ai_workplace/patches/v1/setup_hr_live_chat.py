"""Post-migrate patch: ensure HR live chat role, page, and workspace link exist."""

from ai_workplace.install import setup_hr_live_chat


def execute():
    setup_hr_live_chat()
