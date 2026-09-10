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
            or clean in ("former_payslip", "pay_slip", "pay_previous_slips", "pay_slip_latest", "pay_slip_3m", "pay_slip_6m")
            or clean in ("tax_cert_current", "tax_cert_previous", "tax_cert_latest")
        )

    def handle(self, conv: Any, intent: str, clean_text: str, context: Dict[str, Any], trace_id: str) -> Optional[OutboundMessage]:
        outbound = None
        action = intent
        clean_intent = intent.replace("svc_", "")
        text_lower = (clean_text or "").strip().lower()
        
        # 1) Specific period selection (1, 3, or 6 months)
        if clean_intent in ("pay_slip_latest", "pay_slip_3m", "pay_slip_6m") or (
            getattr(conv, "active_service", None) == "pay_download_slip" and text_lower in ("0", "1", "3", "6", "3m", "6m", "3 months", "6 months", "latest", "last", "last 3", "last 6")
        ):
            from ai_workplace.services.payroll import build_salary_slip_download_outbound
            limit = 1
            if clean_intent == "pay_slip_latest" or text_lower in ("latest", "0", "last", "1"):
                limit = 1
            elif clean_intent == "pay_slip_3m" or text_lower in ("3", "3m", "3 months", "last 3"):
                limit = 3
            elif clean_intent == "pay_slip_6m" or text_lower in ("6", "6m", "6 months", "last 6"):
                limit = 6

            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_salary_slip_download_outbound(context, months=limit)
            action = f"download_payslip_{limit}m"

        # 2) Payslip intro / period options picker
        elif clean_intent in ("pay_download_slip", "former_payslip", "pay_slip", "pay_previous_slips"):
            from ai_workplace.services.payroll import build_salary_slip_download_intro
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service="pay_download_slip")
            resp_text = build_salary_slip_download_intro(context)
            outbound = wrap_salary_slip_period_options(resp_text, context)
            action = "download_payslip_intro"
            
        # 1.5) Tax Certificate options picker
        elif clean_intent in ("pay_tax_deduction", "tax_certificate"):
            from ai_workplace.services.tax_certificate import build_tax_certificate_intro
            from ai_workplace.services.response_helpers import wrap_tax_certificate_period_options
            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service="pay_tax_deduction")
            resp_text = build_tax_certificate_intro(context)
            outbound = wrap_tax_certificate_period_options(resp_text, context)
            action = "tax_certificate_intro"

        # 1.6) Specific Tax Certificate period selection
        elif clean_intent in ("tax_cert_current", "tax_cert_previous", "tax_cert_latest") or (
            getattr(conv, "active_service", None) == "pay_tax_deduction" and text_lower in ("current", "previous", "latest", "current year", "previous year", "last generated")
        ):
            from ai_workplace.services.tax_certificate import build_tax_certificate_download_outbound
            period = "current"
            if clean_intent == "tax_cert_previous" or text_lower in ("previous", "previous year"):
                period = "previous"
            elif clean_intent == "tax_cert_latest" or text_lower in ("latest", "last generated"):
                period = "latest"

            update_conversation(conv, state=ConversationState.AWAITING_SELECTION, current_intent=intent, active_service=None)
            outbound = build_tax_certificate_download_outbound(context, period=period)
            action = f"download_tax_cert_{period}"
            
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
                from ai_workplace.services.response_helpers import wrap_with_parent_menu
                outbound = wrap_with_parent_menu(err, context, "payroll")
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
