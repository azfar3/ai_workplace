"""
Unit tests for Phase 2 Async AI Router, Resilience & Token Accounting
"""

import time
import unittest
from unittest.mock import MagicMock, patch
import frappe
from ai_workplace.ai.router import (
    CircuitBreaker,
    calculate_cost,
    classify_error,
    complete,
    estimate_tokens,
)
from ai_workplace.api.whatsapp_webhook import process_async_whatsapp_message


class TestPhase2AsyncResilience(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Clear test cache
        frappe.cache().delete_value("ai_workplace:circuit:TestProvider")
        frappe.cache().delete_value("ai_workplace:job_processed:msg_test_123")

    def tearDown(self):
        frappe.cache().delete_value("ai_workplace:circuit:TestProvider")
        frappe.cache().delete_value("ai_workplace:job_processed:msg_test_123")

    def test_circuit_breaker_transitions(self):
        provider = "TestProvider"
        threshold = 3
        cooldown = 2

        # 1. Initial State should be CLOSED
        self.assertEqual(CircuitBreaker.get_state(provider, threshold, cooldown), "CLOSED")

        # 2. Record 2 failures -> State remains CLOSED
        CircuitBreaker.record_failure(provider, threshold, cooldown)
        CircuitBreaker.record_failure(provider, threshold, cooldown)
        self.assertEqual(CircuitBreaker.get_state(provider, threshold, cooldown), "CLOSED")

        # 3. Record 3rd failure -> State transitions to OPEN
        state = CircuitBreaker.record_failure(provider, threshold, cooldown)
        self.assertEqual(state, "OPEN")
        self.assertEqual(CircuitBreaker.get_state(provider, threshold, cooldown), "OPEN")

        # 4. Wait for cooldown period -> State transitions to HALF_OPEN
        time.sleep(2.1)
        self.assertEqual(CircuitBreaker.get_state(provider, threshold, cooldown), "HALF_OPEN")

        # 5. Record success in HALF_OPEN -> State transitions to CLOSED
        CircuitBreaker.record_success(provider)
        self.assertEqual(CircuitBreaker.get_state(provider, threshold, cooldown), "CLOSED")

    def test_token_accounting_and_cost(self):
        # Model mock
        model = MagicMock()
        model.input_cost_per_1k = 0.00015
        model.output_cost_per_1k = 0.00060
        model.currency = "USD"

        # Test calculation
        in_cost, out_cost, total_cost, currency = calculate_cost(model, 1000, 500)
        self.assertAlmostEqual(in_cost, 0.00015, places=6)
        self.assertAlmostEqual(out_cost, 0.00030, places=6)
        self.assertAlmostEqual(total_cost, 0.00045, places=6)
        self.assertEqual(currency, "USD")

        # Test fallback token estimation
        text = "Hello world, this is a test prompt for token estimation."
        tokens = estimate_tokens(text)
        self.assertGreater(tokens, 5)

    def test_classify_error(self):
        # Retriable errors
        err_type, retriable = classify_error(None, status_code=429)
        self.assertEqual(err_type, "HTTP_429")
        self.assertTrue(retriable)

        err_type, retriable = classify_error(None, status_code=503)
        self.assertEqual(err_type, "HTTP_503")
        self.assertTrue(retriable)

        # Non-retriable errors
        err_type, retriable = classify_error(None, status_code=401)
        self.assertEqual(err_type, "INVALID_CREDENTIALS")
        self.assertFalse(retriable)

        err_type, retriable = classify_error(None, status_code=400)
        self.assertEqual(err_type, "MALFORMED_REQUEST")
        self.assertFalse(retriable)

    @patch("ai_workplace.api.whatsapp_webhook.process_message")
    @patch("ai_workplace.api.whatsapp_webhook.send_message")
    def test_async_idempotency(self, mock_send, mock_process):
        mock_process.return_value = MagicMock(skip_send=False, log_text=lambda: "Test response", message_type="text")
        mock_send.return_value = {"success": True, "message_id": "outbound_meta_999"}

        # Create dummy inbound log
        log = frappe.new_doc("WhatsApp Message Log")
        log.meta_message_id = "msg_test_123"
        log.direction = "Inbound"
        log.message = "Hello AI"
        log.status = "Processing"
        log.insert(ignore_permissions=True)
        frappe.db.commit()

        # 1st Worker execution -> should process and send message
        res1 = process_async_whatsapp_message(
            inbound_log_name=log.name,
            message_id="msg_test_123",
            wa_id="123456789",
            raw_phone="+923001234567",
            message_text="Hello AI",
            trace_id="trace_test_001",
        )
        self.assertTrue(res1.get("success"))
        self.assertFalse(res1.get("skipped", False))
        self.assertEqual(mock_process.call_count, 1)

        # 2nd Worker execution (duplicate retry) -> should skip execution!
        res2 = process_async_whatsapp_message(
            inbound_log_name=log.name,
            message_id="msg_test_123",
            wa_id="123456789",
            raw_phone="+923001234567",
            message_text="Hello AI",
            trace_id="trace_test_001",
        )
        self.assertTrue(res2.get("success"))
        self.assertTrue(res2.get("skipped", True))
        # process_message should still have call count 1 (not called second time!)
        self.assertEqual(mock_process.call_count, 1)

        # Cleanup
        frappe.delete_doc("WhatsApp Message Log", log.name, force=True)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase2AsyncResilience)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    return {"wasSuccessful": res.wasSuccessful(), "failures": len(res.failures), "errors": len(res.errors)}

