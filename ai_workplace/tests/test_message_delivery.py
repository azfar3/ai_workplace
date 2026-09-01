"""
ai_workplace/tests/test_message_delivery.py
────────────────────────────────────────────
Unit tests for WhatsApp delivery/read status tracking.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ai_workplace.services.message_delivery import (
    handle_delivery_status_webhook,
    normalize_delivery_status,
    should_advance_delivery,
)


class TestMessageDeliveryHelpers(unittest.TestCase):
    def test_normalize_delivery_status(self):
        self.assertEqual(normalize_delivery_status("sent"), "Sent")
        self.assertEqual(normalize_delivery_status("DELIVERED"), "Delivered")
        self.assertEqual(normalize_delivery_status("read"), "Read")
        self.assertEqual(normalize_delivery_status("failed"), "Failed")
        self.assertEqual(normalize_delivery_status("unknown"), "")

    def test_should_advance_delivery(self):
        self.assertTrue(should_advance_delivery("Sent", "Delivered"))
        self.assertTrue(should_advance_delivery("Delivered", "Read"))
        self.assertFalse(should_advance_delivery("Read", "Delivered"))
        self.assertFalse(should_advance_delivery("Read", "Sent"))
        self.assertTrue(should_advance_delivery("Sent", "Failed"))
        self.assertFalse(should_advance_delivery("Failed", "Sent"))


class TestHandleDeliveryStatusWebhook(unittest.TestCase):
    def setUp(self):
        frappe.db.rollback()

    def tearDown(self):
        frappe.db.rollback()

    @patch("ai_workplace.services.message_delivery.publish_session_update")
    def test_updates_log_and_publishes(self, mock_publish):
        log_name = frappe.db.get_value(
            "WhatsApp Message Log",
            {"direction": "Outbound"},
            "name",
        )
        if not log_name:
            self.skipTest("No outbound WhatsApp Message Log in test DB")

        meta_id = frappe.db.get_value("WhatsApp Message Log", log_name, "meta_message_id") or "wamid.test.delivery"
        session = frappe.db.get_value("WhatsApp Message Log", log_name, "hr_live_chat_session") or ""
        frappe.db.set_value("WhatsApp Message Log", log_name, {"meta_message_id": meta_id, "delivery_status": "Sent"})
        frappe.db.commit()

        parsed = {"message_id": meta_id, "delivery_status": "delivered"}
        result = handle_delivery_status_webhook(parsed)

        self.assertIsNotNone(result)
        self.assertEqual(result["log_name"], log_name)
        self.assertEqual(result["delivery_status"], "Delivered")
        self.assertEqual(frappe.db.get_value("WhatsApp Message Log", log_name, "delivery_status"), "Delivered")

        if session:
            mock_publish.assert_called_once()
            payload = mock_publish.call_args[0][1]
            self.assertEqual(payload["event"], "delivery_status_update")
            self.assertEqual(payload["delivery_status"], "Delivered")

    def test_ignores_inbound_logs(self):
        log_name = frappe.db.get_value(
            "WhatsApp Message Log",
            {"direction": "Inbound"},
            "name",
        )
        if not log_name:
            self.skipTest("No inbound WhatsApp Message Log in test DB")

        meta_id = f"wamid.inbound.{log_name}"
        frappe.db.set_value("WhatsApp Message Log", log_name, {"meta_message_id": meta_id, "direction": "Inbound"})
        frappe.db.commit()

        result = handle_delivery_status_webhook({"message_id": meta_id, "delivery_status": "read"})
        self.assertIsNone(result)

    def test_does_not_downgrade_read_to_delivered(self):
        log_name = frappe.db.get_value(
            "WhatsApp Message Log",
            {"direction": "Outbound"},
            "name",
        )
        if not log_name:
            self.skipTest("No outbound WhatsApp Message Log in test DB")

        meta_id = f"wamid.read.{log_name}"
        frappe.db.set_value(
            "WhatsApp Message Log",
            log_name,
            {"meta_message_id": meta_id, "delivery_status": "Read"},
        )
        frappe.db.commit()

        result = handle_delivery_status_webhook({"message_id": meta_id, "delivery_status": "delivered"})
        self.assertIsNone(result)
        self.assertEqual(frappe.db.get_value("WhatsApp Message Log", log_name, "delivery_status"), "Read")
