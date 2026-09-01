# HRMIS Support PIN API Contract

**Audience:** HRMIS Portal team  
**Backend app:** `ai_workplace`  
**Authentication:** Frappe session (logged-in HRMIS user)

## Overview

Employees set and change their 4-digit **MicroMerger Support PIN** in HRMIS User Profile. WhatsApp only verifies the PIN — it never creates, resets, or displays the PIN.

## Endpoints

### `get_support_pin_status`

```
GET/POST /api/method/ai_workplace.api.support_pin.get_support_pin_status
```

**Response:**
```json
{
  "message": {
    "configured": true,
    "status": "Active",
    "last_changed": "2026-08-31 10:00:00",
    "locked_until": null
  }
}
```

Never returns PIN or hash.

---

### `set_support_pin`

```
POST /api/method/ai_workplace.api.support_pin.set_support_pin
```

**Body (form or JSON):**
```json
{
  "new_pin": "4827",
  "confirm_pin": "4827"
}
```

**Success response:**
```json
{
  "message": {
    "success": true,
    "message": "Your MicroMerger Support PIN has been set successfully.",
    "configured": true,
    "status": "Active",
    "last_changed": "...",
    "locked_until": null
  }
}
```

**Errors:**
- `PIN and confirmation do not match.`
- `Please choose a less predictable 4-digit PIN.`
- `No active employee record linked to your account.`

**Side effects:**
- Increments `security_version` on the security profile
- Invalidates all active WhatsApp secure sessions for the employee

## UI guidance (HRMIS team)

Add a **WhatsApp Support** section on authenticated User Profile:

| State | UI |
|-------|-----|
| PIN not set | Show "Not Set" + **Set 4-Digit PIN** (New + Confirm fields) |
| PIN active | Show masked `● ● ● ●` + **Change PIN** (New + Confirm; no old PIN required) |

Optional: display registered WhatsApp number and `last_changed` from status API.

## Security rules

- Do not log `new_pin` or `confirm_pin` on client or server
- Do not store PIN in localStorage
- Use HTTPS only
- HRMIS login is the authentication for PIN set/change (no old PIN required)

## WhatsApp behaviour (reference)

After PIN is set in HRMIS, employee selects a protected WhatsApp service → enters PIN → 24-hour secure session → service resumes automatically.

If PIN not set, WhatsApp shows HRMIS Portal guidance with **Open HRMIS Portal** / **I Have Set My PIN** buttons.
