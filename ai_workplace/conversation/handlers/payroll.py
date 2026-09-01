from typing import Dict, Any, Optional
from ai_workplace.conversation.handlers.base import ServiceHandler
from ai_workplace.whatsapp.outbound import OutboundMessage
from ai_workplace.conversation.manager import update_conversation, ConversationState
from ai_workplace.conversation.orchestrator import log_ai_action
from ai_workplace.services.response_helpers import wrap_with_menu_again, wrap_salary_slip_period_options

class PayrollHandler:
    def can_handle(self, intent: str, state: str) -> bool:
        clean = intent.replace("svc_", "")
        return (
            clean.startswith("pay_")
            or intent.startswith("svc_pay_")
            or clean in ("former_payslip", "pay_slip", "pay_previous_slips", "pay_slip_1m", "pay_slip_3m", "pay_slip_6m")
        )

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        text_lower = (clean_text or "").strip().lower()
        
        # 1) Specific period selection (1, 3, or 6 months)
        if clean_intent in ("pay_slip_1m", "pay_slip_3m", "pay_slip_6m") or (
            getattr(conv, "active_service", None) == "pay_download_slip" and text_lower in ("1", "3", "6", "1m", "3m", "6m", "1 month", "3 months", "6 months")
        ):
            from ai_workplace.services.payroll import build_salary_slip_download_outbound
            months = 1
            if clean_intent == "pay_slip_3m" or text_lower in ("3", "3m", "3 months"):
                months = 3
            elif clean_intent == "pay_slip_6m" or text_lower in ("6", "6m", "6 months"):
                months = 6

            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_salary_slip_download_outbound(context, months=months)
            action = f"download_payslip_{months}m"

        # 2) Payslip intro / period options picker
        elif clean_intent in ("pay_download_slip", "former_payslip", "pay_slip", "pay_previous_slips"):
            from ai_workplace.services.payroll import build_salary_slip_download_intro
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service="pay_download_slip")
            resp_text = build_salary_slip_download_intro(context)
            outbound = wrap_salary_slip_period_options(resp_text, context)
            action = "download_payslip_intro"
            
        elif clean_intent in ("pay_tax_deduction", "tax_certificate"):
            from ai_workplace.services.tax_certificate import build_tax_certificate_download_outbound
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_tax_certificate_download_outbound(context)
            action = "view_tax_deduction"
            
        elif clean_intent in ("pay_bank_letter", "bank_letter"):
            from ai_workplace.services.employee_letters import generate_bank_letter_pdf, build_letter_download_outbound, build_letter_download_error, resolve_bank_name
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            bank_name = resolve_bank_name(context) or "Faysal Bank"
            try:
                pdf_bytes, filename = generate_bank_letter_pdf(context.get("employee", ""), bank_name)
                caption = f"📄 Bank Letter for {bank_name}"
                outbound = build_letter_download_outbound(context, pdf_bytes, filename, caption)
            except Exception:
                err = build_letter_download_error(context, "Bank Letter")
                outbound = wrap_with_menu_again(err, context)
            action = "download_bank_letter"

        if outbound:
            log_ai_action(
                trace_id=trace_id,
                conversation_name=conv.name,
                whatsapp_identity=conv.whatsapp_identity,
                erp_user=conv.erp_user or "",
                employee=conv.employee or "",
                intent=intent,
                service="payroll",
                action=action,
                result=outbound.log_text(),
                status="Success",
            )
            return outbound
            
        return None
