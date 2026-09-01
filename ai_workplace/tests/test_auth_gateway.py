"""
ai_workplace/tests/test_auth_gateway.py
─────────────────────────────────────────
Unit tests for Authorization Gateway.
"""

import unittest

from ai_workplace.auth.gateway import authorize


class TestAuthGateway(unittest.TestCase):

    def setUp(self):
        self.employee_context = {
            "person_type": "Employee",
            "staff_category": "permanent",
            "allowed_services": ["hr", "policy", "travel", "help"],
        }
        self.deliverable_context = {
            "person_type": "Employee",
            "staff_category": "project_deliverable",
            "allowed_services": [
                "hr",
                "deliverables",
                "payroll",
                "pay_tax_deduction",
                "pay_bank_letter",
                "pay_bank_faysal",
                "pay_bank_scb",
                "policies",
                "concerns",
                "contact_hr",
            ],
        }
        self.guest_context = {
            "person_type": "Guest",
            "allowed_services": [],
        }

    def test_authorized_employee_service(self):
        res = authorize(None, self.employee_context, "hr")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["service"], "hr")

    def test_unauthorized_employee_service(self):
        res = authorize(None, self.employee_context, "deliverables")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_unregistered_restrictions(self):
        res_help = authorize(None, self.guest_context, "help")
        self.assertFalse(res_help["allowed"])
        self.assertEqual(res_help["reason"], "GUEST_RESTRICTED")

        res_hr = authorize(None, self.guest_context, "hr")
        self.assertFalse(res_hr["allowed"])
        self.assertEqual(res_hr["reason"], "GUEST_RESTRICTED")

    def test_deliverable_sub_actions_allowed(self):
        for svc in ("deliverables", "dlv_add", "dlv_submit", "dlv_status", "dlv_submit_now"):
            res = authorize(None, self.deliverable_context, svc)
            self.assertTrue(res["allowed"], svc)

    def test_deliverable_staff_denied_payroll(self):
        res = authorize(None, self.deliverable_context, "pay_download_slip")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_deliverable_staff_allowed_tax_certificate(self):
        res = authorize(None, self.deliverable_context, "pay_tax_deduction")
        self.assertTrue(res["allowed"])

    def test_deliverable_staff_allowed_bank_letter(self):
        res = authorize(None, self.deliverable_context, "pay_bank_letter")
        self.assertTrue(res["allowed"])

    def test_direct_unauthorized_attempt_rejection(self):
        emp_b_context = {
            "person_type": "Employee",
            "allowed_services": ["policy", "help"],
        }
        res = authorize(None, emp_b_context, "hr")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_monthly_attendance_sub_actions_via_attendance_leave(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["attendance_leave", "help"],
        }
        for svc in ("att_monthly", "att_monthly_last7", "att_monthly_download"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)
            self.assertEqual(res["service"], svc)

    def test_monthly_attendance_sub_actions_denied_without_parent(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["policy", "help"],
        }
        res = authorize(None, ctx, "att_monthly_last7")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_salary_slip_sub_actions_via_payroll(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["payroll", "help"],
        }
        for svc in ("pay_slip_1m", "pay_slip_3m", "pay_slip_6m", "pay_download_slip", "pay_previous_slips"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)
            self.assertEqual(res["service"], svc)

    def test_salary_slip_sub_actions_via_former_payslip(self):
        ctx = {
            "person_type": "Former Employee",
            "allowed_services": ["former_payslip", "former_letter"],
        }
        for svc in ("pay_slip_1m", "pay_slip_3m", "pay_slip_6m", "former_payslip"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)

    def test_salary_slip_sub_actions_denied_without_payroll(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["policy", "help"],
        }
        res = authorize(None, ctx, "pay_slip_3m")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["reason"], "SERVICE_NOT_ALLOWED")

    def test_guest_careers_menus_allowed(self):
        ctx = {
            "person_type": "Guest",
            "allowed_services": ["guest_careers", "guest_job_status", "guest_concern", "contact_hr"],
        }
        for svc in ("guest_careers", "guest_job_status"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)

    def test_former_careers_allowed(self):
        ctx = {
            "person_type": "Former Employee",
            "allowed_services": ["former_careers", "former_letter", "contact_hr"],
        }
        res = authorize(None, ctx, "former_careers")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["service"], "former_careers")

    def test_profile_flows_allowed_under_hr(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["hr", "policies", "help"],
        }
        for svc in ("prof_cnic_add", "prof_contact_update", "gap_cnic_scans", "update_profile"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)

    def test_policy_submenus_allowed(self):
        ctx = {
            "person_type": "Employee",
            "allowed_services": ["policies", "help"],
        }
        for svc in ("pol_view_policies", "pol_ai_assistant", "pol_sel_TEST-POLICY"):
            res = authorize(None, ctx, svc)
            self.assertTrue(res["allowed"], svc)
