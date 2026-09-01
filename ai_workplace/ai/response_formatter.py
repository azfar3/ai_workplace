from typing import Any, Dict, List

class ResponseFormatter:
    """
    Deterministic response formatter to avoid using the LLM for simple data formatting.
    """
    
    @staticmethod
    def format_leave_balance(data: dict) -> str:
        if not data:
            return "📅 I couldn't find an active leave allocation for your employee record for the current leave period.\n\nThis may mean your leave allocation has not yet been created.\n\nIf you believe this is incorrect, I can help you contact HR."
            
        res = "📅 *Your Leave Balance*\n\n"
        for leave_type, val in data.items():
            res += f"• {leave_type}: {val} days\n"
        return res.strip()
        
    @staticmethod
    def format_attendance_summary(data: dict) -> str:
        if not data:
            return "🕒 I couldn't find any attendance records for today."
            
        res = "🕒 *Attendance Summary*\n\n"
        if "today" in data:
            res += f"Today's Check-in: {data['today'].get('in_time', 'N/A')}\n"
            res += f"Today's Check-out: {data['today'].get('out_time', 'N/A')}\n\n"
            
        if "month" in data:
            res += f"Present this month: {data['month'].get('present', 0)}\n"
            res += f"Absent this month: {data['month'].get('absent', 0)}\n"
            
        return res.strip()
        
    @staticmethod
    def format_profile_gaps(data: dict) -> str:
        if not data:
            return "👤 Your profile completeness could not be determined."
            
        res = f"👤 *Profile Completeness: {data.get('score', 0)}%*\n\n"
        
        gaps = data.get("missing_fields", [])
        if gaps:
            res += "The following fields are missing:\n"
            for gap in gaps:
                res += f"• {gap}\n"
        else:
            res += "Your profile is 100% complete!"
            
        return res.strip()

    @staticmethod
    def format_policy_list(data: List[dict]) -> str:
        if not data:
            return "📚 I'm not seeing any published policies in our system. If you were looking for a specific policy, feel free to let me know."
            
        res = "📚 *Published Policies*\n\n"
        for policy in data:
            res += f"• {policy.get('policy_name', 'Unnamed Policy')} (v{policy.get('version', '1.0')})\n"
        return res.strip()

    @staticmethod
    def format_policy_count(data: List[dict]) -> str:
        if not data:
            return "📚 I'm not seeing any published policies in our system."
            
        return f"📚 There are currently *{len(data)} published policies* available in the system."

    @staticmethod
    def format_office_timings(data: dict) -> str:
        # Default placeholder since office timings might not be explicitly queried yet
        return "🏢 *Office Timings*\n\nMonday to Friday: 9:00 AM - 5:00 PM\nSaturday & Sunday: Closed\n\nFor most accurate office hours, please check MicroMerger's employee handbook or reach out to the HR team directly."

    @staticmethod
    def format_generic_error(reason: str = "I couldn't find an official answer to that question in the available HR information.") -> str:
        return f"⚠️ {reason}\n\nWould you like me to connect you with HR?"
        
    @staticmethod
    def format_salary_slip(data: dict) -> str:
        if not data:
            return "💵 I couldn't find your latest salary slip. Please contact HR if you believe this is an error."
        return f"💵 *Latest Salary Slip*\n\nSlip Name: {data.get('salary_slip_name')}\nPeriod: {data.get('start_date')} to {data.get('end_date')}\nNet Pay: {data.get('net_pay')}"

    @staticmethod
    def format_tax_details(data: dict) -> str:
        if not data:
            return "🧾 I couldn't find your latest tax deduction details."
        return f"🧾 *Latest Tax Deductions*\n\nSlip Name: {data.get('salary_slip_name')}\nPeriod: {data.get('start_date')} to {data.get('end_date')}\nTotal Deductions: {data.get('total_deductions')}"

    @staticmethod
    def format_response(intent: str, data: Any) -> str:
        if intent == "leave_balance":
            return ResponseFormatter.format_leave_balance(data)
        elif intent == "today_attendance":
            return ResponseFormatter.format_attendance_summary(data)
        elif intent == "profile_gaps":
            return ResponseFormatter.format_profile_gaps(data)
        elif intent == "policy_list":
            return ResponseFormatter.format_policy_list(data)
        elif intent == "policy_count":
            return ResponseFormatter.format_policy_count(data)
        elif intent == "office_timings":
            return ResponseFormatter.format_office_timings(data)
        elif intent == "latest_salary_slip":
            return ResponseFormatter.format_salary_slip(data)
        elif intent == "tax_deductions":
            return ResponseFormatter.format_tax_details(data)
        else:
            return str(data)
