"""No-site concurrency, retry, gateway identity and echo regressions."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.whatsapp import idempotency as guard


class FakeCache:
    def __init__(self):
        self.values={}
        self.lock=Lock()
    def make_key(self,key):
        return 'test-site:'+key
    def set(self,key,value,nx=False,ex=None):
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key]=value
            return True
    def get_value(self,*args,**kwargs):
        return None


class TestWhatsAppGuard(unittest.TestCase):
    def setUp(self):
        self.frappe=MagicMock()
        self.cache=FakeCache()
        self.frappe.cache.return_value=self.cache
        self.frappe.db.exists.return_value=False
        self.patch=patch.dict('sys.modules',{'frappe':self.frappe})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_one_of_concurrent_ingress_deliveries_wins(self):
        def enter(_):
            try:
                return guard.duplicate_or_claim_inbound('same-id')
            except guard.InboundBusy:
                return 'retry'
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(enter,range(20)))
        self.assertEqual(results.count(False),1)
        self.assertEqual(results.count('retry'),19)

    def test_committed_retry_is_acknowledged_without_processing(self):
        self.frappe.db.exists.return_value=True
        self.assertTrue(guard.duplicate_or_claim_inbound('same-id'))
        self.assertEqual(self.cache.values,{})

    def test_missing_id_is_not_processed(self):
        self.assertTrue(guard.duplicate_or_claim_inbound(''))

    def test_legacy_gateway_identity_gets_a_unique_internal_id(self):
        payload = {"number": "923001234567", "message": "company overview"}
        first = guard.custom_message_id(payload)
        self.assertTrue(first.startswith("custom_"))
        self.assertNotEqual(first, guard.custom_message_id(payload))

    def test_top_level_and_nested_provider_ids_are_preserved(self):
        for payload in [{'message_id':'M1'},{'id':'M1'},{'messageId':'M1'},{'key':{'id':'M1'}}]:
            self.assertEqual(guard.custom_message_id(payload),'M1')

    def test_timestamp_fallback_is_stable_across_retries(self):
        payload={'number':'923001234567','message':'company overview','timestamp':1793610000}
        self.assertEqual(guard.custom_message_id(payload),guard.custom_message_id(dict(payload)))
        self.assertNotEqual(guard.custom_message_id(payload),guard.custom_message_id(dict(payload,timestamp=1793610001)))

    def test_repeated_question_with_new_provider_id_is_legitimate(self):
        self.assertFalse(guard.duplicate_or_claim_inbound('M1'))
        self.assertFalse(guard.duplicate_or_claim_inbound('M2'))

    def test_boolean_and_nested_outgoing_flags(self):
        for payload in [{'fromMe':True},{'from_me':'true'},{'key':{'fromMe':True}},{'is_echo':1}]:
            self.assertTrue(guard.is_outgoing(payload))
        for payload in [{'fromMe':'false'},{'fromMe':False},{'from_me':'0'},{}]:
            self.assertFalse(guard.is_outgoing(payload))

    def test_atomic_worker_fallback_allows_only_one_job(self):
        self.frappe.get_meta.return_value.has_field.return_value=False
        with ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(lambda _:guard.claim_worker('M1','L1'),range(20)))
        self.assertEqual(sum(result),1)

    def test_durable_worker_claim_survives_cache_loss(self):
        self.frappe.get_meta.return_value.has_field.return_value=True
        row=SimpleNamespace(meta_message_id='M1',direction='Inbound',processing_state=None)
        db_lock=Lock()
        self.frappe.db.sql.side_effect=lambda *a,**k:db_lock.acquire()
        self.frappe.db.commit.side_effect=lambda:db_lock.release()
        self.frappe.db.get_value.side_effect=lambda *a,**k:row
        self.frappe.db.set_value.side_effect=lambda dt,name,field,value,**k:setattr(row,field,value)
        with ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(lambda _:guard.claim_worker('M1','L1'),range(20)))
        self.assertEqual(sum(result),1)
        self.cache.values.clear()
        self.assertFalse(guard.claim_worker('M1','L1'))

    def test_inflight_or_uncertain_send_is_never_replayed(self):
        self.frappe.get_meta.return_value.has_field.return_value=True
        for state in ['Claimed','Sending','Sent','Failed','Skipped']:
            self.frappe.db.get_value.return_value=SimpleNamespace(meta_message_id='M1',direction='Inbound',processing_state=state)
            self.assertFalse(guard.claim_worker('M1','L1'),state)

    def test_mismatched_worker_log_is_rejected(self):
        self.frappe.get_meta.return_value.has_field.return_value=True
        self.frappe.db.get_value.return_value=SimpleNamespace(meta_message_id='M2',direction='Inbound',processing_state=None)
        with self.assertRaises(ValueError):
            guard.claim_worker('M1','L1')


class TestGatewayParser(unittest.TestCase):
    def setUp(self):
        self.frappe=MagicMock()
        self.frappe.get_all.return_value=[]
        self.frappe.db.get_single_value.return_value=''
        self.frappe.cache.return_value=FakeCache()
        self.patch=patch.dict('sys.modules',{'frappe':self.frappe})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path=Path(__file__).parents[1]/'whatsapp'/'payload_parser.py'
        spec=importlib.util.spec_from_file_location('isolated_gateway_parser',path)
        self.parser=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.parser)

    def payload(self,**kwargs):
        return dict(number='923001234567',message='Tell me about MicroMerger',message_id='M1',**kwargs)

    def test_new_ai_disclaimer_echo_does_not_reenter_conversation(self):
        payload=self.payload()
        payload['message']='Company overview.\n\n🤖 This response was generated by AI.\nWhat would you like to know?'
        self.assertIsNone(self.parser.parse_webhook_payload(payload))

    def test_generic_closing_echo_is_ignored(self):
        payload=self.payload()
        payload['message']='Type another message if you need anything else, or type menu to return to the main menu.'
        self.assertIsNone(self.parser.parse_webhook_payload(payload))

    def test_nested_outbound_echo_is_ignored(self):
        self.assertIsNone(self.parser.parse_webhook_payload(self.payload(key={'fromMe':True})))

    def test_string_false_flag_does_not_drop_real_user_message(self):
        result=self.parser.parse_webhook_payload(self.payload(fromMe='false'))
        self.assertEqual(result['message_id'],'M1')

    def test_previous_baileys_payload_is_accepted_without_sender_changes(self):
        payload = dict(number='923001234567', message='AOA',
                       sender_name='Test User', receiver_name='MicroMerger',
                       receiver='923184221489', receiver_number='923184221489',
                       session_id='administrator', username='administrator',
                       domain='192.168.10.43', erp_url='http://192.168.10.43',
                       media_base64='', mime_type='')
        first = self.parser.parse_webhook_payload(payload)
        second = self.parser.parse_webhook_payload(payload)
        self.assertEqual(first['text'], 'AOA')
        self.assertEqual(first['sender_name'], 'Test User')
        self.assertEqual(first['receiver'], payload['receiver'])
        self.assertTrue(first['message_id'].startswith('custom_'))
        self.assertNotEqual(first['message_id'], second['message_id'])

    def test_provider_retries_retain_the_same_id(self):
        first=self.parser.parse_webhook_payload(self.payload())
        second=self.parser.parse_webhook_payload(self.payload())
        self.assertEqual(first['message_id'],second['message_id'])


if __name__=='__main__':
    unittest.main()
