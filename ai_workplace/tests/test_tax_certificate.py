"""
ai_workplace/tests/test_tax_certificate.py
────────────────────────────────────────────
Unit tests for Tax Certificate PDF download service.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.services.tax_certificate import (
    build_tax_certificate_caption,
    build_tax_certificate_download_outbound,
    build_tax_certificate_error,
    generate_tax_certificate_pdf,
    resolve_tax_certificate_fiscal_year,
)


class TestTaxCertificate(unittest.TestCase):
    def setUp(self):
        self.context_en = {
            "employee": "EMP-001",
            "user": "emp@example.com",
            "preferred_language": "English",
        }
        self.context_ur = {"employee": "EMP-001", "preferred_language": "Urdu"}

    @patch("ai_workplace.services.tax_certificate.frappe")
    def test_resolve_tax_certificate_fiscal_year(self, mock_frappe):
        mock_frappe.db.get_value.return_value = "2025-2026"
        self.assertEqual(resolve_tax_certificate_fiscal_year(), "2025-2026")

    @patch("ai_workplace.services.tax_certificate.get_pdf")
    @patch("ai_workplace.services.tax_certificate.frappe")
    def test_generate_tax_certificate_pdf(self, mock_frappe, mock_get_pdf):
        mock_frappe.db.exists.return_value = True
        emp = MagicMock()
        emp.company = "MicroMerger"
        emp.employee_name = "Ali Ahmed"
        report_doc = MagicMock()
        report_doc.get_data.return_value = ([], [{"components": "Basic Pay", "total": 1000}])
        mock_frappe.get_doc.side_effect = [emp, report_doc]

        with patch(
            "mm_app.mm_hr.doctype.salary_slip_and_deduction_tool.salary_slip_and_deduction_tool.generate_html_with_custom_template",
            return_value="<html>report</html>",
        ):
            mock_get_pdf.return_value = b"%PDF-test"
            pdf_bytes, filename = generate_tax_certificate_pdf("EMP-001", "2025-2026")

        self.assertEqual(pdf_bytes, b"%PDF-test")
        self.assertIn("Tax_Certificate", filename)
        self.assertIn("2025-2026", filename)

    def test_build_tax_certificate_caption(self):
        cap = build_tax_certificate_caption(self.context_en, "2025-2026")
        self.assertIn("Tax Certificate", cap)
        self.assertIn("2025-2026", cap)

        cap_ur = build_tax_certificate_caption(self.context_ur, "2025-2026")
        self.assertIn("2025-2026", cap_ur)

    def test_build_tax_certificate_error(self):
        self.assertIn("Tax Certificate", build_tax_certificate_error(self.context_en))

    @patch("ai_workplace.services.employee_letters.build_letter_download_outbound")
    @patch("ai_workplace.services.tax_certificate.generate_tax_certificate_pdf")
    @patch("ai_workplace.services.tax_certificate.resolve_tax_certificate_fiscal_year")
    @patch("ai_workplace.services.tax_certificate.frappe")
    def test_build_tax_certificate_download_outbound(
        self, mock_frappe, mock_fy, mock_generate, mock_outbound
    ):
        mock_frappe.db.exists.return_value = True
        mock_frappe.session.user = "Administrator"
        mock_fy.return_value = "2025-2026"
        mock_generate.return_value = (b"%PDF", "Tax_Certificate_Ali_2025-2026.pdf")
        mock_outbound.return_value = MagicMock(has_document=MagicMock(return_value=True))

        outbound = build_tax_certificate_download_outbound(self.context_en)
        self.assertTrue(outbound.has_document())
        mock_outbound.assert_called_once()

    @patch("ai_workplace.services.response_helpers.wrap_with_menu_again")
    @patch("ai_workplace.services.tax_certificate.generate_tax_certificate_pdf")
    @patch("ai_workplace.services.tax_certificate.resolve_tax_certificate_fiscal_year")
    @patch("ai_workplace.services.tax_certificate.frappe")
    def test_build_tax_certificate_download_outbound_error(
        self, mock_frappe, mock_fy, mock_generate, mock_wrap
    ):
        mock_frappe.db.exists.return_value = True
        mock_frappe.session.user = "Administrator"
        mock_fy.return_value = "2025-2026"
        mock_generate.side_effect = Exception("no data")
        mock_wrap.return_value = MagicMock(body_text="error")

        outbound = build_tax_certificate_download_outbound(self.context_en)
        self.assertEqual(outbound.body_text, "error")


if __name__ == "__main__":
    unittest.main()
