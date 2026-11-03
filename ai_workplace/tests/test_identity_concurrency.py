"""No-site regression for concurrent WhatsApp identity updates."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestIdentityConcurrency(unittest.TestCase):
    def test_overlapping_messages_read_latest_identity_before_saving(self):
        row = dict(name="WA-1", normalized_phone="+923001234567",
                   modified=0, preferred_language="en")
        row_lock = Lock()
        first_loaded = Event()
        second_started = Event()
        reads = []
        frappe = MagicMock()
        frappe.db.get_value.return_value = "WA-1"
        frappe.db.commit.side_effect = row_lock.release

        def get_doc(doctype, name, *, for_update=False):
            self.assertTrue(for_update, "Identity must be locked before it is read")
            row_lock.acquire(timeout=5) or self.fail("Identity lock timed out")
            doc = SimpleNamespace(**row, flags=SimpleNamespace())
            reads.append(doc.modified)
            if len(reads) == 1:
                first_loaded.set()
                self.assertTrue(second_started.wait(5))

            def save(**kwargs):
                self.assertEqual(doc.modified, row["modified"], "Stale identity save")
                row.update({k: v for k, v in vars(doc).items() if k not in {"flags", "save"}})
                row["modified"] += 1
                # Model an unrelated field updated by the first transaction.
                if row["modified"] == 1:
                    row["preferred_language"] = "ur"
            doc.save = save
            return doc

        frappe.get_doc.side_effect = get_doc
        path = Path(__file__).parents[1] / "identity" / "resolver.py"
        spec = importlib.util.spec_from_file_location("isolated_identity_resolver", path)
        resolver = importlib.util.module_from_spec(spec)
        phone = MagicMock()
        phone.PhoneNormalizationError = ValueError
        with patch.dict(sys.modules, {"frappe": frappe,
                                      spec.name: resolver,
                                      "ai_workplace.identity.phone": phone}):
            spec.loader.exec_module(resolver)
            identity = {"status": "matched", "normalized_phone": row["normalized_phone"],
                        "user": "employee@example.com", "employee": "EMP-1"}

            def second_message():
                self.assertTrue(first_loaded.wait(5))
                second_started.set()
                return resolver.get_or_create_whatsapp_identity(identity)

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(resolver.get_or_create_whatsapp_identity, identity)
                second = pool.submit(second_message)
                self.assertEqual(first.result(timeout=10), "WA-1")
                self.assertEqual(second.result(timeout=10), "WA-1")

        self.assertEqual(reads, [0, 1])
        self.assertEqual(row["modified"], 2)
        self.assertEqual(row["preferred_language"], "ur")
        self.assertEqual(row["employee"], "EMP-1")
        self.assertEqual(frappe.db.commit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
