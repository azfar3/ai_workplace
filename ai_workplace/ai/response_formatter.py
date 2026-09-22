from typing import Any, Dict, List

class ResponseFormatter:
    """
    Deterministic response formatter to avoid using the LLM for simple data formatting.
    """
    
    @staticmethod
    def format_leave_balance(data: Any) -> str:
        if not data:
            return "📅 I couldn't find an active leave allocation for your employee record for the current leave period.\n\nThis may mean your leave allocation has not yet been created.\n\nIf you believe this is incorrect, I can help you contact HR."
            
        items = []
        if isinstance(data, dict):
            items = data.get("leave_balances", [])
            if not items and "leave_type" in data:
                items = [data]
        elif isinstance(data, list):
            items = data

        if not items:
            return "📅 You currently have no active leave allocations recorded for this leave period."

        res = "📅 *Your Leave Balance Summary*\n\n"
        for item in items:
            if isinstance(item, dict):
                ltype = item.get("leave_type", "Leave")
                rem = item.get("remaining_leaves", item.get("remaining", "0"))
                alloc = item.get("total_allocated", item.get("allocated", "0"))
                taken = item.get("leaves_taken", item.get("taken", "0"))
                res += f"• *{ltype}*: {rem} days remaining (Allocated: {alloc}, Used: {taken})\n"
        return res.strip()

    @staticmethod
    def format_leave_analysis(data: Any) -> str:
        if not data or not isinstance(data, dict):
            return "📊 I couldn't compute a leave analysis for your profile right now."

        balances = data.get("balances", [])
        history = data.get("history", [])
        total_allocated = data.get("total_allocated", 0)
        total_used = data.get("total_used", 0)
        total_remaining = data.get("total_remaining", 0)
        util_rate = data.get("utilization_rate", "0%")

        res = "📊 *Your Leave Analysis & Insights*\n\n"
        res += f"• *Overall Leave Utilization*: {util_rate} ({total_used} used of {total_allocated} allocated days)\n"
        res += f"• *Total Days Available*: {total_remaining} days remaining\n\n"

        if balances:
            res += "*Category Breakdown*:\n"
            for b in balances:
                if isinstance(b, dict):
                    ltype = b.get("leave_type", "Leave")
                    rem = b.get("remaining_leaves", 0)
                    alloc = b.get("total_allocated", 0)
                    used = b.get("leaves_taken", 0)
                    res += f"  • {ltype}: *{rem} days left* (Allocated: {alloc}, Used: {used})\n"

        if history:
            res += f"\n*Recent Leave Requests*:\n"
            for h in history[:3]:
                if isinstance(h, dict):
                    status_icon = "✅" if h.get("status") == "Approved" else ("⏳" if h.get("status") in ("Open", "Draft", "Applied") else "❌")
                    res += f"  • {status_icon} {h.get('leave_type', 'Leave')}: {h.get('total_leave_days', 1)} day(s) from {h.get('from_date')} ({h.get('status')})\n"

        res += "\n💡 *Insight*: You have leave balance available. Make sure to plan your leaves in advance!"
        return res.strip()
        
    @staticmethod
    def format_attendance_summary(data: dict) -> str:
        if not data or not isinstance(data, dict):
            return "🕒 I couldn't find any attendance records for today."
            
        res = "🕒 *Attendance Summary*\n\n"
        status = data.get("status_today", data.get("status"))
        if status and status != "error":
            res += f"Today's Status: *{status}*\n"
            
        in_time = data.get("in_time")
        out_time = data.get("out_time")
        in_str = in_time if (in_time and in_time != "N/A") else "Not checked in"
        out_str = out_time if (out_time and out_time != "N/A") else "Not checked out"
        res += f"Today's Check-in: {in_str}\n"
        res += f"Today's Check-out: {out_str}\n"
        
        hours = data.get("working_hours")
        if hours and str(hours) != "0.00":
            res += f"Working Hours: {hours} hrs\n"
            
        return res.strip()
        
    @staticmethod
    def format_profile_gaps(data: dict) -> str:
        if not data or not isinstance(data, dict):
            return "👤 Your profile completeness could not be determined."
            
        score = data.get("completeness_score", data.get("score", 100))
        res = f"👤 *Profile Completeness: {score}%*\n\n"
        
        gaps = data.get("missing_fields", data.get("all_gaps", data.get("critical_gaps", [])))
        if gaps:
            res += "The following profile updates are recommended:\n"
            for gap in gaps:
                label = gap.get("label", str(gap)) if isinstance(gap, dict) else str(gap)
                res += f"• {label}\n"
        else:
            res += "Your profile is 100% complete! 🎉"
            
        return res.strip()

    @staticmethod
    def format_knowledge_matches(data: Any) -> str:
        """Format search_knowledge tool results into readable text."""
        matches = []
        if isinstance(data, dict):
            matches = data.get("knowledge_matches", [])
        elif isinstance(data, list):
            matches = data

        if not matches:
            return (
                "I'm sorry, but I don't have a specific policy or information on that topic "
                "in our knowledge base.\n\n"
                "For the most accurate and up-to-date guidance, please reach out to HR directly — "
                "you can use the *Chat with HR* option or contact your HR representative."
            )

        # Build a clean readable answer from the knowledge excerpts
        parts = []
        seen_titles = set()
        INTERNAL_SOURCES = {"menu catalog", "menu_catalog", "service catalog", "service_catalog"}
        for match in matches:
            if not isinstance(match, dict):
                continue
            title = (match.get("source_title") or "").strip()
            text = (match.get("text") or "").strip()
            if not text:
                continue
            # Skip internal system catalog chunks — they contain service keys, not readable policies
            if title.lower() in INTERNAL_SOURCES:
                continue
            # Skip chunks that look like raw key:value system data (e.g. "svc_key: Label\n...")
            if text.count(":") > 3 and "\n" in text and any(c in text for c in ("svc_", "nformer_", "ncontact_", "npay_")):
                continue
            if title and title not in seen_titles:
                seen_titles.add(title)
                parts.append(f"📌 *{title}*\n{text}")
            else:
                parts.append(text)

        if not parts:
            return (
                "I'm sorry, but I don't have a specific policy on that topic in our knowledge base.\n\n"
                "For the most accurate and up-to-date guidance, please reach out to HR directly — "
                "you can use the *Chat with HR* option or contact your HR representative."
            )

        return "\n\n".join(parts)

    @staticmethod
    def format_policy_list(data: Any) -> str:
        if not data:
            return "📚 I'm not seeing any published policies in our system. If you were looking for a specific policy, feel free to let me know."
        
        if isinstance(data, str):
            return data

        if not isinstance(data, list):
            return str(data)

        res = "📚 *Published Policies*\n\n"
        for policy in data:
            if isinstance(policy, dict):
                title = policy.get("title") or policy.get("policy_name") or policy.get("name") or "Unnamed Policy"
                ver = policy.get("version", "1.0")
                category = policy.get("category", "Policy")
                res += f"• *{title}* ({category}, v{ver})\n"
            elif isinstance(policy, str):
                res += f"• *{policy}*\n"
        return res.strip()

    @staticmethod
    def format_policy_count(data: List[dict]) -> str:
        if not data:
            return "📚 I'm not seeing any published policies in our system."
            
        return f"📚 There are currently *{len(data)} published policies* available in the system."

    @staticmethod
    def format_branch(data: dict) -> str:
        if not data or not isinstance(data, dict) or not data.get("branch"):
            return "🏢 Your branch information is not set in your HR profile."
        return f"🏢 You are assigned to the *{data.get('branch')}* branch."

    @staticmethod
    def format_office_timings(data: dict) -> str:
        if not data or not isinstance(data, dict):
            return "🏢 *Office Timings*\n\nMonday to Friday: 9:00 AM - 5:00 PM\nWeekly Off: Saturday & Sunday"
        
        days = data.get("office_days", "Monday to Friday")
        timings = data.get("timings", "9:00 AM - 5:00 PM")
        weekly_off = data.get("weekly_off", "Saturday & Sunday")
        
        res = f"🏢 *Office Schedule & Timings*\n\n"
        res += f"• Working Days: {days}\n"
        res += f"• Working Hours: {timings}\n"
        res += f"• Weekly Off: {weekly_off}\n"
        
        holidays = data.get("upcoming_holidays", [])
        if holidays:
            res += f"\n🎉 *Upcoming Holidays ({data.get('holiday_list', 'Calendar')})*:\n"
            for h in holidays[:5]:
                res += f"  • {h.get('date')}: {h.get('description')}\n"
                
        return res.strip()

    @staticmethod
    def format_generic_error(reason: str = "I couldn't find an official answer to that question in the available HR information.") -> str:
        return f"⚠️ {reason}\n\nWould you like me to connect you with HR?"
        
    @staticmethod
    def format_salary_slip(data: dict) -> str:
        if not data:
            return "💵 I couldn't find your latest salary slip. Please contact HR if you believe this is an error."
        curr = data.get("currency") or "PKR"
        net_pay = data.get("net_pay")
        if net_pay and not any(c in str(net_pay) for c in ["PKR", "Rs"]):
            net_pay = f"{curr} {net_pay}"
        return f"💵 *Latest Salary Slip*\n\nSlip Name: {data.get('salary_slip_name')}\nPeriod: {data.get('start_date')} to {data.get('end_date')}\nNet Pay: {net_pay}"

    @staticmethod
    def format_tax_details(data: dict) -> str:
        if not data:
            return "🧾 I couldn't find your latest tax deduction details."
        curr = data.get("currency") or "PKR"
        tot_ded = data.get("total_deductions")
        if tot_ded and not any(c in str(tot_ded) for c in ["PKR", "Rs"]):
            tot_ded = f"{curr} {tot_ded}"
        return f"🧾 *Latest Tax Deductions*\n\nSlip Name: {data.get('salary_slip_name')}\nPeriod: {data.get('start_date')} to {data.get('end_date')}\nTotal Deductions: {tot_ded}"

    @staticmethod
    def format_leave_history(data: Any) -> str:
        if not data:
            return "📜 I couldn't find any recent leave requests in your records."

        items = []
        if isinstance(data, dict):
            items = data.get("leave_history", data.get("value", data.get("data", [])))
            if isinstance(items, str):
                import json, ast
                try:
                    items = json.loads(items)
                except Exception:
                    try:
                        items = ast.literal_eval(items)
                    except Exception:
                        items = []
        elif isinstance(data, list):
            items = data

        if not items or not isinstance(items, list):
            return "📜 I couldn't find any recent leave requests in your records."

        res = "📜 *Recent Leave Requests*\n\n"
        for item in items[:5]:
            if isinstance(item, dict):
                status_icon = "✅" if item.get("status") == "Approved" else ("⏳" if item.get("status") in ("Open", "Draft", "Applied") else "❌")
                days_val = item.get("total_days", item.get("total_leave_days", 0))
                res += f"{status_icon} *{item.get('leave_type', 'Leave')}* ({days_val} days)\n"
                res += f"   Period: {item.get('from_date')} to {item.get('to_date')}\n"
                res += f"   Status: {item.get('status')}\n\n"
        return res.strip()

    @staticmethod
    def format_designation(data: dict) -> str:
        if not data or not isinstance(data, dict) or not data.get("designation"):
            return "👤 I couldn't find designation information for your profile."
        return f"👔 Your official designation is *{data.get('designation')}*."

    @staticmethod
    def format_department(data: dict) -> str:
        if not data or not isinstance(data, dict) or not data.get("department"):
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
    def format_response(intent: str, raw_data: Any) -> str:
        data = raw_data
        if isinstance(data, dict) and "data" in data and "tool" in data:
            data = data["data"]

        if intent == "leave_balance":
            return ResponseFormatter.format_leave_balance(data)
        elif intent == "analyze_leaves":
            return ResponseFormatter.format_leave_analysis(data)
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
        elif intent == "my_branch":
            return ResponseFormatter.format_branch(data)
        elif intent == "monthly_attendance":
            return ResponseFormatter.format_monthly_attendance(data)
        elif intent == "get_menu_help":
            return "📋 *MicroMerger Staff Services*\n\nPlease select an option from the menu below or tap *View Services*."
        elif intent in ("guest_job_status", "guest_careers"):
            if isinstance(data, dict) and "careers_guide_response" in data:
                return data["careers_guide_response"]
            return str(data)
        else:
            # Generic fallback: handle knowledge_matches dict gracefully
            if isinstance(data, dict) and "knowledge_matches" in data:
                return ResponseFormatter.format_knowledge_matches(data)
            if isinstance(data, list):
                # Could be raw search_knowledge list result
                if data and isinstance(data[0], dict) and ("text" in data[0] or "source_title" in data[0]):
                    return ResponseFormatter.format_knowledge_matches(data)
            # Last resort: stringify, but only if it's a reasonable string
            if isinstance(data, str):
                return data
            if not data:
                return "I could not retrieve that information right now. Please contact HR for assistance."
            return "I could not retrieve that information right now. Please contact HR for assistance."

    @staticmethod
    def sanitize_whatsapp_text(text: str) -> str:
        """
        Sanitize and format text responses for WhatsApp compliance:
        1. Converts double asterisks **bold** to single asterisks *bold*.
        2. Strips Markdown tables (| col | col |) and converts rows into clean bullet points.
        3. Converts HTML breaks <br> to proper newlines without breaking tables.
        4. Strips residual HTML tags.
        """
        import re
        if not text or not isinstance(text, str):
            return text or ""

        # 1. Convert double asterisks **text** to single asterisks *text* (WhatsApp style)
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

        # 2. Strip residual HTML tags except <br>
        text = re.sub(r'<(?!\/?br\b)[^>]+>', '', text, flags=re.IGNORECASE)

        # 3. Clean Markdown table lines line-by-line
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip separator rows like |-------|---------|
            if re.match(r'^\|?[\s:\-]+\|[\s:\-\|]*$', stripped):
                continue

            # Process table row lines starting and ending with |
            if stripped.startswith('|') and stripped.endswith('|'):
                # Replace <br> inside this table row line with newline
                row_content = re.sub(r'<br\s*/?>', '\n', stripped, flags=re.IGNORECASE)
                # Split cells by |
                cells = [c.strip() for c in row_content.strip('|').split('|') if c.strip()]
                
                # Skip header rows containing common headers
                cell_str = " ".join(cells).lower()
                if "method" in cell_str and ("contact" in cell_str or "how to" in cell_str):
                    continue
                    
                for cell in cells:
                    cell_lines = [l.strip() for l in cell.split('\n') if l.strip()]
                    for cl in cell_lines:
                        if cl.startswith("•") or cl.startswith("-") or cl.startswith("*"):
                            cleaned_lines.append(f"  {cl}")
                        else:
                            cleaned_lines.append(f"• {cl}")
            else:
                # Replace <br> in normal non-table lines
                line = re.sub(r'<br\s*/?>', '\n', line, flags=re.IGNORECASE)
                cleaned_lines.append(line)

        result = "\n".join(cleaned_lines)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()


