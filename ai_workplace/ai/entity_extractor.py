"""
ai_workplace/ai/entity_extractor.py
────────────────────────────────────
Phase 2.2 — Deterministic entity extraction for HR queries.

Extracts structured parameters (month, year, date ranges) from free-text
WITHOUT calling the LLM.  Results are passed as kwargs to run_tool() so
queries like "salary slip for August 2026" call the tool with the right
parameters instead of defaulting to "latest".

Public API::

    from ai_workplace.ai.entity_extractor import EntityExtractor

    entities = EntityExtractor.extract("latest_salary_slip", "salary slip for August 2026")
    # → {"month": 8, "year": 2026}

    entities = EntityExtractor.extract("apply_leave", "leave from 10th to 12th September")
    # → {"from_date": "2026-09-10", "to_date": "2026-09-12"}
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Any

# ── Month name → number ────────────────────────────────────────────────────────

_MONTHS: dict[str, int] = {
    # English full
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # English short
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    # Urdu / Roman Urdu
    "january": 1, "fabrari": 2, "march": 3, "april": 4,
    "mei": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# ── Day name → weekday offset ─────────────────────────────────────────────────

_WEEKDAYS: dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# ── Regexes ────────────────────────────────────────────────────────────────────

# ISO or common date: 2026-09-10, 10/09/2026, 10-09-2026
_RE_ISO = re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b")
_RE_DMY = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")

# "10th September", "September 10", "10 Sep"
_RE_DAY_MONTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s)\b" % "|".join(_MONTHS),
    re.IGNORECASE,
)
_RE_MONTH_DAY = re.compile(
    r"\b(%s)\s+(\d{1,2})(?:st|nd|rd|th)?\b" % "|".join(_MONTHS),
    re.IGNORECASE,
)
_RE_MONTH_ONLY = re.compile(
    r"\b(%s)\b" % "|".join(_MONTHS),
    re.IGNORECASE,
)
_RE_YEAR = re.compile(r"\b(20\d{2})\b")

# "from ... to ..." range detection
_RE_FROM_TO = re.compile(
    r"from\s+(.+?)\s+to\s+(.+?)(?:\s|$)",
    re.IGNORECASE,
)


class EntityExtractor:
    """
    Deterministic parameter extractor.

    Dispatches by intent_key to specialised extractors.  Returns a dict of
    kwargs suitable for passing to run_tool().  Returns {} when nothing
    meaningful is found so the tool defaults are preserved.
    """

    @classmethod
    def extract(cls, intent_key: str, text: str) -> dict[str, Any]:
        """Top-level dispatcher — returns extracted parameter dict."""
        text = (text or "").strip()
        if not text:
            return {}

        # Payroll — month / year params
        if intent_key in ("latest_salary_slip", "tax_deductions", "monthly_attendance"):
            return cls._extract_month_year(text)

        # Leave application — date range
        if intent_key in ("apply_leave",):
            return cls._extract_date_range(text)

        return {}

    # ── Month / Year ───────────────────────────────────────────────────────────

    @classmethod
    def _extract_month_year(cls, text: str) -> dict[str, Any]:
        """
        Extract month and year for payroll / attendance queries.

        Examples handled:
          "salary slip for August 2026"       → {month: 8, year: 2026}
          "tax details for last month"        → {month: N-1, year: Y}
          "attendance for Sep"                → {month: 9, year: current}
          "show slip for 08/2026"             → {month: 8, year: 2026}
        """
        lower = text.lower()
        now = datetime.now()

        # "last month" shortcut
        if "last month" in lower or "pichle mahine" in lower:
            if now.month == 1:
                return {"month": 12, "year": now.year - 1}
            return {"month": now.month - 1, "year": now.year}

        # "this month" / "current month"
        if any(p in lower for p in ("this month", "current month", "is mahine", "abhi")):
            return {"month": now.month, "year": now.year}

        result: dict[str, Any] = {}

        # MM/YYYY or MM-YYYY — check FIRST to avoid month-name regex stealing the digits
        mm_yyyy = re.search(r"\b(\d{1,2})[/-](20\d{2})\b", text)
        if mm_yyyy:
            return {"month": int(mm_yyyy.group(1)), "year": int(mm_yyyy.group(2))}

        # Month name match
        m = _RE_MONTH_ONLY.search(text)
        if m:
            result["month"] = _MONTHS[m.group(1).lower()]

        # Year match
        y = _RE_YEAR.search(text)
        if y:
            result["year"] = int(y.group(1))
        elif result.get("month"):
            # Default to current year when only month given
            result["year"] = now.year

        return result


    # ── Date Range ─────────────────────────────────────────────────────────────

    @classmethod
    def _extract_date_range(cls, text: str) -> dict[str, Any]:
        """
        Extract from_date / to_date from natural-language leave requests.

        Examples handled:
          "leave from 10th to 12th September"
          "leave from Monday to Wednesday"
          "leave from 2026-09-10 to 2026-09-12"
          "apply leave on Friday"
        """
        now = datetime.now()
        result: dict[str, Any] = {}

        # Try "from X to Y" pattern first
        ft = _RE_FROM_TO.search(text)
        if ft:
            from_str = ft.group(1).strip()
            # to_str: take the rest of the text after "to"
            to_pos = text.lower().index(" to ", text.lower().index("from "))
            to_str = text[to_pos + 4:].strip().split()[0:4]
            to_str = " ".join(to_str)

            from_date = cls._parse_date_fragment(from_str, now)
            to_date = cls._parse_date_fragment(to_str, now)

            if from_date:
                result["from_date"] = from_date.strftime("%Y-%m-%d")
            if to_date:
                result["to_date"] = to_date.strftime("%Y-%m-%d")
            # If only from given, set to = from (single-day leave)
            if result.get("from_date") and not result.get("to_date"):
                result["to_date"] = result["from_date"]
            return result

        # "on Friday" / "on Monday" single day
        for day_name, offset in _WEEKDAYS.items():
            if f"on {day_name}" in text.lower() or text.lower().startswith(day_name):
                d = cls._next_weekday(now.date(), offset)
                result["from_date"] = d.strftime("%Y-%m-%d")
                result["to_date"] = d.strftime("%Y-%m-%d")
                return result

        # ISO date pair anywhere in text
        iso_matches = _RE_ISO.findall(text)
        if len(iso_matches) >= 2:
            result["from_date"] = "%s-%02d-%02d" % (iso_matches[0][0], int(iso_matches[0][1]), int(iso_matches[0][2]))
            result["to_date"] = "%s-%02d-%02d" % (iso_matches[1][0], int(iso_matches[1][1]), int(iso_matches[1][2]))
        elif len(iso_matches) == 1:
            d = "%s-%02d-%02d" % (iso_matches[0][0], int(iso_matches[0][1]), int(iso_matches[0][2]))
            result["from_date"] = d
            result["to_date"] = d

        return result

    @classmethod
    def _parse_date_fragment(cls, fragment: str, ref: datetime) -> date | None:
        """
        Parse a loose date fragment like "10th September", "Monday", "2026-09-10".
        Returns a date object or None.
        """
        fragment = fragment.strip()
        lower = fragment.lower()

        # ISO date
        m = _RE_ISO.search(fragment)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        # DMY date
        m = _RE_DMY.search(fragment)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

        # Day-month: "10th September", "10 Sep"
        m = _RE_DAY_MONTH.search(fragment)
        if m:
            day = int(m.group(1))
            month = _MONTHS[m.group(2).lower()]
            year_m = _RE_YEAR.search(fragment)
            year = int(year_m.group(1)) if year_m else ref.year
            try:
                return date(year, month, day)
            except ValueError:
                return None

        # Month-day: "September 10"
        m = _RE_MONTH_DAY.search(fragment)
        if m:
            month = _MONTHS[m.group(1).lower()]
            day = int(m.group(2))
            year_m = _RE_YEAR.search(fragment)
            year = int(year_m.group(1)) if year_m else ref.year
            try:
                return date(year, month, day)
            except ValueError:
                return None

        # Weekday name: "Monday", "Friday"
        for day_name, offset in _WEEKDAYS.items():
            if lower == day_name or lower.startswith(day_name):
                return cls._next_weekday(ref.date(), offset)

        return None

    @staticmethod
    def _next_weekday(from_date: date, weekday: int) -> date:
        """Return the next occurrence of weekday (0=Mon) on or after from_date."""
        days_ahead = weekday - from_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0:
            days_ahead = 7  # "next Monday" means the Monday 7 days away
        from datetime import timedelta
        return from_date + timedelta(days=days_ahead)
