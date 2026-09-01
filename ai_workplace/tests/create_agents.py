import frappe

def create_all_agents():
    # Force reload schema first
    frappe.reload_doctype("AI Workplace Agent", force=True)

    agents = [
        {
            "agent_slug": "hr-agent",
            "agent_name": "HR Concierge Agent",
            "agent_type": "HR Agent",
            "is_active": 1,
            "description": "Primary employee assistant for leave balance, attendance history, profile updates, and general HR policies.",
            "system_prompt": """You are the official HR Concierge Assistant for MicroMerger.
Your objective is to answer employee queries regarding leave balance, attendance logs, profile details, and company HR policies.
Always be polite, concise, professional, and clear.
Never disclose sensitive personal information (CNIC, IBAN, Passwords)."""
        },
        {
            "agent_slug": "it-support-agent",
            "agent_name": "IT Helpdesk & Assets Agent",
            "agent_type": "IT Support Agent",
            "is_active": 1,
            "description": "Automated technical support for Wi-Fi, VPN, software licenses, hardware requests, and IT ticket status.",
            "system_prompt": """You are the official IT Helpdesk Assistant for MicroMerger.
Your objective is to help employees troubleshoot technical issues, guide them on VPN/email setup, software licenses, and IT ticketing procedures.
Provide clear step-by-step instructions for IT SOPs."""
        },
        {
            "agent_slug": "payroll-expense-agent",
            "agent_name": "Payroll & Expense Agent",
            "agent_type": "Payroll & Expense Agent",
            "is_active": 1,
            "description": "Specialized assistant for salary slip explanations, tax deduction queries, and reimbursement claim status.",
            "system_prompt": """You are the official Payroll & Expense Assistant for MicroMerger.
Your objective is to explain salary slip breakdowns, tax rules, fuel/travel reimbursement guidelines, and claim status.
Maintain maximum confidentiality and guidance accuracy."""
        },
        {
            "agent_slug": "manager-assistant-agent",
            "agent_name": "Manager Executive Assistant Agent",
            "agent_type": "Manager Assistant Agent",
            "is_active": 1,
            "description": "Dedicated assistant for Department Managers to view team attendance, pending leave approvals, and appraisals.",
            "system_prompt": """You are the Executive Assistant Agent for Department Managers at MicroMerger.
Your objective is to help managers manage team leave approvals, daily shift attendance summaries, and team performance reminders efficiently."""
        },
        {
            "agent_slug": "onboarding-agent",
            "agent_name": "Onboarding & Candidate Agent",
            "agent_type": "Onboarding Agent",
            "is_active": 1,
            "description": "Dedicated guide for day 1-30 new hires, onboarding checklists, and job opening inquiries.",
            "system_prompt": """You are the Onboarding & New Hire Guide for MicroMerger.
Your objective is to assist new employees through their first 30 days, completing onboarding checklists, submitting documents, and understanding company culture."""
        }
    ]

    for item in agents:
        slug = item["agent_slug"]
        if not frappe.db.exists("AI Workplace Agent", slug):
            doc = frappe.new_doc("AI Workplace Agent")
            doc.update(item)
            doc.insert(ignore_permissions=True)
            print(f"Created Agent: {doc.agent_name} ({slug})")
        else:
            doc = frappe.get_doc("AI Workplace Agent", slug)
            doc.update(item)
            doc.save(ignore_permissions=True)
            print(f"Updated Agent: {doc.agent_name} ({slug})")

    frappe.db.commit()
    print("All 5 agents successfully created and updated in Desk database!")
