"""
ai_workplace/tests/test_payroll.py
────────────────────────────────────
Unit tests for salary slip download service.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from ai_workplace.services.payroll import (
    build_salary_slip_download_intro,
    build_salary_slip_not_found,
    build_salary_slip_download_outbound,
    build_slip_document_caption,
    generate_salary_slip_pdf,
    get_salary_slips_for_months,
)
from ai_workplace.services.response_helpers import wrap_salary_slip_period_options
from ai_workplace.whatsapp.interactive import build_salary_slip_period_options_message


class TestPayrollServices(unittest.TestCase):
    def setUp(self):
        self.context_en = {
            "employee": "EMP-001",
            "full_name": "Ali Ahmed",
            "preferred_language": "English",
        }

    def test_build_salary_slip_download_intro(self):
        res = build_salary_slip_download_intro(self.context_en)
        self.assertIn("Previous Salary Slips", res)

    def test_build_former_payslip_intro(self):
        from ai_workplace.services.payroll import build_former_payslip_intro

        res = build_former_payslip_intro(self.context_en)
        self.assertIn("Payslip", res)

    @patch("ai_workplace.services.payroll.frappe")
    def test_get_salary_slips_for_months(self, mock_frappe):
        mock_frappe.db.get_all.return_value = [{"name": "SLIP-1", "start_date": "2026-07-01"}]
        slips = get_salary_slips_for_months("EMP-001", 3)
        self.assertEqual(len(slips), 1)
        mock_frappe.db.get_all.assert_called_once()

    @patch("ai_workplace.services.payroll.generate_salary_slip_pdf")
    @patch("ai_workplace.services.payroll.get_salary_slips_for_months")
    def test_build_salary_slip_download_outbound_single(self, mock_get_slips, mock_pdf):
        mock_get_slips.return_value = [
            {"name": "SLIP-1", "start_date": "2026-07-01", "net_pay": 50000},
        ]
        mock_pdf.return_value = (b"%PDF-test", "Salary_Slip_EMP-001_Jul_2026.pdf")

        outbound = build_salary_slip_download_outbound(self.context_en, 1)
        self.assertTrue(outbound.has_document())
        self.assertEqual(outbound.document_mimetype, "application/pdf")
        self.assertEqual(len(outbound.follow_up), 1)

    @patch("ai_workplace.services.payroll.generate_salary_slip_pdf")
    @patch("ai_workplace.services.payroll.get_salary_slips_for_months")
    def test_build_salary_slip_download_outbound_with_period_options(self, mock_get_slips, mock_pdf):
        mock_get_slips.return_value = [
            {"name": "SLIP-1", "start_date": "2026-07-01", "net_pay": 50000},
        ]
        mock_pdf.return_value = (b"%PDF-test", "Salary_Slip_EMP-001_Jul_2026.pdf")

        outbound = build_salary_slip_download_outbound(
            self.context_en, 3, show_period_options_after=True
        )
        self.assertTrue(outbound.has_document())
        btn_ids = [b["reply"]["id"] for b in outbound.follow_up[0].interactive["action"]["buttons"]]
        self.assertIn("svc_pay_slip_3m", btn_ids)

    @patch("ai_workplace.services.payroll.get_salary_slips_for_months")
    def test_build_salary_slip_download_outbound_empty(self, mock_get_slips):
        mock_get_slips.return_value = []
        outbound = build_salary_slip_download_outbound(self.context_en, 3, show_period_options_after=True)
        self.assertIn("No submitted salary slips", outbound.body_text)
        self.assertEqual(len(outbound.follow_up), 1)

    def test_build_slip_document_caption(self):
        slip = {"start_date": "2026-07-01", "net_pay": 75000}
        cap = build_slip_document_caption(self.context_en, slip, 1, 2)
        self.assertIn("salary slip", cap)
        self.assertIn("(1/2)", cap)

    @patch("ai_workplace.services.payroll.frappe")
    def test_generate_salary_slip_pdf_uses_default_format(self, mock_frappe):
        mock_doc = MagicMock()
        mock_doc.start_date = "2026-06-01"
        mock_doc.employee = "EMP-001"
        mock_frappe.get_doc.return_value = mock_doc
        mock_frappe.get_meta.return_value.default_print_format = "Salary Slip New"
        mock_frappe.session.user = "Administrator"
        mock_frappe.get_print.return_value = b"%PDF"

        content, filename = generate_salary_slip_pdf("SLIP-1")
        self.assertTrue(filename.endswith(".pdf"))
        self.assertEqual(content, b"%PDF")
        mock_frappe.get_print.assert_called_once()
        call_kwargs = mock_frappe.get_print.call_args.kwargs
        self.assertEqual(call_kwargs["print_format"], "Salary Slip New")
        self.assertTrue(call_kwargs["as_pdf"])

    def test_wrap_salary_slip_period_options(self):
        msg = wrap_salary_slip_period_options("Choose period", self.context_en)
        self.assertEqual(msg.body_text, "Choose period")
        opts = build_salary_slip_period_options_message(self.context_en)
        btn_ids = [b["reply"]["id"] for b in opts.interactive["action"]["buttons"]]
        self.assertIn("svc_pay_slip_1m", btn_ids)
        self.assertIn("svc_pay_slip_3m", btn_ids)
        self.assertIn("svc_pay_slip_6m", btn_ids)

    def test_build_salary_slip_not_found(self):
        msg = build_salary_slip_not_found(self.context_en, 6)
        self.assertIn("6 month", msg)


if __name__ == "__main__":
    unittest.main()
