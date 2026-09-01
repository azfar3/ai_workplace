"""
Expanded smoke test for Phases 1.1, 1.3, 2.1, 2.3, and 3.
Tests both the QueryResolver's four-layer scoring AND that workflow intents
are correctly identified (response_mode="workflow").

Run via: bench --site erp.v15 run-tests --app ai_workplace --module ai_workplace.tests.test_resolver_routing
"""
import unittest
from ai_workplace.ai.query_resolver import QueryResolver


class TestQueryResolverLayer1Alias(unittest.TestCase):
    """Layer 1: exact alias match (score 1.0)"""

    def _check(self, msg, expected_intent, expected_mode):
        intent, meta, score = QueryResolver.resolve(msg)
        self.assertEqual(intent, expected_intent, f"Wrong intent for: {msg!r}")
        self.assertGreaterEqual(score, 0.7, f"Score too low for: {msg!r}")
        self.assertEqual(meta["response_mode"], expected_mode, f"Wrong mode for: {msg!r}")

    def test_leave_balance_exact(self):
        self._check("what is my leave balance", "leave_balance", "deterministic")

    def test_salary_slip_exact(self):
        self._check("show my salary slip", "latest_salary_slip", "deterministic")

    def test_attendance_today_exact(self):
        self._check("today attendance", "today_attendance", "deterministic")

    def test_apply_leave_exact(self):
        self._check("apply leave", "apply_leave", "workflow")

    def test_maternity_policy_exact(self):
        self._check("what is the maternity leave policy", "maternity_leave_policy", "hybrid")

    def test_carry_forward_exact(self):
        self._check("can i carry forward my remaining 4 leaves", "carry_forward_leave", "hybrid")


class TestQueryResolverLayer2Substring(unittest.TestCase):
    """Layer 2: alias substring match (score 0.8)"""

    def _check(self, msg, expected_intent):
        intent, meta, score = QueryResolver.resolve(msg)
        self.assertEqual(intent, expected_intent, f"Wrong intent for: {msg!r}")
        self.assertGreaterEqual(score, 0.7)

    def test_leave_balance_substring(self):
        self._check("what is my remaining leave balance today", "leave_balance")

    def test_salary_slip_substring(self):
        self._check("please send salary slip for this month", "latest_salary_slip")

    def test_policy_list_substring(self):
        self._check("show me the published policies for employees", "policy_list")


class TestQueryResolverLayer3Patterns(unittest.TestCase):
    """Layer 3: regex pattern match (score 0.85)"""

    def _check(self, msg, expected_intent, expected_mode=None):
        intent, meta, score = QueryResolver.resolve(msg)
        self.assertEqual(intent, expected_intent, f"Wrong intent for: {msg!r}")
        self.assertGreaterEqual(score, 0.7, f"Score too low for: {msg!r}")
        if expected_mode:
            self.assertEqual(meta["response_mode"], expected_mode)

    # Leave
    def test_leave_balance_pattern_how_many(self):
        self._check("how many leaves do I have remaining", "leave_balance")

    def test_leave_balance_pattern_urdu(self):
        self._check("kitne leaves hain mere", "leave_balance")

    def test_leave_balance_pattern_annual(self):
        self._check("how many annual leaves remaining", "leave_balance")

    def test_apply_leave_pattern_need(self):
        self._check("I need a leave from Monday", "apply_leave", "workflow")

    def test_apply_leave_pattern_chutti(self):
        self._check("chutti chahiye", "apply_leave", "workflow")

    def test_apply_leave_pattern_request(self):
        self._check("request leave starting from Friday", "apply_leave", "workflow")

    def test_leave_history_pattern(self):
        self._check("show my leave history", "leave_history", "deterministic")

    def test_leave_history_how_many_taken(self):
        self._check("how many leaves did I take this year", "leave_history")

    def test_carry_forward_pattern(self):
        self._check("can i carry forward my unused leaves", "carry_forward_leave", "hybrid")

    def test_carry_forward_what_happens(self):
        self._check("what happens to unused annual leave", "carry_forward_leave")

    # Payroll
    def test_salary_slip_pattern_download(self):
        self._check("download salary slip", "latest_salary_slip")

    def test_salary_slip_pattern_view(self):
        self._check("view my salary slip", "latest_salary_slip")

    def test_salary_slip_urdu_pattern(self):
        self._check("bhejo meri salary", "latest_salary_slip")

    def test_tax_deduction_pattern(self):
        self._check("how much tax was deducted this month", "tax_deductions")

    def test_tax_deduction_pattern2(self):
        self._check("income tax deduction details", "tax_deductions")

    # Attendance
    def test_attendance_today_pattern_checkin(self):
        self._check("did I check in today", "today_attendance")

    def test_attendance_today_checkin_time(self):
        self._check("what time did I check in", "today_attendance")

    def test_attendance_today_urdu(self):
        self._check("aaj ki attendance", "today_attendance")

    def test_monthly_attendance_pattern(self):
        self._check("show my attendance for this month", "monthly_attendance")

    def test_monthly_attendance_summary(self):
        self._check("attendance summary for August", "monthly_attendance")

    def test_forgot_checkin_pattern(self):
        self._check("I forgot to check in today", "forgot_checkin", "workflow")

    def test_forgot_checkin_missed(self):
        self._check("missed check in", "forgot_checkin")

    def test_forgot_checkin_urdu(self):
        self._check("check in nahi hua", "forgot_checkin")

    # Profile
    def test_designation_pattern(self):
        self._check("what is my designation", "my_designation")

    def test_designation_mera(self):
        self._check("mera designation kya hai", "my_designation")

    def test_department_pattern(self):
        self._check("which department am I in", "my_department")

    def test_profile_gaps_pattern(self):
        self._check("my profile completion status", "profile_gaps")

    # Policy / navigation
    def test_policy_list_pattern(self):
        self._check("show all policies", "policy_list")

    def test_office_timings_pattern(self):
        self._check("what are the office timings", "office_timings")

    def test_office_hours_pattern(self):
        self._check("when does office start", "office_timings")

    def test_maternity_pattern(self):
        self._check("maternity leave rules", "maternity_leave_policy")


class TestWorkflowMode(unittest.TestCase):
    """Phase 3: workflow intents are correctly classified so the orchestrator
    can start the multi-step flow directly without a submenu round-trip."""

    def _workflow(self, msg, expected_workflow_intent):
        intent, meta, score = QueryResolver.resolve(msg)
        self.assertGreaterEqual(score, 0.7, f"Score too low for: {msg!r}")
        self.assertEqual(meta["response_mode"], "workflow", f"Not workflow mode for: {msg!r}")
        self.assertEqual(meta.get("workflow_intent"), expected_workflow_intent,
                         f"Wrong workflow_intent for: {msg!r}")

    def test_apply_leave_starts_leave_apply_flow(self):
        self._workflow("apply leave", "leave_apply")

    def test_need_leave_starts_leave_apply_flow(self):
        self._workflow("I need a leave from Monday to Wednesday", "leave_apply")

    def test_chutti_chahiye_starts_leave_apply_flow(self):
        self._workflow("chutti chahiye", "leave_apply")

    def test_forgot_checkin_starts_att_exception_flow(self):
        self._workflow("I forgot to check in today", "att_exception")

    def test_missed_checkin_starts_att_exception_flow(self):
        self._workflow("missed check in", "att_exception")


class TestUnknownFallthrough(unittest.TestCase):
    """Queries that should NOT resolve deterministically (→ LLM fallback)."""

    def _unknown(self, msg):
        intent, meta, score = QueryResolver.resolve(msg)
        self.assertLess(score, 0.7, f"Should be unknown but resolved for: {msg!r}")
        self.assertEqual(intent, "unknown", f"Should be unknown for: {msg!r}")

    def test_flight_booking_unknown(self):
        self._unknown("I want to book a flight to Lahore")

    def test_complicated_query_unknown(self):
        self._unknown("I have a complicated HR situation with my manager")

    def test_very_short_single_word(self):
        self._unknown("hi")


if __name__ == "__main__":
    unittest.main()
