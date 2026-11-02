# Guided conversations and unfinished-task reminders

This first release extends existing leave workflows, hybrid policy responses, and company-information
answers from both hybrid and agentic generation paths.
It uses approved knowledge and ERP tools; it does not change leave submission,
permission checks, or the requirement to confirm transactions.

## Behavior

- Supported policy answers offer one relevant next question. Missing knowledge
  does not trigger an engagement prompt. Generic closing messages are removed
  when a specific next question is available.
- Short replies to a policy clarification inherit the previous policy topic.
  Explicit new intents and menu selections route normally.
- Existing leave application steps retain their draft and collect information
  using the established validation. The guidance memory stores only dates, leave
  type, half-day choice, and the next question, not free-text reasons or PINs.
- Continue repeats the pending question. It never submits a transaction. A Yes/No
  response during leave confirmation still reaches the existing workflow.
- A pending reminder is cancelled on a new inbound message. An unfinished leave
  step can schedule a fresh due time while preserving the one-reminder limit.
- Dismiss or `stop reminders` disables catch-ups for the current conversation.
  Remind me later explicitly permits one more catch-up.
- Web conversations have guidance but no scheduled WhatsApp outbound messages.

## Deployment

From the real Frappe bench, run `bench --site <site-name> migrate` to sync the new
conversation and settings fields and scheduler hook. Restart the site's workers
using your normal deployment procedure and confirm its scheduler is enabled.

AI Workplace Settings contains:

| Setting | Default |
| --- | --- |
| Enable Guided Conversations | On |
| Enable Unfinished Conversation Reminders | Off |
| Catch-up Delay (Minutes) | 60 |
| Quiet Hours Start | 20 |
| Quiet Hours End | 9 |

Quiet hours use the Frappe site timezone, not the worker machine timezone. Equal
start/end hours disable quiet hours. A reminder deferred overnight must still
satisfy the 23-hour freshness limit. Enable reminders after verifying recipient
and custom WhatsApp session routing in a test site. They are disabled initially
because this repository checkout has no configured Frappe site or messaging
credentials to validate delivery.

Unfinished conversations with scheduled reminders retain their draft until at
least 12 hours after the due time. Normal conversation cleanup then applies.
The memory and due/status fields are stored on WhatsApp Conversation, separately
from `draft_payload`. This release does not introduce a separate follow-up DocType.

## Delivery guarantees and limits

The scheduler processes up to 100 due conversations per run. Before delivery it
checks conversation status, latest activity, employee/user/identity linkage,
active employee status, enabled user, human HR ownership, and channel. It only
sends free-form catch-ups within a conservative 23 hours of the last recorded
inbound turn. Outside that limit it cancels; it does not send template messages.
No new factual HR claims are generated in a catch-up.

A database row lock and durable Claimed status prevent two scheduler workers
from sending the same reminder. Inbound handling revokes Pending/Claimed work,
and delivery rechecks its claim immediately before sending. A message already
in flight at the provider cannot be recalled if a reply arrives simultaneously.

Successful/failed deliveries are recorded in WhatsApp Message Log. The scheduler
never automatically retries an uncertain network delivery; a crash after claiming
may leave Claimed status for administrator inspection. Sent/Failed/Claimed
records must not be reset blindly because a provider may have delivered them.

Scope limits: notification preference is per conversation; no account-wide
opt-out UI is added. Leave inputs continue through the existing step sequence;
this release does not add extraction of an entire leave application from one
sentence, or arbitrary topic switching inside an active transactional draft.
Knowledge metadata, retrieval ranking, and ingestion remain unchanged.

## Verification

Run without a Frappe site:

```sh
python3 -m unittest ai_workplace.tests.test_conversation_guidance -v
```

On a test site, run the existing Frappe suite and verify:

1. A grounded leave-policy answer offers a useful next step in each supported language.
2. Leave draft details survive inactivity and Continue does not submit the draft.
3. A new reply, completed application, Dismiss, or live HR chat stops stale reminders.
4. A due reminder reaches the correct recipient and custom WhatsApp account once.
5. Quiet hours, disabled users, reassigned identities, web chats, and stale windows
   suppress delivery.

## Company discovery

Public company questions such as “what do you know about micromerger” receive
concise-answer instructions in both the hybrid handler and HR agent. Brief
answers are bounded at complete sentence/line boundaries when possible. Explicit
requests for detail (including “detailll”, full explanations, Urdu and Roman Urdu
depth requests) bypass that bound and use thorough-answer instructions. A single
long sentence is preserved rather than cutting a factual statement midway.
The instructions avoid unsolicited statistics and promotional claims; all company
facts must still come from the retrieved evidence.

After a supported company introduction, the assistant asks whether the user wants
services, careers, or company background, in the selected language. After a
services answer it asks which service to explore. This replaces the separate
“Type another message…” closing. Follow-up choices are routed through existing
knowledge/careers services; explicit new HR questions keep normal routing.
The optional catch-up settings and delivery restrictions apply to company topics.
No reminder is sent to guest identities without a linked active employee/user.

During rolling deployments, supported answers can display their next question
without the new conversation fields. Durable memory and reminder scheduling
remain disabled for such documents until migration. An unset new guidance setting
uses its enabled default for response presentation; an explicit disabled value
is always respected. If a production reply still has the generic closing, verify
that the new workers are running, guidance is enabled, and retrieval returned
supporting evidence; this checkout cannot inspect the live site's configuration.
