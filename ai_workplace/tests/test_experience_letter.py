"""
ai_workplace/tests/test_experience_letter.py
─────────────────────────────────────────────
Unit tests for employee experience letter generation with conditional work history table.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import today, formatdate

from ai_workplace.services.employee_letters import (
    render_experience_letter_content,
    generate_experience_letter_pdf,
    WORK_HISTORY_TABLE_TEMPLATE,
    _create_employee_letter,
)


SAMPLE_TEMPLATE_CONTENT = """<p style="text-align: right;">{{qr_code}}</p>
<p style="text-align: right;"><strong>{{series}}</strong></p>
<p style="text-align: right;"><strong>Dated: {{today_date}}</strong></p>
<p style="text-align: center;"><strong><u>To Whom It May Concern</u></strong></p>
<p style="text-align: justify;">This is to certify that <strong>{{employee_name}}</strong> holding CNIC No. <strong>{{cnic}}</strong>, has been employed with <strong>MicroMerger (Pvt.) Ltd.</strong> as <strong>{{designation}}</strong> employment since <strong>{{date_of_joining}}</strong>, as a third party contracted staff serving at duty station, <strong>{{custom_district_name}}, {{custom_province_name}}</strong>.</p>
<p>{table}<strong> </strong></p>
<p style="text-align: justify;"><strong>{{first_field}} {{second_field}} {{third_field}} {{fourth_field}}</strong></p>
<p style="text-align: justify;">This letter is being issued upon the employee's request and carries no liability on <strong>MicroMerger (Pvt.) Ltd.</strong></p>
<p style="text-align: justify;"><strong>MicroMerger (Pvt.) Ltd.</strong> wishes best of luck for future endeavors.</p>
<p>Regards,</p>
<p><strong>HR Department</strong></p>
<p><strong>MicroMerger (Pvt.) Ltd.</strong></p>"""


class TestExperienceLetterGeneration(unittest.TestCase):
    def setUp(self):
        frappe.local.lang = "en"

    def test_experience_letter_with_internal_work_history(self):
        """When internal_work_history is filled, a styled table should be inserted replacing {table}."""
        emp = {
            "name": "EMP-MM-00100",
            "employee_name": "Test Employee With History",
            "designation": "Senior Engineer",
            "date_of_joining": "2020-01-15",
            "cnic": "12345-1234567-1",
            "custom_district_name": "Islamabad",
            "custom_province_name": "ICT",
            "internal_work_history": [
                {
                    "designation": "Associate Engineer",
                    "from_date": "2020-01-15",
                    "to_date": "2021-12-31",
                },
                {
                    "designation": "Senior Engineer",
                    "from_date": "2022-01-01",
                    "to_date": None,
                },
            ],
        }

        rendered = render_experience_letter_content(emp, SAMPLE_TEMPLATE_CONTENT)

        # Must contain work history table and styling
        self.assertIn("work-history-card", rendered)
        self.assertIn("work-history-table", rendered)
        self.assertIn("<th>Designation</th>", rendered)
        self.assertIn("<th>From</th>", rendered)
        self.assertIn("<th>To</th>", rendered)

        # Check table contents
        self.assertIn("Associate Engineer", rendered)
        self.assertIn("15-Jan-2020", rendered)
        self.assertIn("31-Dec-2021", rendered)
        self.assertIn("Senior Engineer", rendered)
        self.assertIn("01-Jan-2022", rendered)
        self.assertIn("Present", rendered)

        # Must NOT contain raw {table} placeholder
        self.assertNotIn("{table}", rendered)
        self.assertNotIn("{{first_field}}", rendered)

    def test_experience_letter_without_internal_work_history(self):
        """When internal_work_history is empty, experience letter should be generated without any table."""
        emp = {
            "name": "EMP-MM-00200",
            "employee_name": "Test Employee Without History",
            "designation": "Software Developer",
            "date_of_joining": "2022-06-01",
            "cnic": "54321-7654321-2",
            "custom_district_name": "Lahore",
            "custom_province_name": "Punjab",
            "internal_work_history": [],
        }

        rendered = render_experience_letter_content(emp, SAMPLE_TEMPLATE_CONTENT)

        # Must NOT contain table markup
        self.assertNotIn("work-history-card", rendered)
        self.assertNotIn("work-history-table", rendered)
        self.assertNotIn("<th>Designation</th>", rendered)

        # Must NOT contain raw {table} placeholder or empty paragraph
        self.assertNotIn("{table}", rendered)
        self.assertNotIn("<p>{table}<strong> </strong></p>", rendered)
        self.assertNotIn("{{first_field}}", rendered)

        # Must contain the single designation text
        self.assertIn("Software Developer", rendered)
        self.assertIn("01-Jun-2022", rendered)
        self.assertIn("Lahore", rendered)
        self.assertIn("Test Employee Without History", rendered)

    def test_experience_letter_with_none_internal_work_history(self):
        """When internal_work_history is None, no table is included."""
        emp = {
            "name": "EMP-MM-00300",
            "employee_name": "Test Null History",
            "designation": "Business Analyst",
            "date_of_joining": "2023-03-01",
            "cnic": "11111-2222222-3",
            "internal_work_history": None,
        }

        rendered = render_experience_letter_content(emp, SAMPLE_TEMPLATE_CONTENT)
        self.assertNotIn("work-history-card", rendered)
        self.assertNotIn("{table}", rendered)
        self.assertIn("Business Analyst", rendered)

    @patch("ai_workplace.services.employee_letters._letter_pdf_bytes")
    @patch("ai_workplace.services.employee_letters._create_employee_letter")
    def test_generate_experience_letter_pdf_flow(self, mock_create, mock_pdf_bytes):
        """Test full generate_experience_letter_pdf function."""
        mock_create.return_value = "EXP-LTR-9999"
        mock_pdf_bytes.return_value = b"%PDF-test-bytes"

        with patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.exists", return_value=True), \
             patch("frappe.get_single") as mock_get_single:

            mock_hr_settings = MagicMock()
            mock_hr_settings.experience_letter_template = "Experience Letter"
            mock_get_single.return_value = mock_hr_settings

            mock_emp = MagicMock()
            mock_emp.name = "EMP-MM-00500"
            mock_emp.employee_name = "Jane Doe"
            mock_emp.designation = "Lead Architect"
            mock_emp.as_dict.return_value = {
                "name": "EMP-MM-00500",
                "employee_name": "Jane Doe",
                "designation": "Lead Architect",
                "date_of_joining": "2021-05-10",
                "internal_work_history": [],
            }

            mock_template = MagicMock()
            mock_template.letter_content = SAMPLE_TEMPLATE_CONTENT

            def get_doc_side_effect(doctype, name=None):
                if doctype == "Employee":
                    return mock_emp
                elif doctype == "Letter Template":
                    return mock_template
                return MagicMock()

            mock_get_doc.side_effect = get_doc_side_effect

            pdf_bytes, filename = generate_experience_letter_pdf("EMP-MM-00500")

            self.assertEqual(pdf_bytes, b"%PDF-test-bytes")
            self.assertEqual(filename, "Experience_Letter_Jane_Doe.pdf")
            mock_create.assert_called_once()
            called_rendered = mock_create.call_args[1]["rendered_content"]
            self.assertNotIn("{table}", called_rendered)
            self.assertNotIn("work-history-card", called_rendered)
            self.assertIn("Lead Architect", called_rendered)
