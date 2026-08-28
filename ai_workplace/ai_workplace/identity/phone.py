"""
ai_workplace/identity/phone.py
──────────────────────────────
Phone number normalization service.

Canonical representation: E.164 (e.g. +923001234567)

Supported input formats (Pakistani examples):
  03001234567
  923001234567
  +923001234567
  0300 1234567
  0300-1234567
  3001234567

The `phonenumbers` library handles international parsing correctly.
A default region of "PK" is used for ambiguous local numbers
(e.g. 03001234567 without a country prefix).

International numbers with a leading + are parsed without a default region,
so the service is internationally extensible.
"""

import re
from typing import Optional

import frappe

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, NumberParseException
    _PHONENUMBERS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PHONENUMBERS_AVAILABLE = False


# Default region used when no country prefix is present.
# Frappe site config can override this if needed.
_DEFAULT_REGION = "PK"


class PhoneNormalizationError(Exception):
    """Raised when a phone number cannot be normalized to E.164."""


def normalize_phone_number(
    raw: str,
    default_region: Optional[str] = None,
) -> str:
    """
    Normalize *raw* phone number to E.164 format.

    Parameters
    ----------
    raw : str
        The raw phone string from WhatsApp, a form, or a DB field.
    default_region : str, optional
        ISO 3166-1 alpha-2 region code used when the number has no country
        prefix (e.g. "PK").  Defaults to _DEFAULT_REGION.

    Returns
    -------
    str
        E.164-formatted phone number, e.g. "+923001234567".

    Raises
    ------
    PhoneNormalizationError
        If the number cannot be parsed or is invalid.
    """
    if not raw:
        raise PhoneNormalizationError("Empty phone number provided")

    region = default_region or _DEFAULT_REGION
    cleaned = _pre_clean(raw)

    if not _PHONENUMBERS_AVAILABLE:
        # Fallback: basic Pakistani normalization without the library.
        return _fallback_normalize_pk(cleaned)

    try:
        parsed = phonenumbers.parse(cleaned, region)
    except NumberParseException as exc:
        raise PhoneNormalizationError(
            f"Cannot parse phone number '{raw}': {exc}"
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise PhoneNormalizationError(
            f"Phone number '{raw}' is not a valid number"
        )

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_phone_number_safe(
    raw: str,
    default_region: Optional[str] = None,
) -> Optional[str]:
    """
    Same as :func:`normalize_phone_number` but returns ``None`` on failure
    instead of raising an exception. Useful in bulk-lookup contexts.
    """
    try:
        return normalize_phone_number(raw, default_region)
    except PhoneNormalizationError:
        return None


def _pre_clean(raw: str) -> str:
    """
    Strip whitespace, dashes, parentheses and other decorative characters
    commonly seen in stored phone numbers, keeping digits and the leading +.
    """
    raw = raw.strip()

    # If the number starts with + preserve it; otherwise strip all non-digits
    # first to catch formats like "(0300) 123-4567".
    if raw.startswith("+"):
        # Keep + and digits only.
        return "+" + re.sub(r"\D", "", raw[1:])

    # Remove non-digit characters.
    digits_only = re.sub(r"\D", "", raw)

    # Re-attach nothing — the library handles it.
    return digits_only


def _fallback_normalize_pk(cleaned: str) -> str:
    """
    Minimal Pakistani normalization when the `phonenumbers` library is
    not available.  Handles the most common formats only.
    """
    # Already E.164
    if cleaned.startswith("+"):
        return cleaned

    # With country code but no +: 923001234567 → +923001234567
    if cleaned.startswith("92") and len(cleaned) == 12:
        return "+" + cleaned

    # Local format: 03001234567 → +923001234567
    if cleaned.startswith("0") and len(cleaned) == 11:
        return "+92" + cleaned[1:]

    # Bare: 3001234567 → +923001234567
    if len(cleaned) == 10 and cleaned.startswith("3"):
        return "+92" + cleaned

    raise PhoneNormalizationError(
        f"Cannot normalize phone number (fallback mode): '{cleaned}'"
    )


def phones_match(phone_a: Optional[str], phone_b: Optional[str]) -> bool:
    """
    Return True if both phones normalize to the same E.164 number.
    Returns False (not an exception) on any parse failure.
    """
    if not phone_a or not phone_b:
        return False
    norm_a = normalize_phone_number_safe(phone_a)
    norm_b = normalize_phone_number_safe(phone_b)
    return bool(norm_a and norm_b and norm_a == norm_b)
