import frappe

def test_evidence_sanitization():
    from ai_workplace.ai.tools import get_leave_balance
    from ai_workplace.ai.evidence import sanitize_tool_evidence
    from ai_workplace.services.hr_agent import _run_tools

    emp = "EMP-MM-00796"
    ctx = {"employee": emp}
    
    raw = get_leave_balance(emp)
    print("Raw get_leave_balance:", raw)

    sanitized = sanitize_tool_evidence("get_leave_balance", raw, ctx)
    print("Sanitized evidence:", sanitized)

    tool_context = _run_tools(["get_leave_balance"], ctx, "How many leaves do I have left?")
    print("\n_run_tools output:")
    print(tool_context)
