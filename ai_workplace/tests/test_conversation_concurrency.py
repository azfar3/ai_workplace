"""No-site regression for state updates after a slow agent response."""
from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestConversationConcurrency(unittest.TestCase):
    def test_update_reloads_under_lock_and_preserves_unrelated_fields(self):
        frappe = MagicMock()
        frappe.utils.now_datetime.return_value = datetime(2026, 11, 3)
        path = Path(__file__).parents[1] / 'conversation' / 'manager.py'
        spec = importlib.util.spec_from_file_location('isolated_conversation_manager', path)
        manager = importlib.util.module_from_spec(spec)
        resolver = MagicMock()
        with patch.dict(sys.modules, {'frappe': frappe, spec.name: manager,
                                     'ai_workplace.identity.resolver': resolver,
                                     'ai_workplace.conversation.state': MagicMock()}):
            spec.loader.exec_module(manager)
            conv = MagicMock()
            conv.flags = SimpleNamespace()
            conv.modified = 'old'
            conv.preferred_language = 'English'
            calls = []

            def reload():
                self.assertTrue(conv.flags.for_update)
                calls.append('reload')
                conv.modified = 'latest'
                conv.preferred_language = 'Urdu'

            def save(**kwargs):
                calls.append('save')
                self.assertEqual(conv.modified, 'latest')
                self.assertEqual(conv.preferred_language, 'Urdu')
                self.assertEqual(conv.current_state, 'AWAITING_SELECTION')

            conv.reload.side_effect = reload
            conv.save.side_effect = save
            with patch.object(manager, 'get_default_ttl_minutes', return_value=60):
                result = manager.update_conversation(conv, state='AWAITING_SELECTION')
            self.assertIs(result, conv)
            self.assertEqual(calls, ['reload', 'save'])
            frappe.db.commit.assert_called_once()
