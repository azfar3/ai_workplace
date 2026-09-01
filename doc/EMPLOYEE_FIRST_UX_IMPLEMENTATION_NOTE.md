# Employee-First WhatsApp UX — Implementation Note

| Existing Feature | Existing File | Reuse/Modify | Required Change |
|---|---|---|---|
| Welcome header | `response/builder.py` | Modify | Staff Support branding, employee-first copy |
| Language saved message | `services/language.py` | Modify | "How can we help you today?" post-language |
| Menu seed | `menu/seed_data.py` | Modify | Reorder, rename, add documents/staff_support/my_day |
| Quick actions | `whatsapp/interactive.py` | Modify | Pin Attendance, Payroll, Chat with HR + All Staff Services |
| Service registry | `services/registry.py` | Modify | Quick-action key priority |
| Allowed services | `context/resolver.py` | Modify | Add `documents`, `staff_support` |
| Proactive nudge | `services/proactive.py` | Modify | Single reminder, no profile % list, cooldown |
| Profile hub | `services/profile_completion.py` | Modify | My Details & Documents, hide primary % |
| Profile gaps | `services/profile_gaps.py` | Modify | Employee labels, hide internal contract gap |
| Staff Support hub | NEW `services/staff_support.py` | Add | Route to concerns/HR chat/policies |
| Documents hub | NEW `services/documents_hub.py` | Add | Group document services |
| My Day | NEW `services/my_day.py` | Add | Lightweight deterministic snapshot |
| Keyword router | NEW `services/keyword_router.py` | Add | Deterministic free-text aliases (no LLM) |
| Orchestrator | `conversation/orchestrator.py` | Modify | New routes, remove LLM free-text default |
| HR contact copy | `services/hr_contact_prompt.py` | Modify | Chat with HR, offline hours message |
| HR profile | `services/hr_profile.py` | Modify | Supervisor & HR Contact titles |
| Policies AI item | `menu/seed_data.py` + orchestrator | Modify | Route to policy list not AI agent |
| Menu integrity test | NEW `tests/test_menu_integrity.py` | Add | Handler/registry validation |
| UX tests | NEW `tests/test_employee_first_ux.py` | Add | Welcome, proactive, profile hub wording |
