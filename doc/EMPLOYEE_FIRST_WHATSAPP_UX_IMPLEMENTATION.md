# Employee-First WhatsApp UX — Implementation Record

**Date:** 2026-08-31  
**App:** `ai_workplace` | **Site:** `erp.v15`  
**Scope:** Phase 1 deterministic employee services (no LLM)

---

## 1. Existing system reviewed

| Area | Path |
|------|------|
| WhatsApp webhook | `api/whatsapp_webhook.py` |
| Identity resolver | `identity/resolver.py` |
| Context / persona | `context/resolver.py` |
| Language selection | `services/language.py` |
| Conversation orchestrator | `conversation/orchestrator.py` |
| Menu seed / DB | `menu/seed_data.py`, `doctype/whatsapp_menu_item/` |
| Menu registry | `services/registry.py` |
| Interactive UX | `whatsapp/interactive.py` |
| Welcome / responses | `response/builder.py` |
| Profile gaps / completion | `services/profile_gaps.py`, `services/profile_completion.py` |
| Proactive nudges | `services/proactive.py` |
| Attendance / leave | `services/attendance_leave.py`, `services/attendance_location.py` |
| Payroll / documents | `services/payroll.py`, `services/tax_certificate.py`, `services/employee_letters.py` |
| Travel | `services/travel.py` |
| HR profile | `services/hr_profile.py` |
| Live HR chat | `services/hr_chat.py`, `services/hr_contact_prompt.py`, `services/office_hours.py` |
| Concerns (confidential) | `services/concern_report.py` |
| Support PIN | `security/pin_flow.py`, `security/support_pin.py` |
| Auth gateway | `auth/gateway.py` |

---

## 2. Files modified

| File | Change |
|------|--------|
| `response/builder.py` | MicroMerger Staff Support welcome; employee first name; “How can we help you today?” |
| `services/language.py` | Post-language employee-first message; keyword hints |
| `services/proactive.py` | Max one reminder; no profile %; “Review Next Item” / “Later” |
| `services/profile_completion.py` | “My Details & Documents” hub; no primary completeness % |
| `services/profile_gaps.py` | Employee-friendly labels; hide internal contract-not-generated |
| `services/hr_profile.py` | “Supervisor & HR Contact” + HR phone/email footer |
| `services/hr_contact_prompt.py` | “Chat with HR” copy; off-hours note on intro |
| `services/office_hours.py` | Employee-friendly offline message |
| `services/keyword_router.py` | Deterministic free-text → service (no LLM) |
| `menu/seed_data.py` | Employee-first menu restructure; unique alias keys |
| `context/resolver.py` | `documents`, `staff_support` in allowed services |
| `services/registry.py` | Pinned quick actions (Attendance, Payroll, Chat with HR) |
| `whatsapp/interactive.py` | All Staff Services; pinned quick buttons |
| `auth/gateway.py` | Gateway rules for new menu keys and aliases |
| `conversation/orchestrator.py` | Service aliases, new handlers, keyword routing, no AI fallback |
| `tests/test_profile_completion.py` | Updated for employee-first hub |

---

## 3. New files

| File | Purpose |
|------|---------|
| `services/staff_support.py` | Staff Support hub buttons (used for programmatic follow-ups) |
| `services/my_day.py` | Lightweight My Day snapshot |
| `services/documents_hub.py` | Contract status + Support PIN help |
| `services/keyword_router.py` | Deterministic keyword routing |
| `tests/test_menu_integrity.py` | Menu seed integrity validation |
| `tests/test_employee_first_ux.py` | Welcome, language, keyword, profile UX tests |
| `doc/EMPLOYEE_FIRST_UX_IMPLEMENTATION_NOTE.md` | Pre-implementation review note |

---

## 4. Menu changes

### Active employee top-level (sequence)

1. 🕒 Attendance & Leave  
2. 💰 Salary & Payroll  
3. 🚗 Travel & DSA  
4. 📄 Documents & Contract  
5. 👤 My HR & Profile  
6. 💙 Staff Support  
7. 📚 Policies & HR Help  
8. 📦 Deliverables (project deliverable staff only)  
9. 💬 Chat with HR (`user_category: All`)

### Quick reply buttons (pinned)

- Attendance & Leave  
- Salary & Payroll  
- Chat with HR  
- 📋 All Staff Services (list)

### Renames

| Before | After |
|--------|-------|
| All Services | All Staff Services |
| My HR | My HR & Profile |
| Update Profile | Update My Details |
| Fix Top Item | Review Next Item (proactive only) |
| Profile Completion Hub | My Details & Documents |
| Supervisor & Reporting… | Supervisor & HR Contact |

### New categories

- **Documents & Contract** — contract, payslip/tax/letter aliases  
- **Staff Support** — HR Guidance, Supervisor, Confidential, Chat with HR  
- **My Day** — under My HR & Profile  

### Alias keys (unique DB keys → shared handlers)

| Menu key | Resolves to |
|----------|-------------|
| `doc_salary_slip` | `pay_download_slip` |
| `doc_tax_cert` | `pay_tax_deduction` |
| `doc_experience_letter` | `pay_experience_letter` |
| `doc_bank_letter` | `pay_bank_letter` |
| `doc_my_requests` | `prof_my_requests` |
| `staff_hr_guidance` | `pol_view_policies` |
| `staff_supervisor` | `supervisor_reporting` |
| `staff_contact_hr` | `contact_hr` |

### Removed from welcome / primary UX

- Profile completeness percentage card after language selection  
- Automatic full profile-gap list on session start  
- Top-level standalone Concerns menu (now under Staff Support)

---

## 5. Message changes

- Welcome: *Assalam-o-Alaikum, {first_name}!* → **MicroMerger Staff Support**  
- After language: *How can we help you today?* + keyword hints  
- Chat with HR intro + off-hours guidance  
- Profile hub: supportive wording; no “non-compliant” / “missing” labels  
- Internal “contract not generated” hidden from employees  

---

## 6. Removed / hidden profile nudges

- No `% complete` on welcome or post-language menu  
- Proactive: max **one** reminder with cooldown; dismissible “Later”  
- Contract gap hidden unless employee signature action required  

---

## 7. Added / updated services

| Service | Handler |
|---------|---------|
| My Day | `services/my_day.py` |
| Support PIN Help | `documents_hub.build_pin_help` |
| Current Contract | `documents_hub.build_contract_status` |
| Staff Support submenu | Existing concerns + HR chat + policies |
| Keyword free-text | `keyword_router.match_keyword_service` |

---

## 8. Security impact

- **No change** to Support PIN policy: create/reset in HRMIS only; WhatsApp verifies only  
- Renamed/moved items retain seed `security_level` (PIN where required)  
- Document aliases route through same PIN-gated payroll handlers  
- Confidential concerns still use `concern_report` restricted flow  
- Public / former personas unchanged; no cross-persona leakage  

---

## 9. Tests added

- `tests/test_menu_integrity.py` — unique keys, parents, security, handler coverage  
- `tests/test_employee_first_ux.py` — welcome, language, keywords, profile hub  

---

## 10. Automated test results

```
test_menu_integrity .............. OK (6)
test_employee_first_ux ........... OK (10)
test_profile_completion .......... OK (3)
test_orchestrator_hr_chat ........ OK (4)
test_auth_gateway ................ OK (17)
test_dynamic_menu ................ OK (8)
test_language .................... OK (3)
test_profile_menu_flows .......... OK (12)
```

**Note:** Full `bench run-tests --app ai_workplace` may fail on unrelated site fixtures (Company / United States). Run targeted modules above for regression.

**Re-seed menus after deploy:**

```bash
bench --site erp.v15 execute ai_workplace.ai_workplace.doctype.whatsapp_menu_item.whatsapp_menu_item.setup_default_menu_items --kwargs '{"force": True}'
bench restart
```

---

## 11. Manual UAT checklist

| Flow | Steps | Status |
|------|-------|--------|
| **A** | Hi → Language → Main Menu → Attendance → Back → Payroll → Main Menu | ☐ Staging |
| **B** | My HR → Update My Details → PIN → My Details hub → item → My Requests | ☐ Staging |
| **C** | Staff Support → HR Guidance → Chat with HR → Desk reply → employee receives | ☐ Staging |
| **D** | Unknown/public number → guest menu only | ☐ Staging |
| **E** | Former employee → settlement/letter/tax/HR chat | ☐ Staging |

---

## 12. Known limitations

- **My Day** shows only data available from existing ERP queries (attendance snapshot, pending leave, travel, HR requests)  
- **My Requests** consolidates profile change requests; not a universal case engine  
- **Deliverables** remains visible only for deliverable-contract staff  
- **Attendance Check In/Out** requires location attendance settings + permissions (separate feature)  
- **AI / LLM** intentionally disabled for free-text in Phase 1  

---

## 13. Deferred items

- Full **My Day** with HR chat waiting indicator  
- Universal **My Requests** across all request types  
- Proactive reminders beyond bank/attendance (requires business rules)  
- AI policy Q&A (Phase 2)  
- Urdu/Roman Urdu copy polish pass for all new strings  

---

## 14. Recommended next step

1. Manual UAT on staging WhatsApp (flows A–E)  
2. Enable `proactive_notifications_enabled` selectively after HR review  
3. Phase 2: optional AI intent layer behind explicit “Ask HR Assistant” entry (not session default)
