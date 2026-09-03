"""
ai_workplace/tests/test_cascade_delete.py
──────────────────────────────────────────
Unit tests for targeted cascade deletion of Log DocTypes in AI Workplace.
"""

import unittest
import frappe


class TestCascadeDelete(unittest.TestCase):
    def test_knowledge_source_cascade_delete(self):
        source_name = "Test Policy Document Unique 123"
        if frappe.db.exists("AI Workplace Knowledge Source", source_name):
            frappe.delete_doc("AI Workplace Knowledge Source", source_name, ignore_permissions=True, force=True)

        # Create a Knowledge Source
        source = frappe.new_doc("AI Workplace Knowledge Source")
        source.source_name = source_name
        source.source_type = "Policy"
        source.status = "Active"
        source.insert(ignore_permissions=True)

        # Create a Knowledge Chunk linked to this Source
        chunk = frappe.new_doc("AI Workplace Knowledge Chunk")
        chunk.knowledge_source = source.name
        chunk.chunk_index = 1
        chunk.chunk_text = "This is test chunk content for cascade delete test."
        chunk.insert(ignore_permissions=True)

        chunk_name = chunk.name
        self.assertTrue(frappe.db.exists("AI Workplace Knowledge Chunk", chunk_name))

        # Delete the Parent Knowledge Source
        frappe.delete_doc("AI Workplace Knowledge Source", source.name, ignore_permissions=True)

        # Assert the linked Knowledge Chunk is automatically deleted
        self.assertFalse(frappe.db.exists("AI Workplace Knowledge Chunk", chunk_name))
        self.assertFalse(frappe.db.exists("AI Workplace Knowledge Source", source.name))

    def test_whatsapp_identity_cascade_delete(self):
        wa_id = "test_wa_id_99999_unique"
        existing = frappe.db.get_value("WhatsApp Identity", {"whatsapp_id": wa_id}, "name")
        if existing:
            frappe.delete_doc("WhatsApp Identity", existing, ignore_permissions=True, force=True)

        # Create a WhatsApp Identity
        identity = frappe.new_doc("WhatsApp Identity")
        identity.whatsapp_id = wa_id
        identity.normalized_phone = "+923999999999"
        identity.status = "Active"
        identity.insert(ignore_permissions=True)

        # Create a WhatsApp Conversation linked to Identity
        conv = frappe.new_doc("WhatsApp Conversation")
        conv.whatsapp_identity = identity.name
        conv.conversation_status = "Active"
        conv.insert(ignore_permissions=True)
        conv_name = conv.name

        # Create an HR Live Chat Session linked to Identity & Conversation
        session = frappe.new_doc("HR Live Chat Session")
        session.whatsapp_identity = identity.name
        session.conversation = conv.name
        session.status = "Queued"
        session.insert(ignore_permissions=True)
        session_name = session.name

        self.assertTrue(frappe.db.exists("WhatsApp Conversation", conv_name))
        self.assertTrue(frappe.db.exists("HR Live Chat Session", session_name))

        # Delete the WhatsApp Identity
        frappe.delete_doc("WhatsApp Identity", identity.name, ignore_permissions=True)

        # Assert linked conversation and session are automatically deleted
        self.assertFalse(frappe.db.exists("WhatsApp Conversation", conv_name))
        self.assertFalse(frappe.db.exists("HR Live Chat Session", session_name))
        self.assertFalse(frappe.db.exists("WhatsApp Identity", identity.name))
