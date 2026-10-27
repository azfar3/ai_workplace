"""
ai_workplace/whatsapp/outbound.py
──────────────────────────────────
Structured outbound message for WhatsApp (text or interactive).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class OutboundMessage:
    """WhatsApp outbound payload — plain text, interactive, and/or document."""

    body_text: str = ""
    interactive: Optional[dict[str, Any]] = field(default=None)
    follow_up: list["OutboundMessage"] = field(default_factory=list)

    skip_send: bool = False
    document_bytes: Optional[bytes] = field(default=None)
    document_filename: str = ""
    document_mimetype: str = ""
    document_caption: str = ""
    preserve_follow_up: bool = False
    session_name: str = ""
    receiver: str = ""
    receiver_name: str = ""
    username: str = ""
    session_id: str = ""

    def is_interactive(self) -> bool:
        return bool(self.interactive)

    def is_location_request(self) -> bool:
        return bool(self.interactive and self.interactive.get("type") == "location_request_message")

    def has_document(self) -> bool:
        return bool(self.document_bytes)

    def has_media(self) -> bool:
        return bool(self.document_bytes)

    @property
    def message_type(self) -> str:
        if self.has_document():
            return "document"
        return "interactive" if self.is_interactive() else "text"

    def log_text(self) -> str:
        """Human-readable text stored in WhatsApp Message Log."""
        if self.has_document():
            cap = self.document_caption or self.body_text
            name = self.document_filename or "file"
            return f"{cap}\n\n[document: {name}]"
        if self.is_interactive():
            itype = self.interactive.get("type", "")
            if itype == "location_request_message":
                return f"{self.body_text}\n\n[location request: send current location]"
            action = self.interactive.get("action", {})
            pieces = []
            if self.interactive.get("header", {}).get("text"):
                pieces.append(self.interactive["header"]["text"])
            if self.body_text:
                pieces.append(self.body_text)
            if self.interactive.get("footer", {}).get("text"):
                pieces.append(self.interactive["footer"]["text"])
            rendered = "\n\n".join(pieces)

            if itype == "list":
                index = 1
                for section in action.get("sections", []):
                    if section.get("title"):
                        rendered += f"\n\n{section['title']}"
                    for row in section.get("rows", []):
                        title = row.get("title", "")
                        description = row.get("description", "")
                        suffix = f" — {description}" if description and description != title else ""
                        rendered += f"\n{index}. {title}{suffix}"
                        index += 1
                return rendered

            if itype == "button":
                for index, button in enumerate(action.get("buttons", []), 1):
                    title = button.get("reply", {}).get("title", "")
                    if title:
                        rendered += f"\n{index}. {title}"
                return rendered

            return rendered or self.body_text
        return self.body_text

    def __str__(self) -> str:
        return self.log_text()
