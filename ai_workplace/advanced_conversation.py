"""Pure decisions for slot collection, task switching, and scoped knowledge."""
from __future__ import annotations

import re
from datetime import date, timedelta

# Workflow drafts can be resumed; never snapshot credentials or active HR chats.
RESUMABLE_WORKFLOWS = {
    'leave_apply': ('leave application', 'attendance_leave'),
    'att_request_apply': ('attendance request', 'attendance_leave'),
    'trv_apply': ('travel request', 'travel'),
    'trv_problem': ('travel support request', 'travel'),
}


def leave_request(text):
    return bool(re.search(r'\b(?:apply|request|need|take|want)\b.{0,35}\bleave\b|\bleave\b.{0,20}\b(?:apply|request)\b|chutti (?:chahiye|leni)', text, re.I))


def extract_leave_slots(text, today: date):
    """Only explicit, unambiguous slots. Missing fields stay missing."""
    # Expand an explicitly shared month, without inventing an end date.
    text = re.sub(r'\bfrom (\d{1,2})(?:st|nd|rd|th)? to (\d{1,2})(?:st|nd|rd|th)? ([A-Za-z]+)(?: (20\d{2}))?',
                  lambda m: f"from {m[1]} {m[3]} {m[4] or today.year} to {m[2]} {m[3]} {m[4] or today.year}", text, flags=re.I)
    clean = text.lower()
    slots = {}
    # Parse absolute ISO dates, explicit day/month-name/year, and relative days.
    dates = []
    for match in re.finditer(r'\b\d{4}-\d{1,2}-\d{1,2}\b', text):
        try:
            dates.append((match.start(), date.fromisoformat(match.group())))
        except ValueError:
            pass
    months = {name: i for i, name in enumerate(('january','february','march','april','may','june','july','august','september','october','november','december'), 1)}
    for match in re.finditer(r'\b(\d{1,2})(?:st|nd|rd|th)?[ -]+([a-z]+)(?:[ ,\-]+(20\d{2}))?\b', clean):
        month = next((n for word,n in months.items() if match[2] == word or match[2] == word[:3]), None)
        if month:
            try:
                dates.append((match.start(), date(int(match[3] or today.year), month, int(match[1]))))
            except ValueError:
                pass
    for match in re.finditer(r'\b([a-z]+) (\d{1,2})(?:st|nd|rd|th)?(?:,? (20\d{2}))?\b', clean):
        month = next((n for word,n in months.items() if match[1] == word or match[1] == word[:3]), None)
        if month:
            try:
                dates.append((match.start(), date(int(match[3] or today.year), month, int(match[2]))))
            except ValueError:
                pass
    for match in re.finditer(r'\b(today|tomorrow|next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b', clean):
        token = match.group()
        if token.startswith('next '):
            weekday = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday').index(token[5:])
            offset = (weekday - today.weekday()) % 7 or 7
        else:
            offset = int(token == 'tomorrow')
        dates.append((match.start(), today + timedelta(days=offset)))
    dates.sort()
    # More than two dates or invalid explicit dates require clarification.
    invalid_iso = len(re.findall(r'\b\d{4}-\d{1,2}-\d{1,2}\b', text)) != len([d for d in dates if re.match(r'\d{4}-', text[d[0]:])])
    if not invalid_iso and len(dates) in (1, 2):
        start = dates[0][1]
        end = dates[-1][1]
        incomplete_range = len(dates) == 1 and bool(re.search(r'\b(?:to|until|through)\b', clean))
        if start >= today:
            slots['from_date'] = start.isoformat()
            if not incomplete_range and end >= start:
                slots['to_date'] = end.isoformat()
    reasons = [
        (r'\bmaternity\b', 'Maternity'),
        (r'\b(?:family|child|mother|father)\b.*\bsick\b|\bsick\b.*\b(?:family|child|mother|father)\b', 'Sick Leave Immediate Family'),
        (r'\bsick\b', 'Self-Sick Leave'),
        (r'\b(?:annual|vacation|vacations)\b', 'Vacations'),
        (r'\b(?:exam|exams|study)\b', 'Study/Exams'),
        (r'\bumrah\b', 'Umrah'), (r'\bhajj\b', 'Hajj'),
    ]
    type_text = re.split(r'\b(?:because|reason\s*:|for the reason)\b', clean, maxsplit=1)[0]
    for pattern, reason in reasons:
        if re.search(pattern, type_text):
            slots['custom_leave_reason'] = reason
            break
    if re.search(r'\b(?:not|no) (?:a )?half[ -]day\b', clean):
        slots['half_day'] = 0
    elif re.search(r'\bhalf[ -]day\b', clean):
        slots['half_day'] = 1
    elif re.search(r'\bfull[ -]days?\b', clean):
        slots['half_day'] = 0
    reason = re.search(r'\b(?:because|reason\s*:|for the reason)\s+(.+)', text, re.I)
    if reason and len(reason[1].strip()) >= 3:
        slots['description'] = reason[1].strip()[:1000]
    return slots


def applicable_metadata(chunk, context, today):
    """Scoped content fails closed when the caller lacks an attribute."""
    for target, user in [('target_employment_type','employment_type'),('target_department','department'),('target_location','location')]:
        value = chunk.get(target)
        if value and value != 'All' and value != context.get(user):
            return False
    try:
        for key, future in [('effective_date', True), ('effective_to', False)]:
            if chunk.get(key):
                value = date.fromisoformat(str(chunk[key])[:10])
                if (future and value > today) or (not future and value < today):
                    return False
    except ValueError:
        return False
    return True
