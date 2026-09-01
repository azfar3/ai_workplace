"""Backfill delivery_status on existing outbound WhatsApp Message Log rows."""

import frappe


def execute():
    if not frappe.db.has_column("WhatsApp Message Log", "delivery_status"):
        return

    frappe.db.sql(
        """
        UPDATE `tabWhatsApp Message Log`
        SET delivery_status = CASE
            WHEN status = 'Failed' THEN 'Failed'
            ELSE 'Sent'
        END
        WHERE direction = 'Outbound'
          AND (delivery_status IS NULL OR delivery_status = '')
        """
    )
    frappe.db.commit()
