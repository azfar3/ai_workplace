"""Prevent previously finalized inbound messages from replaying after deploy."""
import frappe


def execute():
    frappe.db.sql('''UPDATE `tabWhatsApp Message Log`
        SET processing_state=CASE WHEN status='Failed' THEN 'Failed' ELSE 'Skipped' END
        WHERE direction='Inbound' AND status IN ('Received','Failed','Duplicate')
        AND COALESCE(processing_state,'')='' ''')
