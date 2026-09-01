# Cursor Implementation Plan — MicroMerger WhatsApp Support PIN Security

## 1. Objective

Implement a **simple, employee-friendly 4-digit Support PIN security layer** for protected HR/Operations services accessed through WhatsApp.

The design must be suitable for field staff and non-technical employees. Avoid OTP, SMS verification, CNIC questions, DOB questions, or password entry inside WhatsApp.

### Core product rule

> **The MicroMerger Support PIN is created, changed, or reset only by the authenticated employee through the HRMIS Portal. WhatsApp can only check whether a PIN exists and verify the PIN entered by the employee. WhatsApp must never create, reset, reveal, recover, or change the PIN.**

---

# 2. Final User Experience

## 2.1 If the employee selects a protected service

Example protected services:
- Salary slip
- Salary/payroll details
- Leave balance
- Detailed attendance history
- Tax certificate
- Contract document
- Personal profile
- Personal HR documents
- Profile update
- Sensitive travel/claim information

Flow:

```text
Employee selects protected WhatsApp service
                ↓
Identify employee using registered WhatsApp number
                ↓
Check whether Support PIN is configured
              /        \
            NO          YES
            ↓            ↓
Tell user to       Ask for 4-digit
set PIN in HRMIS   Support PIN
Portal                  ↓
                       Verify
                      /     \
                   Valid   Invalid
                    ↓         ↓
               Continue     Retry /
               service      lockout
```

---

# 3. PIN Not Configured — WhatsApp Flow

If no Support PIN exists, WhatsApp must not offer PIN creation.

Send:

> 🔐 **Secure Access Required**
>
> To access your personal HR information, please first set your **4-digit MicroMerger Support PIN**.
>
> Log in to your **HRMIS Portal**, open **My Profile**, and set your Support PIN.
>
> Once completed, return here and continue.

Buttons:

- **Open HRMIS Portal**
- **I Have Set My PIN**
- **Main Menu**

### Button behavior

`I Have Set My PIN` must re-check the backend.

Do not trust the button itself.

If the PIN is still not configured, repeat the Portal guidance.

If PIN is configured, ask for PIN and resume the pending service.

---

# 4. PIN Already Configured — WhatsApp Flow

Send:

> 🔐 **Verification Required**
>
> Please enter your **4-digit MicroMerger Support PIN** to continue.

When the PIN is received:

- intercept it before ordinary message logging;
- verify it against the stored hash;
- never save the raw PIN;
- never send it to AI;
- never display it in HR live chat.

### On successful verification

Send:

> ✅ **Verified successfully.**

Then automatically resume the service originally requested.

Example:

```text
Salary Slip
    ↓
PIN requested
    ↓
PIN verified
    ↓
Salary Slip is sent automatically
```

The employee must not have to select the service again.

---

# 5. Forgot PIN — WhatsApp Flow

There is no PIN recovery/reset flow inside WhatsApp.

Provide a simple action such as **Forgot PIN?** or help text.

Send:

> 🔐 **Forgot your Support PIN?**
>
> For your security, Support PINs cannot be reset through WhatsApp.
>
> Please log in to the **HRMIS Portal → My Profile** and set a new Support PIN.
>
> Once changed, return here and continue.

Buttons:

- **Open HRMIS Portal**
- **Try Again**
- **Main Menu**

No:
- CNIC verification
- DOB verification
- OTP
- SMS
- HRMIS password inside WhatsApp
- PIN recovery questions

---

# 6. HRMIS Portal — User Profile Changes

> **Ownership:** PIN setup/change UI in the HRMIS user profile is owned by the **HRMIS team**. The `ai_workplace` app delivers the backend (`WhatsApp Security Profile`, `set_support_pin` / `get_support_pin_status` APIs). HRMIS Portal calls those APIs from the authenticated user profile screen.

Add a simple section/card to the authenticated employee profile (HRMIS team implements).

## Card title

**WhatsApp Support**

### Display

**Registered WhatsApp Number**  
`03XX XXXXXXX`

**Support PIN**

If not configured:

`Not Set`

Button:

**Set 4-Digit PIN**

If configured:

`● ● ● ●`

Status:

`Active`

Button:

**Change PIN**

Optional metadata:

- PIN Last Changed
- WhatsApp secure access status

Do not display the actual PIN.

---

# 7. PIN Setup in HRMIS Portal

## First-time setup

User must already be authenticated in HRMIS.

Flow:

```text
HRMIS Login
    ↓
My Profile
    ↓
WhatsApp Support
    ↓
Set 4-Digit PIN
    ↓
Enter PIN
    ↓
Confirm PIN
    ↓
Validate
    ↓
Hash PIN
    ↓
Save
```

UI:

```text
Set MicroMerger Support PIN

New PIN
[ _ _ _ _ ]

Confirm PIN
[ _ _ _ _ ]

[ Save PIN ]
```

Success message:

> Your MicroMerger Support PIN has been set successfully.

---

# 8. Change / Reset PIN in HRMIS Portal

The user does not need to know the old Support PIN.

Because they are already authenticated in their HRMIS account, they may set a new PIN from their own profile.

Flow:

```text
Authenticated HRMIS user
        ↓
My Profile
        ↓
WhatsApp Support
        ↓
Change PIN
        ↓
New PIN
        ↓
Confirm
        ↓
Hash and replace existing PIN
        ↓
Increment security_version
        ↓
Invalidate active WhatsApp secure sessions
```

Do not offer PIN reset to HR representatives from the WhatsApp inbox.

System Administrator/HR should not be able to view the employee's PIN.

---

# 9. PIN Rules

The Support PIN must:

- contain exactly **4 numeric digits**;
- reject blank values;
- reject non-numeric values;
- reject values longer or shorter than 4 digits;
- reject obvious weak values.

At minimum block:

```text
0000
1111
2222
3333
4444
5555
6666
7777
8888
9999
1234
4321
1212
1122
```

Optional additional checks:

- reject last four digits of registered mobile number;
- reject last four digits of CNIC;
- reject employee birth year.

User-facing error:

> Please choose a less predictable 4-digit PIN.

Do not reveal sensitive matching rules.

---

# 10. Data Model

## Recommended DocType

**WhatsApp Security Profile**

One record per Employee/User.

Fields:

| Field | Type | Purpose |
|---|---|---|
| user | Link/User | HRMIS account |
| employee | Link/Employee | Employee record |
| pin_hash | Internal/password-hash storage | One-way hash only |
| pin_is_set | Check | Fast status check |
| pin_status | Select | Not Set / Active / Locked / Disabled |
| pin_created_on | Datetime | Audit |
| pin_changed_on | Datetime | Audit |
| failed_attempts | Int | Brute-force protection |
| locked_until | Datetime | Temporary lock |
| last_successful_verification | Datetime | Audit |
| last_failed_verification | Datetime | Audit |
| security_version | Int | Session invalidation |
| disabled_reason | Small Text | Optional |

### Important

Do not create:

```text
support_pin = "4827"
```

Do not store the PIN in recoverable encrypted form.

Store only a one-way password-style hash.

Use Frappe's secure password hashing utility if suitable, otherwise use a modern password-hashing implementation such as Argon2id/bcrypt configured appropriately.

---

# 11. User Profile Field / Portal Integration

The user asked for the PIN to be available from the employee/user profile.

Implement this as:

### UI-visible profile controls

- `Support PIN Status`
- `Set Support PIN`
- `Change Support PIN`

### Backend

Actual PIN hash should live in `WhatsApp Security Profile`.

If required for reporting, add read-only metadata fields to User/Employee:

```text
custom_whatsapp_support_pin_configured
custom_whatsapp_support_pin_status
custom_whatsapp_support_pin_last_changed
```

These fields are optional mirrors only.

Do not put the actual PIN or hash in a normal visible User Profile field.

---

# 12. Server APIs

Implement deterministic backend APIs.

## `get_support_pin_status()`

Authenticated HRMIS user or internal WhatsApp service.

Returns:

```json
{
  "configured": true,
  "status": "Active",
  "last_changed": "...",
  "locked_until": null
}
```

Never return PIN or hash.

---

## `set_support_pin(new_pin, confirm_pin)`

Authenticated HRMIS user only.

Responsibilities:

1. Resolve current User → Employee.
2. Confirm employee is allowed to use WhatsApp HR service.
3. Validate `new_pin == confirm_pin`.
4. Apply PIN rules.
5. Hash PIN.
6. Create/update WhatsApp Security Profile.
7. Set `pin_is_set = 1`.
8. Set `pin_status = Active`.
9. Reset failed attempts.
10. Clear lock.
11. Increment `security_version`.
12. Set timestamps.
13. Invalidate existing WhatsApp secure sessions.
14. Write security audit event.

Never log request parameters containing PIN.

---

## `verify_support_pin(employee, pin)`

Internal server-side method only.

Responsibilities:

1. Ensure PIN is configured.
2. Check lock status.
3. Verify hash.
4. On success:
   - reset failed attempts;
   - update last successful verification;
   - create secure session.
5. On failure:
   - increment failure counter;
   - update last failed verification;
   - apply lockout if threshold reached.
6. Return success/failure only.

Never return hash.

---

# 13. Secure WhatsApp Session

After correct PIN verification, create a temporary secure session.

Recommended TTL:

**24 hours**

Session should be bound to:

- Employee
- User
- Registered WhatsApp number
- Conversation
- Verification timestamp
- Expiry timestamp
- `security_version`

Recommended active-session storage:

- Redis/Frappe cache

Persistent DB record is optional for audit only.

---

# 14. Security Version

Every security profile has:

```text
security_version
```

Example:

```text
security_version = 4
```

When employee changes PIN in HRMIS:

```text
security_version = 5
```

Any active WhatsApp session created under version `4` becomes invalid immediately.

Protected services must check:

```text
session.security_version == profile.security_version
```

before execution.

---

# 15. Protected-Service Middleware

Do not add PIN logic separately to every handler.

Create common middleware.

Suggested function:

```python
authorize_whatsapp_service(context, service_key)
```

Logic:

```text
Load service security policy
       ↓
Does service require PIN?
       ↓
NO → continue
       ↓
YES
       ↓
PIN configured?
       ↓
NO → Portal setup message
       ↓
YES
       ↓
Valid secure session?
       ↓
YES → continue
       ↓
NO
       ↓
Set conversation state WAITING_FOR_SUPPORT_PIN
       ↓
Store pending service
       ↓
Ask for PIN
```

---

# 16. Conversation State

Add:

```text
WAITING_FOR_SUPPORT_PIN
```

Store:

- pending service key
- pending menu action
- minimum safe pending context
- request timestamp

Example:

```json
{
  "state": "WAITING_FOR_SUPPORT_PIN",
  "pending_service_key": "salary_slip"
}
```

After successful PIN verification:

1. clear PIN state;
2. create secure session;
3. automatically invoke `salary_slip`.

---

# 17. Credential Redaction — Mandatory

PIN input must be intercepted **before normal WhatsApp logging**.

When:

```text
conversation.state == WAITING_FOR_SUPPORT_PIN
```

and inbound text matches expected PIN format:

do not persist raw message text.

Instead save:

```text
[SUPPORT PIN REDACTED]
```

or skip message-body persistence entirely.

Raw PIN must never enter:

- WhatsApp Message Log
- WhatsApp Conversation transcript
- HR live chat
- HR case summary
- analytics
- exception logs
- debug logs
- AI prompts
- RAG/indexer
- usage logs
- email notifications

AI integration later must occur **after** credential interception.

---

# 18. Failed PIN Attempts

A 4-digit PIN requires strict rate limiting.

Recommended:

```text
Maximum attempts: 5
Lock duration: 30 minutes
```

Incorrect attempt:

> ❌ The PIN you entered is incorrect. Please try again.

After fifth failed attempt:

> 🔒 **Secure access has been temporarily locked.**
>
> Please try again after 30 minutes.
>
> If you have forgotten your PIN, log in to the HRMIS Portal to set a new one.

Buttons:

- **Open HRMIS Portal**
- **Main Menu**

A PIN change from HRMIS should clear the previous lock and invalidate sessions.

---

# 19. Security Events

Reuse existing `AI Security Event` if appropriate, or create a dedicated security log.

Record:

- PIN_SET
- PIN_CHANGED
- PIN_VERIFICATION_SUCCESS
- PIN_VERIFICATION_FAILED
- PIN_LOCKED
- SECURE_SESSION_CREATED
- SECURE_SESSION_EXPIRED
- SECURE_SESSION_INVALIDATED

Store:

- employee
- user
- WhatsApp number or masked number
- service requested
- timestamp
- result
- Meta message ID where useful

Never store the PIN.

---

# 20. Services That Should NOT Require PIN

Keep routine/support services easy for field staff.

No PIN:

- Main Menu
- General policies and SOP guidance
- HR contact details
- HR working hours
- Chat with HR
- Staff support/wellbeing access
- Confidential concern initiation
- Today's attendance status
- Attendance Check-In
- Attendance Check-Out

---

# 21. Attendance Security

Attendance should use a separate deterministic validation model:

```text
Registered WhatsApp Number
        +
Active Employee
        +
Employee eligible for WhatsApp attendance
        +
User-shared current location
        +
Assigned worksite/geofence validation
        +
Authoritative SERVER timestamp
```

### Time rule

Never trust:
- mobile device time;
- mobile device timezone.

Use:

- server authoritative timestamp;
- preferably store UTC;
- display/process HR attendance using `Asia/Karachi`.

Meta message timestamp may be retained for audit/cross-checking, but should not override the server attendance time.

---

# 22. Services That SHOULD Require PIN

PIN-protected:

- Leave balance
- Detailed attendance history
- Attendance personal records
- Leave application if personal details are surfaced
- Salary slip
- Payroll summary
- Salary deductions
- Tax certificate
- Personal profile
- CNIC/bank masked details
- Contract documents
- Employment letters
- Personal HR documents
- Sensitive travel/claim records
- Profile/document update flows

Service policy should be configurable.

---

# 23. Critical Updates — PIN + Approval

For critical employee-master changes:

```text
Registered WhatsApp
       +
Valid Support PIN
       +
Change Request
       +
Required HR / Finance Approval
```

Examples:

### Bank account
Do not directly overwrite an already verified payroll bank account.

Create change request → HR/Finance review → apply after approval.

### CNIC / legal identity
Create change request → HR verification → apply after approval.

### Registered WhatsApp/mobile
Controlled HR process.

An unrecognized phone number must never be able to claim an existing employee account using only personal information.

---

# 24. HR Live Chat Behavior

The HR representative must never see the PIN.

If the employee enters a PIN while in verification mode:

HR Inbox should show something like:

```text
🔐 Support PIN submitted — [REDACTED]
```

or no employee message at all, followed by:

```text
✅ Employee identity verified for protected services
```

Do not allow an HR representative to ask:

> Tell me your Support PIN.

Include a UI hint:

> MicroMerger staff should never request an employee's Support PIN.

---

# 25. Future AI Agent Rule

When AI Agent is implemented later:

```text
WhatsApp Message
      ↓
Identity
      ↓
Security Middleware
      ↓
Credential interception / authorization
      ↓
ONLY THEN
      ↓
AI Agent / ERP Tools
```

AI must never:

- see PIN text;
- validate PIN;
- decide authorization level;
- create/change/reset PIN;
- bypass service-security middleware.

Every ERP tool must independently check authorization context.

---

# 26. Suggested Code Structure

Adapt to actual app structure after inspecting the repository.

```text
ai_workplace/
│
├── security/
│   ├── support_pin.py
│   ├── authorization.py
│   ├── secure_session.py
│   ├── credential_redaction.py
│   └── security_events.py
│
├── api/
│   └── support_pin.py
│
├── ai_workplace/doctype/
│   ├── whatsapp_security_profile/
│   └── whatsapp_service_security_policy/
│
├── conversation/
│   └── orchestrator.py
│
├── whatsapp/
│   └── webhook.py
│
└── tests/
    ├── test_support_pin.py
    ├── test_pin_portal.py
    ├── test_pin_whatsapp.py
    ├── test_secure_session.py
    ├── test_pin_redaction.py
    ├── test_pin_lockout.py
    └── test_service_authorization.py
```

HRMS frontend:

```text
hrms/frontend/   ← HRMIS team owns PIN UI in User Profile
    Profile/     (Set/Change PIN fields — calls ai_workplace APIs)
```

Before creating new portal files, HRMIS team should use the API contract from `ai_workplace/api/support_pin.py`. `ai_workplace` inspects webhook, orchestrator, and audit patterns only.

---

# 27. Cursor Implementation Phases

## Phase PIN-1 — Repository Review

Before coding:

1. Inspect current WhatsApp webhook.
2. Inspect employee identity resolver.
3. Inspect orchestrator/session implementation.
4. Inspect User/Employee profile frontend.
5. Inspect Frappe password/hash utilities.
6. Inspect current security/audit DocTypes.
7. Inspect existing cache/session utility.
8. Inspect menu/service registry.

Output a short implementation mapping showing what will be reused vs created.

Do not duplicate existing functionality.

---

## Phase PIN-2 — Data Model + Backend Security Service

Build:

- `WhatsApp Security Profile`
- optional service security policy
- PIN policy validator
- PIN hashing
- PIN verification
- failed attempt counter
- lockout
- security version
- audit events

Tests:

- valid PIN
- invalid PIN
- weak PIN rejection
- hash verification
- five-failure lock
- lock expiry
- PIN update security-version increment

Exit criteria:

PIN is never stored or returned in plain text.

---

## Phase PIN-3 — HRMIS Profile UI (HRMIS team)

**Owner: HRMIS team** — not `ai_workplace`.

**Dependency (ai_workplace / PIN-2):** whitelisted APIs must exist before HRMIS UI ships:
- `get_support_pin_status()`
- `set_support_pin(new_pin, confirm_pin)`

HRMIS team builds in **User Profile** (My Profile):

- show registered WhatsApp number (from Employee);
- show PIN status (Not Set / Active);
- **Set 4-Digit PIN** / **Change PIN** fields with confirm;
- simple validation messages (client-side + API errors).

On successful set/change, HRMIS calls `set_support_pin`; backend handles hash, security_version, session invalidation.

**ai_workplace does not build** `ProfilePanel.vue` / portal Vue components for PIN.

Exit criteria:

A normal field employee can set/change PIN from HRMIS user profile in a few simple steps; WhatsApp can verify it.

---

## Phase PIN-4 — WhatsApp Authorization Middleware

Build:

- service security classification;
- secure-session lookup;
- no-PIN configured handling;
- `WAITING_FOR_SUPPORT_PIN`;
- PIN request;
- verification;
- auto-resume pending service.

Exit criteria:

Protected service cannot execute without a valid secure session.

---

## Phase PIN-5 — Credential Redaction

Modify webhook/message pipeline.

Credential detection must happen before ordinary logging.

Test that a known test PIN such as `4827` does not appear anywhere in:

- database message logs;
- HR inbox;
- application logs;
- error logs;
- conversation transcript;
- analytics;
- AI payloads.

Exit criteria:

Search entire test database/log set and confirm raw test PIN is absent.

---

## Phase PIN-6 — Session + Lockout Hardening

Implement:

- 24-hour secure-session TTL;
- security-version check;
- session invalidation on PIN change;
- 5-attempt lock;
- 30-minute lock;
- correct user messaging;
- security events.

Exit criteria:

Old session stops working immediately after Portal PIN change.

---

## Phase PIN-7 — Classify Existing Services

Review every existing WhatsApp service and assign:

- No PIN
- PIN Required
- PIN + Approval

Do not change employee-facing service behavior unnecessarily.

Prioritize usability.

---

## Phase PIN-8 — End-to-End Testing

Test at least:

### PIN lifecycle
- no PIN → Portal instruction
- set PIN in Portal
- return to WhatsApp
- verify
- protected service continues
- change PIN in Portal
- old PIN fails
- current secure session invalidated
- new PIN succeeds

### Failure
- wrong PIN
- five failures
- lock
- lock expiry
- change PIN while locked

### Services
- salary slip
- leave balance
- detailed attendance
- contract
- profile
- HR chat
- attendance Check-In/Out without PIN

### Security
- PIN not logged
- PIN not visible to HR
- PIN not sent to AI
- PIN hash cannot be retrieved through API
- authorization enforced server-side

---

# 28. Acceptance Criteria

Do not mark the feature complete until all are true:

1. PIN is created only in authenticated HRMIS Portal.
2. PIN can be changed/reset only in authenticated HRMIS Portal.
3. WhatsApp cannot create/reset/change/recover PIN.
4. PIN is exactly 4 numeric digits.
5. Actual PIN is stored only as a one-way hash.
6. HR/System Manager cannot view existing PIN.
7. Protected WhatsApp services require PIN verification or a valid secure session.
8. Successful verification resumes the originally requested service.
9. Secure session expires after configured TTL.
10. Changing PIN invalidates existing secure sessions.
11. Five failed attempts cause temporary lockout.
12. Raw PIN is never persisted in WhatsApp logs or HR Inbox.
13. Raw PIN is never sent to AI.
14. Attendance Check-In/Out remains PIN-free.
15. Attendance uses authoritative server time, not phone time.
16. Critical master-data updates require approval in addition to PIN.
17. Security rules are server-side and cannot be bypassed by menus/UI.
18. Existing public/basic services remain simple for field employees.

---

# 29. Product Principle

The security feature must remain nearly invisible during normal use.

Employees should understand only three things:

1. **Set your 4-digit Support PIN once in HRMIS Portal.**
2. **Enter it in WhatsApp when accessing private HR information.**
3. **If you forget it, log in to HRMIS Portal and set a new PIN.**

Everything else — hashing, session control, redaction, lockout, auditing, authorization and AI isolation — must happen securely in the backend.
