import frappe
import unittest
from ai_workplace.api.analytics import (
    get_dashboard_summary,
    get_usage_metrics,
    get_provider_health,
    get_rag_metrics,
    get_conversation_metrics,
    get_security_metrics,
    get_recent_activity
)

class TestAnalytics(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        
        # Insert Mock Provider and Model
        if not frappe.db.exists("AI Workplace Provider", "TestProvider"):
            p = frappe.get_doc({
                "doctype": "AI Workplace Provider",
                "name": "TestProvider",
                "provider_name": "TestProvider"
            })
            p.db_insert()
            
        if not frappe.db.exists("AI Workplace Model", "test-model"):
            m = frappe.get_doc({
                "doctype": "AI Workplace Model",
                "name": "test-model",
                "model_slug": "test-model",
                "provider": "TestProvider"
            })
            m.db_insert()

        # Cleanup mock logs
        frappe.db.sql("DELETE FROM `tabAI Workplace Usage Log`")
        frappe.db.sql("DELETE FROM `tabWhatsApp Conversation`")
        frappe.db.sql("DELETE FROM `tabAI Action Log`")
        
        # Insert mock usage logs
        self.doc1 = frappe.get_doc({
            "doctype": "AI Workplace Usage Log",
            "name": "test_log_1",
            "provider": "TestProvider",
            "model": "test-model",
            "success": 1,
            "fallback_used": 0,
            "tokens_in": 10,
            "tokens_out": 20,
            "tokens_total": 30,
            "total_cost": 0.001,
            "latency_ms": 150,
            "channel": "WhatsApp"
        }).insert(ignore_permissions=True)
        
        self.doc2 = frappe.get_doc({
            "doctype": "AI Workplace Usage Log",
            "name": "test_log_2",
            "provider": "TestProvider",
            "success": 0,
            "fallback_used": 1,
            "tokens_total": 10,
            "total_cost": 0.0005,
            "latency_ms": 300,
            "channel": "HR Desk"
        }).insert(ignore_permissions=True)
        
        # Insert mock conversation
        self.conv = frappe.get_doc({
            "doctype": "WhatsApp Conversation",
            "name": "test_conv_1",
            "whatsapp_identity": "test_id",
            "conversation_status": "Active"
        })
        self.conv.db_insert()
        
        # Insert mock action log
        self.action = frappe.get_doc({
            "doctype": "AI Action Log",
            "name": "test_action_1",
            "action": "Security Escalation",
            "trace_id": "trace_1"
        })
        self.action.db_insert()

        frappe.db.commit()

    def tearDown(self):
        frappe.db.sql("DELETE FROM `tabAI Workplace Usage Log`")
        frappe.db.sql("DELETE FROM `tabWhatsApp Conversation`")
        frappe.db.sql("DELETE FROM `tabAI Action Log`")
        frappe.db.commit()

    def test_dashboard_summary(self):
        summary = get_dashboard_summary()
        self.assertIn("health", summary)
        self.assertTrue(summary["requests_total"] >= 2)
        self.assertTrue(summary["tokens_total"] >= 40)
        self.assertTrue(summary["total_cost"] >= 0.0015)
        self.assertTrue(summary["active_conversations"] >= 1)

    def test_usage_metrics(self):
        metrics = get_usage_metrics(days=7)
        self.assertIn("timeline", metrics)
        self.assertIn("providers", metrics)
        
        provider_data = [p for p in metrics["providers"] if p["provider"] == "TestProvider"]
        self.assertEqual(len(provider_data), 1)
        self.assertEqual(provider_data[0]["total"], 2)
        self.assertEqual(provider_data[0]["tokens"], 40)
        
    def test_conversation_metrics(self):
        metrics = get_conversation_metrics()
        self.assertTrue(metrics["active"] >= 1)
        
    def test_security_metrics(self):
        metrics = get_security_metrics()
        self.assertTrue(metrics["blocked_actions"] >= 1)

