# WhatsApp Menu Implementation Plan (Revised)

**Saved:** 2026-08-28 (updated 2026-08-31 — Employee-First UX)  
**Target implementation:** Monday (Phase 1 first)  
**App:** `ai_workplace` | **Site:** `erp.v15`

> **Employee-first redesign (2026-08-31):** See [`EMPLOYEE_FIRST_WHATSAPP_UX_IMPLEMENTATION.md`](EMPLOYEE_FIRST_WHATSAPP_UX_IMPLEMENTATION.md) for the MicroMerger Staff Support rebrand, menu restructure, and Phase 1 deterministic routing (no LLM on free-text).

---

## Product decisions (confirmed)

| Topic | Decision |
|-------|----------|
| **Tax (`pay_tax_deduction`)** | Use existing Portal API — annual **Tax Certificate** via `hrms.api.employee.download_salary_certificate` (same as Portal). Deliver PDF on WhatsApp (not a custom tax text summary). |
| **Missing attendance (`att_missing`)** | **Read-only in v1.** Show discrepancies only. **No** WhatsApp regularization / `Attendance Request` submit in this version. |
| **Update profile (`update_profile`)** | Show **Portal instructions** for self-service profile update (no WhatsApp form, no Basic Information step flow). |
| **Jobs (`guest_careers`, `guest_job_status`, `former_careers`)** | Guide users to official job portal **https://www.xpertjobs.com** — no ERP `Job Opening` / `Job Applicant` integration. |
| **Next major feature** | **AI policy Q&A + AI support bot** — first-line automated help before a real HR representative (Contact HR live chat). |

---

## Monday checklist — Phase 1

- [x] **Tax Certificate PDF** (`pay_tax_deduction`) — `services/tax_certificate.py`, orchestrator wired
- [x] **Portal profile instructions** (`update_profile`) — Profile Completion Hub in `services/profile_completion.py`
- [x] **Missing attendance messaging** (`att_missing`) — guidance footer via `services/attendance_guidance.py`
- [x] **XpertJobs guide** (`guest_careers`, `guest_job_status`, `former_careers`) — `services/careers_guide.py`, orchestrator wired
- [ ] Tests for tax certificate + careers guide
- [ ] `bench restart` after deploy

---

## Current coverage summary

| Status | Count | Meaning |
|--------|-------|---------|
| **Implemented** | 28 leaf services | Real ERP data, PDF, or multi-step submit |
| **Partial** | 3 | Shows info but incomplete UX |
| **Placeholder** | 3 | "Available soon" via `build_service_placeholder_response` |
| **Navigation only** | 6 top-level | Open submenus only |

Flow actions (`pay_slip_1m`, `att_monthly_last7`, etc.) are **implemented**.

---

## Menu status matrix

### Active Employee — My HR

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `my_profile` | Done | — |
| `supervisor_reporting` | Done | — |
| `update_profile` | Partial | **Portal instructions message** |

### Active Employee — Attendance & Leave

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `att_today` | Done | — |
| `att_monthly` | Done | — |
| `att_missing` | Partial (read-only) | **Keep read-only** + clarify Portal/supervisor path |
| `leave_balance` | Done | — |
| `leave_apply` | Done | — |
| `leave_requests` | Done | — |

### Active Employee — Salary & Payroll

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `pay_download_slip` | Done | — |
| `pay_previous_slips` | Done | — |
| `pay_tax_deduction` | Done | Annual Tax Certificate PDF (Portal report) |
| `pay_experience_letter` | Done | — |
| `pay_bank_letter` | Done | All active staff types (partial payroll menu for deliverable consultants) |

### Active Employee — Travel (Phase 3 — Done)

| Menu key | Status | Notes |
|----------|--------|-------|
| `trv_approved` | Done | Approved `Travel Authorisation Request Form` itineraries |
| `trv_upcoming` | Done | Upcoming travel legs (from_date ≥ today) |
| `trv_claim_status` | Done | Recent `Employee Expense Claim` status |
| `trv_vehicle_info` | Done | Employee commute / vehicle + upcoming travel vehicle type |
| `trv_sop` | Done | Travel / DSA policy PDF from `System Notifications` |
| `trv_problem` | Done | Redirects to confidential Concern report flow |

### Project Deliverable staff — Deliverables (Phase 2 — Done)

| Menu key | Status | Notes |
|----------|--------|-------|
| `deliverables` | Done | Top-level submenu (Contract Deliverable staff only) |
| `dlv_add` | Done | Multi-step draft creation → `Consultant Deliverable` (with per-line attachments) |
| `dlv_submit` | Done | Submit draft for supervisor approval |
| `dlv_status` | Done | List recent deliverables with workflow status |

### Active Employee — Policies (Phase 4 — AI)

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `pol_ai_assistant` | Missing | **AI Q&A + support bot before HR** |

### All user types

| Menu key | Status |
|----------|--------|
| `concerns` / `guest_concern` / `former_concern` | Done |
| `contact_hr` | Done (live HR chat) |

### Former Employee

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `former_letter` | Done | — |
| `former_payslip` | Done | — |
| `former_verification` | Missing | Phase 5 |
| `former_concern` | Done | — |
| `former_careers` | Done | XpertJobs portal guide |

### Guest

| Menu key | Status | v1 target |
|----------|--------|-----------|
| `guest_careers` | Done | XpertJobs portal guide |
| `guest_job_status` | Done | XpertJobs portal guide |
| `guest_verification` | Missing | Phase 5 |
| `guest_vendor` | Missing | Phase 5 |
| `guest_concern` | Done | — |
| `guest_number_changed` | Partial | Phase 5 upgrade |

---

## Staff-type menu matrix (Phase 2 — Done)

Menus are driven by `Employee.employment_type` via `context/resolver.py` (`staff_category` + `allowed_services`).

| Category | `employment_type` | WhatsApp menus |
|----------|-------------------|----------------|
| **Permanent** | Anything except `Contract`, `Contract (Deliverable)` | Full: HR, Attendance & Leave, Salary & Payroll, Travel, Policies, Concerns, Contact HR |
| **Project Contract** | `Contract` | HR, Attendance & Leave, Payroll, Policies, Concerns, Contact HR — **+ Travel** when employee has an active `Expense Claim Structure Assigment` |
| **Project Deliverable** | `Contract (Deliverable)` | HR, Deliverables, **Payroll documents** (Tax Certificate + Bank Letter only), Policies, Concerns, Contact HR — **+ Travel** when employee has an active `Expense Claim Structure Assigment` |

Legacy Consultant-role menus (`engagement`, `timesheet`, `invoice`) are **removed** — employment type is the sole driver.

---

## Phase 1 — Quick wins (Portal-aligned, low effort)

### 1. `pay_tax_deduction` — Annual Tax Certificate PDF

**Portal endpoint:** `GET /api/method/hrms.api.employee.download_salary_certificate`

**Backend chain (already in production):**
- Resolves active employee for session user
- Uses fiscal year from ERP
- Calls `mm_app.mm_hr.doctype.salary_slip_and_deduction_tool.salary_slip_and_deduction_tool.send_email` with `type_="PDF"`
- Report: **CNIC Wise Salary Slip & Certificate of Deduction**
- Generates landscape PDF via `get_pdf()`

**WhatsApp implementation:**
- New `ai_workplace/services/tax_certificate.py`
- Reuse same report + HTML template logic; return `(pdf_bytes, filename)` for WhatsApp media (pattern from `payroll.generate_salary_slip_pdf`)
- Set user context to employee ERP user before calling (same as leave apply)
- Wire orchestrator handler for `pay_tax_deduction`
- Caption: "Your annual Tax Certificate is attached."

### 2. `update_profile` — Portal instructions

Replace `build_update_profile_coming_soon_response` in `hr_profile.py` with:
- Log in to employee Portal (`frappe.utils.get_url()`)
- Steps: My Profile / Basic Information → update mobile, bank, address
- Urdu + Roman Urdu variants
- Fallback: Contact HR for urgent changes

### 3. `att_missing` — Read-only + guidance (no submit)

Keep `build_missing_attendance_response`. Add footer:
- Regularization **not available on WhatsApp in v1**
- Use Portal or contact supervisor / HR
- Do **not** build `attendance_regularize.py`

### 4. Jobs — XpertJobs portal guide

New `ai_workplace/services/careers_guide.py` for:
- `guest_careers`
- `guest_job_status`
- `former_careers`

Message: official portal **https://www.xpertjobs.com**, how to apply and track status.

---

## Phase 2 — Staff-type menus & Deliverables (Done)

- `context/resolver.py` — `staff_category` + employment-type `allowed_services`
- `menu/seed_data.py` — `deliverables`, `dlv_add`, `dlv_submit`, `dlv_status`
- `services/deliverables.py` — WhatsApp flow against `Consultant Deliverable` (mm_bpo)
- Orchestrator + auth gateway wiring
- Tests: `test_context_resolver`, `test_deliverables`, `test_dynamic_menu`, `test_auth_gateway`

---

## Phase 3 — Travel self-service (Done)

Built `ai_workplace/services/travel.py`:
- `trv_upcoming` / `trv_approved` — Travel Authorisation Request Form
- `trv_claim_status` — Employee Expense Claim
- `trv_vehicle_info` — Employee commute / vehicle details
- `trv_sop` — policy PDF from `System Notifications`
- `trv_problem` — redirect to `concerns` workflow

Orchestrator wiring + tests: `test_travel.py`

---

## Phase 4 — AI Policy Q&A + Support Bot (after Phase 1)

**Goal:** Answer policy and common HR questions before live chat.

New `ai_workplace/services/policy_assistant.py`:
- Load policies via `hrms.api.employee.get_policies` / `get_policies_data`
- Free-text Q&A with policy context
- Escalate to Contact HR when bot cannot help
- Session: `current_intent = "ai_assistant"`, `PROCESSING` state

---

## Phase 5 — Remaining guest/former

- `guest_verification` / `former_verification`
- `guest_vendor`
- `guest_number_changed` (upgrade from stub)

---

## Phase 6 — New hire onboarding (AI Agent)

Orientation playbooks for new hires via HR Agent on WhatsApp.

---

## Removed from v1 scope

| Item | Reason |
|------|--------|
| WhatsApp attendance regularization submit | Explicitly excluded |
| Custom tax text rollup | Replaced by Portal tax certificate PDF |
| ERP Job Opening / Applicant integration | Replaced by XpertJobs portal guide |
| Basic Information WhatsApp step flow | Replaced by Portal instructions |

---

## Priority order

| Priority | Feature | Effort |
|----------|---------|--------|
| **P0** | Tax Certificate PDF | Low — **Done** |
| **P0** | Portal profile instructions | Very low |
| **P0** | XpertJobs careers guide | Very low — **Done** |
| **P0** | att_missing messaging polish | Very low |
| **P1** | Staff-type menus + Deliverables | Medium — **Done** |
| **P1** | Travel status services | Medium — **Done** |
| **P1** | AI policy Q&A + support bot | High |
| **P2** | Guest verification / vendor / number change | Medium |

---

## Phase 1 files to touch

| File | Change |
|------|--------|
| `services/tax_certificate.py` | New — PDF generation wrapper |
| `services/careers_guide.py` | New — XpertJobs instructions |
| `services/hr_profile.py` | Portal instructions for update_profile |
| `services/attendance_leave.py` | att_missing footer |
| `conversation/orchestrator.py` | Wire pay_tax_deduction + careers menus |
| `auth/gateway.py` | Authorize pay_tax_deduction if needed |
| `tests/test_tax_certificate.py` | New |
| `tests/test_careers_guide.py` | New |

---

## Key reference paths

- Menu seed: `ai_workplace/menu/seed_data.py`
- Orchestrator: `ai_workplace/conversation/orchestrator.py`
- Portal tax API: `hrms/hrms/api/employee.py` → `download_salary_certificate`
- PDF generator: `mm_app/mm_app/mm_hr/doctype/salary_slip_and_deduction_tool/salary_slip_and_deduction_tool.py`
- Payslip PDF pattern: `ai_workplace/services/payroll.py`
