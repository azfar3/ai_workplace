"""Recognize requests for instructions before matching workflow keywords."""
import re


def procedure_intent(text: str) -> str | None:
    text = (text or "").lower()
    asks_how = re.search(
        r"\b(?:steps?|process|procedure|instructions?|how\s+(?:do\s+i|can\s+i|to)|"
        r"kaise|kesay|kaisay|tariqa|tareeqa|tarika)\b|طریقہ|کیسے|مراحل",
        text,
    )
    if not asks_how:
        return None
    if re.search(r"\b(?:leave|leaves|ch+h?utt?i)\b|چھٹی", text):
        return "leave_application_procedure"
    if re.search(r"\b(?:expense|expenses|claim|claims|reimbursement)\b|اخراجات|کلیم", text):
        return "expense_claim_procedure"
    return None
