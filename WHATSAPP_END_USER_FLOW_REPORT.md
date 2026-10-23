# WhatsApp end user flow and access report

**Scope:** repository implementation for the Baileys/custom WhatsApp API path, including identity resolution, employee categories, menu generation, authorization, PIN checks, conversation routing, and outbound formatting. This is a code-path analysis; actual menu labels and active items can also be changed in ERPNext's `WhatsApp Menu Item` records, and runtime settings/database state were not available in this repository review.

## Executive summary

Incoming messages use one shared conversation engine whether the transport is Meta Cloud API or a custom Baileys-compatible API. The custom transport changes webhook authentication and outbound formatting; identity, context, menu eligibility, service permissions, and PIN logic stay in the same application path.

The user is classified primarily by phone-number matching:

| Result | Matching rule | Person type / menu category | Broad menu access |
|---|---|---|---|
| Active employee | Exactly one active Employee/User candidate, or one selected by the multiple-profile project rule | Employee / Active Employee | Employee services filtered by `employment_type`; permissions and selected live checks further constrain actions |
| Former employee | Number matches an Employee or User candidate, but no matched candidate is active | Former Employee | Former letters, payslips/tax documents, employment verification, concerns, careers, HR contact |
| Guest | No ERP identity matches | Guest | Careers, job application status, employment verification intake, vendor support, concerns, HR contact, changed-number request |
| Ambiguous | Multiple active matches cannot be resolved by the project rule | Guest category in menu registry; context is not treated as a former employee | Guest menu is the intended safe menu; user-specific ERP data is not attached |

Active staff are then separated by `Employee.employment_type`: `Contract (Deliverable)` gets project-deliverable access; `Contract` gets project-contract access; all other or blank values default to permanent access. There is no separate menu category for these staff types: all are `Active Employee`, with the `allowed_services` list doing the filtering.

## End-to-end request flow

1. **Webhook authentication.** `receive` reads the raw body. With `custom_whatsapp_api_enabled`, it accepts either a configured bearer token or `X-Custom-Api-Token`. If custom mode is enabled but no token is configured, the inbound request is accepted without signature validation. Otherwise it validates Meta's `X-Hub-Signature-256`.
2. **Payload parsing and filtering.** The parser normalizes provider payloads. Empty/unsupported/status events are acknowledged; duplicate message IDs are skipped. Self-echo messages are dropped. Media and location are routed through specialized handlers.
3. **Identity resolution.** The sender phone is normalized, then matched against Employee `cell_number`/`company_mobile` and User `phone`/`mobile_no`. Employee candidates include statuses Active, Left, and Inactive. A linked User must also be enabled for the combined candidate to count active.
4. **Identity persistence and audit.** A `WhatsApp Identity` is created/updated with Active, Guest, Ambiguous, or Inactive status. Inbound content is logged (PIN-shaped content redacted where applicable); guest/inactive/ambiguous events are recorded as security events.
5. **Conversation processing.** The webhook enqueues asynchronous processing by default outside tests, unless `async_whatsapp_enabled` is off. Active HR live-chat sessions receive inbound text directly. Other text goes to `process_message`.
6. **Context and menu.** Context is built from the resolved identity and Employee record. The menu is loaded from active `WhatsApp Menu Item` rows by category, then filtered by `allowed_services`. Custom mode uses grouped numbered text menus instead of Cloud API native interactive lists/buttons.
7. **Selection and execution.** User input can be an interactive ID, number, title, or alias. The orchestrator handles navigation, multi-step workflow state, direct service authorization, PIN step-up, service handler dispatch, and AI intent routing.
8. **Reply.** `send_message` turns the common outbound representation into a custom API payload for Baileys, posts it to the configured URL, and logs the outbound result.

## What each persona sees

### Guest or unknown number

`get_user_context` sets `person_type = Guest`, with no employee roles/projects/manager and only guest services. The generic initial greeting intentionally does not confirm whether the phone exists in ERPNext. The seeded main menu is:

- Careers at MicroMerger
- I Applied for a Job
- Employment Verification
- Vendor / Supplier Support
- Report a Concern
- Contact HR (shared `All` item)
- My number has changed

Guests cannot access protected employee services: the authorization gateway denies when there are no allowed services, and direct employee-specific AI intents require an employee. Public intake/careers flows may proceed without ERP employee context. `contact_hr` is available across categories; the live HR intake implementation decides whether a request is queued/assigned.

### Former employee

An identity is called inactive/former when a phone-matched candidate exists but all candidates are inactive (including an Employee whose status is Left/Inactive or a disabled linked User). The generic greeting is the same as for a guest. The menu exposes:

- Experience / Service Letter
- Payslip & Tax Documents
- Employment Verification
- Report a Concern
- Career Opportunities
- Contact HR (shared `All` item)

Former letter and payslip/tax documents are PIN-gated in seed/security policy. The data request still depends on the former employee's employee record and the backend service implementation. Former employee context currently retains candidate `user`/`employee` only when produced by some callers; the phone resolver's `inactive` classification returns neither, so record-bound former self-service should be reviewed carefully (see findings).

### Active employee: permanent/default

An active candidate is an `Employee`; employment types other than the two exact recognized strings default to `permanent`. Allowed top-level service keys are:

- HR / My HR
- Attendance & Leave
- Payroll
- Travel
- Documents
- Staff Support
- Policies
- Concerns
- Contact HR

Seeded menus include the relevant children, including profile completion, attendance/leave, payroll and documents, travel, staff support, policies, and deliverables (deliverables appears in the seed but is not part of the permanent allowed-service list, so it should be filtered out).

### Active employee: Contract

`Contract` maps to `project_contract`. Its service list is the same core list as permanent staff (HR, attendance/leave, payroll, travel, documents, staff support, policies, concerns, HR contact). Travel is included only if there is an effective Expense Claim Structure Assignment as of today. The top-level menu still uses `Active Employee` category.

### Active employee: Contract (Deliverable)

`Contract (Deliverable)` maps to `project_deliverable`. The allowed services are HR, Deliverables, Payroll documents, Policies, Concerns, and Contact HR. It receives specific payroll document keys (tax deduction and bank letters) instead of full payroll/salary-slip access. Travel is added only when an effective Expense Claim Structure Assignment exists. Attendance/leave, general travel, documents, and staff support are not in this category's allowed list.

## Menu structure and multi-step flows

Top-level menu rows are sorted by the sequence configured in `WhatsApp Menu Item`; canonical seed sequence numbers for active staff put Payroll before Attendance & Leave, followed by Travel, Documents, HR, Staff Support, Policies, Deliverables, Contact HR. However, each category's allowed list removes unavailable parents.

Relevant seeded submenus include:

- **Attendance & Leave:** today's attendance, check-in/out, monthly attendance, missing attendance, leave balance, apply leave, attendance request, leave requests. Check-in/out is removed when location attendance eligibility fails; attendance request is removed when the permission checker fails.
- **Payroll:** salary slip, tax certificate, experience letter, bank letter. Salary slip periods (last / 3 months / 6 months), tax certificate year, and bank choice are separate flow prompts. Salary slips, tax documents, bank letters, experience letters require PIN according to menu/security rules.
- **Travel:** travel authorization, approved/upcoming travel, claim status, vehicle/driver, policy, support; employee data actions are PIN-protected.
- **Documents:** current contract, salary slip, tax certificate, experience letter, bank letter, and requests; personal documents require PIN.
- **HR/Profile:** view profile and submit profile updates; sensitive profile values require PIN, while CNIC/bank/education/work history requests require PIN plus approval.
- **Staff Support:** AI Policy Assistant, Supervisor Support (PIN), Confidential Concern, Chat with HR.
- **Deliverables:** add, submit for approval, view status.

Custom API mode converts Cloud interactive buttons/lists into plain text with numbered options and an option map so numbered replies resolve to the intended `svc_*` or menu key. For Urdu, numeric options can be emoji-numbered. The inbound parser accepts numeric replies (including a trailing period/Urdu stop), interactive IDs, titles, and aliases. This is why navigation/selection works over Baileys without native WhatsApp interactive messages.

## Authorization and security behavior

- Menu filtering is UX-level access control; the orchestrator also calls `authorize(...)` before running a selected service. Do not treat a hidden menu item as the only security boundary.
- The authorization gateway checks direct allowed service membership, known service-parent relationships, and selected aliases/sub-actions. Payroll has extra logic to distinguish full payslip access from document-only access.
- `maybe_gate_service` applies PIN policy after service authorization. Sensitive services require a configured Support PIN and valid secure session, or the user is sent into the PIN flow. PIN+Approval items imply an additional approval workflow in the service path.
- Personal/attendance/payroll details are not meant to be exposed to guests or ambiguous identities. AI tools also have explicit employee-required guards, with separate PIN checks for sensitive deterministic intents.
- Status/policy/service security is partly data-driven through menu and policy DocTypes; exact live configuration may override fallback values in code.

## Findings and items to validate

1. **Custom inbound auth can be open.** If custom API is enabled and its token is blank, webhook authentication is bypassed. Configure a strong token and require it at the Baileys webhook; ideally make missing token a hard failure.
2. **Inactive identity loses the matched employee key.** `_classify` returns `inactive` without `user`, `employee`, or `full_name`. Context consequently has no Employee ID. That may prevent former-letter/payslip retrieval and PIN checks (the PIN middleware currently allows a PIN-required service when `context.employee` is empty). This is a consequential mismatch: former menus are visible, yet record binding and step-up protection may not work as intended. Preserve the unique inactive candidate reference and verify secure record ownership before enabling former self-service.
3. **Menu records are runtime source of truth.** The seed documents intended labels/order, but ERPNext rows may differ, be inactive, or be edited. Compare the installed `WhatsApp Menu Item` records with seed data before treating this as the exact production menu.
4. **Employment type matching is exact and fallback is permissive.** Only exact `Contract` and `Contract (Deliverable)` names change access. Misspellings, capitalization differences, renamed types, and blanks default to permanent services. Validate the allowed `employment_type` values in HRMIS or replace exact string mapping with a controlled configuration.
5. **Phone reuse / multiple matches need operational validation.** The resolver handles multiple active matches by choosing exactly one candidate with an empty project; otherwise it marks ambiguous. This can select a profile based on a project field heuristic or lock out a person where phones are shared. Verify that the rule fits the organization's data and phone-sharing practices.
6. **Web Chat can differ from WhatsApp matching.** Authenticated web identities are marked matched if the User exists, even when no Active Employee record is found. The phone-based WhatsApp path instead considers Employee status and User enabled state. If both channels are in scope, align the classification policy.
7. **Service menu and security policy can drift.** Security policy can come from the menu item, active security-policy records, or code fallback. Audit production values for all payroll/profile/travel keys and ensure no sensitive item falls back to `None` unexpectedly.
8. **Baileys endpoint contract needs an integration smoke check.** Custom sends assume the configured URL accepts transformed JSON plus optional Bearer token and returns an optional `message_id`/`id`. Custom responses are treated as success even when the response body is invalid JSON (using a placeholder ID), so delivery confirmation depends on the bridge contract and logs.

## Suggested production validation checklist

1. Compare active ERPNext menu rows and service security policies with `ai_workplace/menu/seed_data.py`.
2. Validate identity outcomes for one Active permanent employee, `Contract`, `Contract (Deliverable)`, Left employee, disabled User, Guest, and ambiguous/shared number.
3. Confirm every former self-service handler resolves the employee from a safely verified identity and requires PIN before document disclosure.
4. Test custom webhook authentication with valid token, invalid token, and missing configured token; reject the last case.
5. Exercise Baileys numbered replies for top-level and submenu flows in English and Urdu, including number punctuation and back/main-menu navigation.
6. Verify async jobs, inbound/outbound logs, failure responses, and message IDs against the actual bridge API.

## Code references

- Identity resolution: `ai_workplace/identity/resolver.py`
- Persona, employment type, and allowed service mapping: `ai_workplace/context/resolver.py`
- Dynamic menu filtering: `ai_workplace/services/registry.py`
- Menu seed and flow definitions: `ai_workplace/menu/seed_data.py`
- Menu construction and selection: `ai_workplace/conversation/menu.py`
- Webhook/custom authentication and dispatch: `ai_workplace/api/whatsapp_webhook.py`
- Conversation state, routing, authorization, and PIN orchestration: `ai_workplace/conversation/orchestrator.py`
- Service authorization: `ai_workplace/auth/gateway.py`
- PIN policy and secure session: `ai_workplace/security/authorization.py`
- Baileys transform and custom send: `ai_workplace/whatsapp/sender.py`
