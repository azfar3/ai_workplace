"""
ai_workplace/ai/query_resolver.py
──────────────────────────────────
Deterministic Query Resolver — classifies free-text employee messages WITHOUT
calling the LLM.

Resolution is performed in four layers, each more expensive but more flexible:

  Layer 1 — Exact alias match     (score 1.00)
  Layer 2 — Substring alias match (score 0.80)
  Layer 3 — Regex pattern match   (score 0.85)
  Layer 4 — Keyword overlap       (score 0.70)

The highest score across all layers wins.  A score ≥ CONFIDENCE_THRESHOLD (0.70)
is considered a confirmed classification.  Anything below falls through to the
keyword router / LLM fallback in the orchestrator.
"""

from __future__ import annotations

import re
import string
from typing import Any, Dict, Optional, Tuple

from ai_workplace.ai.intent_catalog import INTENT_CATALOG

# Minimum score to accept a classification as deterministic
CONFIDENCE_THRESHOLD = 0.70


# ─── Layer 3: Regex patterns per intent ────────────────────────────────────────
# Score awarded on a successful match: 0.85
# Patterns use (?i) flag (applied at compile time) for case-insensitivity.
# Keep patterns concise; prefer specificity over broad catch-alls.

INTENT_PATTERNS: Dict[str, list[str]] = {
    # ── Leave ──────────────────────────────────────────────────────────────────
    "leave_balance": [
        r"how (many|much) leaves? (do i|i have|have i|are|left|remaining|available)",
        r"(remaining|leftover|pending|available) leaves?",
        r"leave (balance|left|remaining|available|baqi)",
        r"kitne leaves? (hain|bache|baqi|hai)",
        r"meri? leave (balance|kitni|kitne|kya hai)",
        r"how many (annual|casual|sick|earned) leaves?",
    ],
    "apply_leave": [
        r"(apply|request|take|need|want|lena).{0,15}leave",
        r"leave (from|on|between|starting|ke liye).{0,30}(monday|tuesday|wednesday|thursday|friday|to|\d{1,2})",
        r"chutti (chahiye|leni hai|lena chahta|lagani|ka|ke liye)",
        r"(i need|i want|can i take|mujhe) (a |some )?leaves?",
        r"leave (request|application|apply|dena|lena)",
        r"submit (a |)?leave",
    ],
    "leave_history": [
        r"(my |show |view )?(leave|chutti) (history|record|past|previous|taken|log)",
        r"(how many|kitni|kitne) leaves? (did i|maine) (take|li|liye|taken)",
        r"past (leave|chutti) (record|history)",
        r"leaves? (i |maine )?(have |)?taken",
    ],
    "carry_forward_leave": [
        r"carry.?forward (leave|leaves|chutti)",
        r"unused leaves?.{0,20}carry",
        r"(can i|kya) carry.?forward",
        r"what happens to (unused|remaining|leftover) (leave|leaves|chutti)",
        r"leave (encashment|lapse|expire)",
    ],
    # ── Payroll ────────────────────────────────────────────────────────────────
    "latest_salary_slip": [
        r"(my |show |send |get |bhejo )?(latest|last|current|this month.?s?)? ?(salary slip|payslip|pay slip)",
        r"salary slip (for|of|ka|ki)?",
        r"(bhejo|dena|send|show|de do) (meri? )?salary",
        r"(download|view) (my )?(salary|payslip|pay slip)",
    ],
    "tax_deductions": [
        r"(my |kitna |how much )?tax (deducted|deductions|kata|katta|cut|detail)",
        r"how much (tax|income tax) (was |is |has been |)?deducted",
        r"income tax (deduction|detail|info)",
        r"tax (summary|breakdown|history)",
    ],
    # ── Attendance ─────────────────────────────────────────────────────────────
    "today_attendance": [
        r"(today.?s?|aaj ki?) (attendance|hazri|check.?in|check.?out)",
        r"(my )?attendance (today|aaj)",
        r"(did|have) i (checked? in|marked attendance|punched) today",
        r"(check.?in|check.?out) (time|status|today|aaj|abhi)",
        r"aaj (check in|checkin|hazri) (hua|kiya|ki|status)",
    ],
    "monthly_attendance": [
        r"(my |show )?(attendance|hazri) (for|of|this|last) (month|[a-z]+)",
        r"(monthly|mahana) (attendance|hazri)",
        r"attendance (summary|report) (for|of)? ?(this |last )?(month|[a-z]+ \d{4})?",
        r"[a-z]+ (month|2024|2025|2026).{0,10}attendance",
    ],
    "forgot_checkin": [
        r"(forgot|forget|missed|miss|bhool|nahi kiya) (to )?(check.?in|punch|mark attendance)",
        r"(check.?in|attendance) (nahi|not|bhool|miss|hua nahi)",
        r"i (didn.?t|did not|forgot to) (check.?in|punch|mark)",
        r"check.?in (miss|bhool|nahi|forgot)",
    ],
    # ── Employee Profile ───────────────────────────────────────────────────────
    "my_designation": [
        r"(my |meri |mera )?(designation|job title|position|post|rank|pada)",
        r"what (is|am) (my |i |meri )?(designation|title|position|role|post)",
        r"(mera|meri) (designation|post|position|title)",
    ],
    "my_department": [
        r"(my |mera |meri )?department",
        r"which (department|dept) (am i|do i|hoon|mein hoon)",
        r"(what is|mera) (my )?department",
    ],
    "my_branch": [
        r"(my |mera |meri )?branch",
        r"which (branch|office branch|office location) (am i|i am|do i|hoon|mein hoon)",
        r"what is my branch",
    ],
    "profile_gaps": [
        r"(my |show )?(profile|profil) (gap|completion|incomplete|missing|status)",
        r"(what|which) (info|information|detail) (is |are )?(missing|incomplete|required|needed)",
        r"profile (complete|completion|status|kitna)",
    ],
    # ── Policy / Knowledge ─────────────────────────────────────────────────────
    "search_knowledge": [
        r"(employee |company |staff |hr )?(handbook|manual|guide|guideline|rulebook)",
        r"what does (the |employee |company |hr )?(handbook|manual|policy) say",
        r"quality policy",
        r".{0,20}policy.{0,30}",
        r"(what|tell|explain|show).{0,20}(policy|rule|guideline)",
    ],
    "policy_list": [
        r"(show|list|view|all|get) (the |)?policies",
        r"(available|company|hr|all) policies",
        r"(which|what|how many) policies (are there|exist|do we have)",
    ],
    "office_timings": [
        r"(office|work) (timing|hour|time|schedule|waqt)",
        r"(kab|when) (does |do |is )?office (start|end|open|close|begin)",
        r"(what time|kitne baje) (does|is) (office|work) (start|open|begin|end)",
        r"office (hours|timing|schedule)",
    ],
    "maternity_leave_policy": [
        r"maternity (leave|policy|rules?|detail)",
        r"(pregnancy|baby|birth).{0,10}leave",
        r"paternity leave",
    ],
    "leave_application_procedure": [
        r"how (do i|to|can i) apply (for )?leave",
        r"(procedure|process|steps?) (for |to )?(apply|applying|get|take) (leave|chutti)",
        r"leave (application|apply) (process|procedure|steps?|kaise)",
    ],
    # ── Profile / Navigation ───────────────────────────────────────────────────
    "menu_help": [
        r"what (can you do|do you do|are your capabilities|services do you offer)",
        r"(show |list )?(all )?(services|options|features|capabilities)",
        r"(help|mدد|madat)",
    ],
}


class QueryResolver:
    """
    Deterministic four-layer intent classifier.

    Usage::

        intent_key, meta, confidence = QueryResolver.resolve("what is my leave balance?")
        # → ("leave_balance", {...}, 1.0)
    """

    # ── Text normalisation ──────────────────────────────────────────────────────

    _CORRECTIONS: dict[str, str] = {
        "chuti":    "leave",
        "chutti":   "leave",
        "chhutti":  "leave",
        "paisa":    "salary",
        "tankhwa":  "salary",
        "tanjwah":  "salary",
        "payslip":  "salary slip",
        "polices":  "policies",
        "baance":   "balance",
        "bal":      "balance",
        "timings":  "office timings",
        "hazri":    "attendance",
        "bhejo":    "send",
        "mujhe":    "i need",
        "dena":     "give me",
        "dikhao":   "show",
        "batao":    "tell me",
        "kya":      "what is",
        "kitne":    "how many",
        "kitni":    "how many",
        "mere":     "my",
        "meri":     "my",
        "mera":     "my",
        "hai":      "is",
        "hain":     "are",
    }

    _COMPILED_PATTERNS: dict[str, list[re.Pattern]] | None = None

    @classmethod
    def _get_compiled_patterns(cls) -> dict[str, list[re.Pattern]]:
        if cls._COMPILED_PATTERNS is None:
            cls._COMPILED_PATTERNS = {
                intent: [re.compile(p, re.IGNORECASE) for p in patterns]
                for intent, patterns in INTENT_PATTERNS.items()
            }
        return cls._COMPILED_PATTERNS

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalise free-text for matching:
          1. Lowercase
          2. Strip punctuation
          3. Collapse whitespace
          4. Apply Roman-Urdu / common spelling corrections word-by-word
        """
        if not text:
            return ""

        text = text.lower()
        text = text.translate(str.maketrans("", "", string.punctuation))
        text = re.sub(r"\s+", " ", text).strip()

        words = text.split()
        corrected = [QueryResolver._CORRECTIONS.get(w, w) for w in words]
        return " ".join(corrected)

    # ── Layer scorers ───────────────────────────────────────────────────────────

    @staticmethod
    def _score_aliases(normalized_text: str, intent_data: dict[str, Any]) -> float:
        """
        Layer 1 (exact): 1.00
        Layer 2 (substring): 0.80
        """
        score = 0.0
        for alias in intent_data.get("aliases", []):
            norm_alias = QueryResolver.normalize_text(alias)
            if normalized_text == norm_alias:
                return 1.0
            if norm_alias and norm_alias in normalized_text:
                score = max(score, 0.80)
        return score

    @staticmethod
    def _score_keywords(normalized_text: str, intent_data: dict[str, Any]) -> float:
        """Layer 4: keyword overlap → 0.70."""
        score = 0.0
        for intent_kw in intent_data.get("intents", []):
            norm_kw = QueryResolver.normalize_text(intent_kw.replace("_", " "))
            if norm_kw and norm_kw in normalized_text:
                score = max(score, 0.70)
        return score

    @classmethod
    def _score_patterns(cls, raw_text: str, intent_key: str) -> float:
        """Layer 3: regex patterns → 0.85."""
        compiled = cls._get_compiled_patterns()
        patterns = compiled.get(intent_key, [])
        for pattern in patterns:
            if pattern.search(raw_text):
                return 0.85
        return 0.0

    @classmethod
    def score_intent(cls, raw_text: str, normalized_text: str, intent_key: str,
                     intent_data: dict[str, Any]) -> float:
        """Combine all layer scores, return the highest."""
        alias_score = cls._score_aliases(normalized_text, intent_data)
        if alias_score == 1.0:
            return 1.0  # early exit — perfect match

        pattern_score = cls._score_patterns(raw_text, intent_key)
        keyword_score = cls._score_keywords(normalized_text, intent_data)

        return max(alias_score, pattern_score, keyword_score)

    # ── Public API ──────────────────────────────────────────────────────────────

    @classmethod
    def resolve(cls, message: str) -> Tuple[Optional[str], Optional[dict[str, Any]], float]:
        """
        Resolve a message to an intent and metadata.

        Returns:
            (intent_key, metadata_dict, confidence_score)

        If confidence < CONFIDENCE_THRESHOLD the intent_key will be "unknown"
        and metadata will be None.
        """
        raw = (message or "").strip()
        normalized = cls.normalize_text(raw)

        best_intent: Optional[str] = None
        best_meta: Optional[dict[str, Any]] = None
        best_score: float = 0.0

        for intent_key, meta in INTENT_CATALOG.items():
            score = cls.score_intent(raw, normalized, intent_key, meta)
            if score > best_score:
                best_score = score
                best_intent = intent_key
                best_meta = meta

        if best_score >= CONFIDENCE_THRESHOLD and best_intent:
            return best_intent, best_meta, best_score

        return "unknown", None, 0.0
