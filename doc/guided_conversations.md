# Guided conversations

The conversation layer now covers policy/company knowledge, supported employee
read services, resumable forms, reminder preferences, and engagement reporting.
Existing ERP validation and final transaction confirmations remain authoritative.

## What users can do

- Ask a policy, company, leave, attendance, payroll, travel, profile, careers,
  onboarding, or document question and receive a relevant next question when
  supporting results exist. Plain factual questions remain concise; explicit
  requests for detail use a fuller answer.
- Answer a suggested choice with a short reply. Supported choices reenter normal
  service routing, including authentication, authorization, and PIN checks.
- Supply a leave request in one message, for example:
  `Apply for annual leave from 2026-12-10 to 2026-12-12 full days because family trip`.
  Explicit fields are reused; missing or ambiguous fields are requested. This
  reaches the review screen but never submits automatically.
- Switch to a recognized different topic while filling a leave, attendance
  request, or travel form. The form is parked privately for later continuation.
- Send `pause`, `my tasks`, `resume 1`, or `resume leave` to manage saved work.
  A protected task requires current access and a valid PIN session before restore.
  Resume never counts as Yes or Submit. Expiring sessions also save supported work.
- Send `stop reminders` or `start reminders` to change account-wide preferences,
  including across web/WhatsApp conversations linked to the same ERP user.
- Send `reminder settings` to view preference status and
  `quiet hours 20 9 Asia/Karachi` to set personal quiet hours and timezone.
- Use Continue, Remind me later, or Dismiss on a catch-up. Dismiss affects the
  current conversation; Stop reminders affects the whole account.

The parser supports ISO dates, English day/month-name dates with optional year,
shared-month ranges, today, tomorrow and next weekday. It never guesses an
ambiguous numeric date, missing end date, leave reason, or half-day choice.
Duration-only requests are clarified rather than assuming calendar/working days.

Task suspension is limited to leave, attendance requests, travel requests, travel
support, and informational guidance. Identity verification, PIN entry, live HR,
media/location check-in and sensitive profile update flows keep exclusive routing.
Those flows continue using their existing menus and handlers.

## Settings and deployment

Run from the real site's Frappe bench:

```sh
bench --site <site-name> migrate
bench build --app ai_workplace
```

Restart web and background workers with your deployment's usual process. Confirm
that the site's scheduler is enabled. The post-model migration backfills validity,
scoping and guidance metadata on existing knowledge chunks without embedding API
calls, and removes unmapped/unapproved legacy knowledge-entry chunks.

AI Workplace Settings contains:

| Setting | Default |
| --- | --- |
| Enable Guided Conversations | On |
| Enable Unfinished Conversation Reminders | Off |
| Catch-up Delay | 60 minutes |
| Site quiet hours | 20:00–09:00, site timezone |

Account preferences can further restrict reminders and add personal quiet hours;
they cannot override disabled site reminders or site quiet hours. Enable outbound
reminders only after verifying test-site delivery to the correct WhatsApp account.
Web conversations do not send scheduled WhatsApp messages. Guest identities do
not receive scheduled employee reminders. Display-only guidance can work before
migration; durable tasks/preferences/reporting require the new schema.

Authenticated self-service endpoints:

- `ai_workplace.api.conversation_preferences.get_preferences`
- POST `ai_workplace.api.conversation_preferences.update_preferences`

These endpoints always target `frappe.session.user`; they accept no other user's
identifier. The preference DocType itself remains restricted to System Managers.

## Knowledge authoring

AI Knowledge Entry and AI Workplace Knowledge Source now expose:

- `guided_questions`: JSON with optional English, Urdu, and Roman Urdu questions,
  each at most 500 characters, for example
  `{"English":"Which department does your question concern?"}`.
- `related_intent`: a registered application intent to offer as the next step.
- Department/location applicability, versions, effective-from and effective-to
  metadata propagated into retrieval chunks.

Only applicable and currently effective content is retrieved. When a restricted
scope has no matches, retrieval does not widen to other departments/locations.
Related actions route through normal services and never grant extra permissions.
Unpublishing a previously indexed entry removes its stable-ID chunks.

## Engagement reporting

The existing Admin Dashboard has an Engagement tab. The System-Manager-only
endpoint `ai_workplace.api.conversation_engagement.get_engagement` exposes the same
aggregates: guided conversations, response rate, completions, resumes, reminders,
dismissals, knowledge gaps, tokens and topic counts. Response rate means the share
of guided conversations with a subsequent reply to the same topic in the selected
period. Reply counts include user decisions to stop/continue, not satisfaction.
The complete dashboard payload includes these metrics under `engagement`.

Events store categories, counters and conversation references, never draft text,
free-text medical reasons, PINs, or employee field values. Model tokens/cost use
router-reported accounting; agentic answers accumulate all planner calls. Metrics
failures are isolated so a successful ERP action remains successful.

## Persistence and delivery guarantees

- Private task snapshots are scoped to ERP user, employee, identity and channel.
  At most ten are retained per scope, for seven days. A daily job removes expired
  tasks and events older than 90 days. Resuming a task rechecks ownership, expiry,
  current authorization and applicable PIN policy.
- Conversation guidance memory stays separate from workflow drafts and snapshots.
  Shared knowledge never receives private task content.
- Catch-ups require a fresh, unfinished conversation, unchanged identity, active
  employee, enabled user, allowed account preferences, and no active human chat.
  They are cancelled after a reply/completion/dismissal and not sent beyond the
  conservative 23-hour free-form freshness limit. No template sending is added.
- A database row lock and durable claim prevent competing scheduler workers from
  sending twice. Provider delivery already in flight cannot be recalled.
- Failed or uncertain sends are not automatically retried. Claimed records after
  worker crashes require administrator inspection; do not reset them blindly.
- Delivery results are also recorded in WhatsApp Message Log.

## Verification

Without a Frappe site:

```sh
python3 -m unittest ai_workplace.tests.test_conversation_guidance ai_workplace.tests.test_advanced_conversation -v
node --check ai_workplace/public/js/admin_dashboard/admin_dashboard_render.js
```

Before production rollout, test the existing Frappe suite and exercise: short and
long company answers; missing knowledge; all supported read categories; a complete
one-message leave request; topic switches with multiple parked tasks; session
expiry and cross-session resume; revoked permissions; protected travel resume;
account preference changes; overnight quiet hours; reminder delivery and duplicate
webhooks; approved/expired/scoped knowledge; and the Engagement dashboard date
filters. This checkout has no Frappe runtime, configured site, or live messaging
credentials, so it cannot validate those deployment checks locally.
