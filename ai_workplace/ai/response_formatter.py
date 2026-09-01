from typing import Any, Dict, List

class ResponseFormatter:
    """
    Deterministic response formatter to avoid using the LLM for simple data formatting.
    """
    
    @staticmethod
    def format_leave_balance(data: Any) -> str:
        if not data:
            return "📅 I couldn't find an active leave allocation for your employee record for the current leave period.\n\nThis may mean your leave allocation has not yet been created.\n\nIf you believe this is incorrect, I can help you contact HR."
            
        res = "📅 *Your Leave Balance Summary*\n\n"
        if isinstance(data, list):
            for item in data:
                ltype = item.get("leave_type", "Leave")
                rem = item.get("remaining", "0")
                alloc = item.get("allocated", "0")
                taken = item.get("taken", "0")
                res += f"• *{ltype}*: {rem} days remaining (Allocated: {alloc}, Used: {taken})\n"
        elif isinstance(data, dict):
            for leave_type, val in data.items():
                if isinstance(val, dict):
                    rem = val.get("remaining", val.get("unused_leaves", 0))
                    res += f"• *{leave_type}*: {rem} days remaining\n"
                else:
                    res += f"• *{leave_type}*: {val} days\n"
        return res.strip()
        
    @staticmethod
    def format_attendance_summary(data: dict) -> str:
        if not data:
            return "🕒 I couldn't find any attendance records for today."
            
        res = "🕒 *Attendance Summary*\n\n"
        if isinstance(data, dict):
            if "status" in data:
                res += f"Today's Status: {data.get('status')}\n"
            if "in_time" in data:
                res += f"Today's Check-in: {data.get('in_time')}\n"
            if "out_time" in data:
                res += f"Today's Check-out: {data.get('out_time')}\n"
            if "working_hours" in data and data.get("working_hours") != "0.00":
                res += f"Working Hours: {data.get('working_hours')} hrs\n"
                
            if "month" in data and isinstance(data["month"], dict):
                res += f"\nPresent this month: {data['month'].get('present', 0)}\n"
                res += f"Absent this month: {data['month'].get('absent', 0)}\n"
            
        return res.strip()
        
    @staticmethod
    def format_profile_gaps(data: dict) -> str:
        if not data:
            return "👤 Your profile completeness could not be determined."
            
        score = data.get("completeness_score", data.get("score", 100))
        res = f"👤 *Profile Completeness: {score}%*\n\n"
        
        gaps = data.get("all_gaps", data.get("critical_gaps", data.get("missing_fields", [])))
        if gaps:
            res += "The following profile updates are recommended:\n"
            for gap in gaps:
                label = gap.get("label", str(gap)) if isinstance(gap, dict) else str(gap)
                res += f"• {label}\n"
        else:
            res += "Your profile is 100% complete! 🎉"
            
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
    def format_leave_history(data: list) -> str:
        if not data:
            return "📜 I couldn't find any recent leave requests in your records."
        res = "📜 *Recent Leave Requests*\n\n"
        for item in data[:5]:
            status_icon = "✅" if item.get("status") == "Approved" else ("⏳" if item.get("status") in ("Open", "Draft", "Applied") else "❌")
            res += f"{status_icon} *{item.get('leave_type', 'Leave')}* ({item.get('total_leave_days', 0)} days)\n"
            res += f"   Period: {item.get('from_date')} to {item.get('to_date')}\n"
            res += f"   Status: {item.get('status')}\n\n"
        return res.strip()

    @staticmethod
    def format_designation(data: dict) -> str:
        if not data or not data.get("designation"):
            return "👤 I couldn't find designation information for your profile."
        return f"👔 Your official designation is *{data.get('designation')}*."

    @staticmethod
    def format_department(data: dict) -> str:
        if not data or not data.get("department"):
            return "🏢 I couldn't find department information for your profile."
        return f"🏢 You belong to the *{data.get('department')}* department."

    @staticmethod
    def format_monthly_attendance(data: dict) -> str:
        if not data:
            return "📅 I couldn't find attendance records for the requested period."
        res = "📅 *Monthly Attendance Summary*\n\n"
        if isinstance(data, dict):
            if "present" in data:
                res += f"• Present: {data.get('present', 0)} days\n"
            if "absent" in data:
                res += f"• Absent: {data.get('absent', 0)} days\n"
            if "leave" in data:
                res += f"• On Leave: {data.get('leave', 0)} days\n"
            if "late" in data:
                res += f"• Late Check-ins: {data.get('late', 0)} days\n"
            if "total_working_days" in data:
                res += f"• Total Working Days: {data.get('total_working_days')}\n"
        return res.strip()

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
        elif intent == "leave_history":
            return ResponseFormatter.format_leave_history(data)
        elif intent == "my_designation":
            return ResponseFormatter.format_designation(data)
        elif intent == "my_department":
            return ResponseFormatter.format_department(data)
        elif intent == "monthly_attendance":
            return ResponseFormatter.format_monthly_attendance(data)
        elif intent == "get_menu_help":
            return "📋 *MicroMerger Staff Services*\n\nPlease select an option from the menu below or tap *View Services*."
        else:
            return str(data)

