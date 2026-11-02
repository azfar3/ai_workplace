"""Atomic inbound/worker claims. Never automatically replay an uncertain send."""
from __future__ import annotations

import hashlib
import json


class MissingMessageIdentity(ValueError):
    """A gateway omitted the stable ID/timestamp needed to detect redelivery."""


class InboundBusy(Exception):
    """Another delivery owns ingress but has not committed its inbound log yet."""


def _frappe():
    import frappe
    return frappe


def _key(cache, kind, value):
    digest = hashlib.sha256(str(value).encode()).hexdigest()
    return cache.make_key(f'ai_workplace:once:{kind}:{digest}')


def claim_once(kind, value, seconds=600):
    cache = _frappe().cache()
    # Redis SET NX EX is one atomic operation, unlike get-then-set.
    return bool(cache.set(_key(cache,kind,value), '1', nx=True, ex=seconds))


def custom_message_id(payload):
    """Use the gateway's real WhatsApp ID, including common nested formats."""
    key = payload.get('key') if isinstance(payload.get('key'),dict) else {}
    supplied = payload.get('message_id') or payload.get('id') or payload.get('messageId') or key.get('id')
    if supplied:
        return str(supplied)
    fingerprint = {k:payload.get(k) for k in (
        'number','message','receiver','receiver_number','session_id','session_name',
        'receiver_name','username','timestamp','filename','mime_type','latitude','longitude',
    ) if payload.get(k) is not None}
    # A timestamp distinguishes intentionally repeated, identical user messages.
    encoded = json.dumps(fingerprint,sort_keys=True,default=str,separators=(',',':'))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    if payload.get('timestamp') not in (None, '', 0, '0'):
        return 'custom_'+digest
    raise MissingMessageIdentity(
        'Custom WhatsApp gateway must forward the original message_id (or key.id) '
        'or original stable message timestamp. ID-less events are not processed.'
    )


def is_outgoing(payload):
    def enabled(value):
        return value is True or value == 1 or isinstance(value,str) and value.strip().lower() in {'true','1','yes'}
    key = payload.get('key') if isinstance(payload.get('key'),dict) else {}
    return any(enabled(value) for value in (payload.get('fromMe'),payload.get('from_me'),payload.get('is_echo'),key.get('fromMe')))


def claim_worker(message_id, log_name):
    frappe = _frappe()
    meta = frappe.get_meta('WhatsApp Message Log')
    if not meta.has_field('processing_state'):
        # Rolling-deployment fallback. No expiry-based automatic job retry.
        return claim_once('worker',message_id,7*24*3600)
    frappe.db.sql('SELECT name FROM `tabWhatsApp Message Log` WHERE name=%s FOR UPDATE',(log_name,))
    log = frappe.db.get_value('WhatsApp Message Log',log_name,['meta_message_id','direction','processing_state'],as_dict=True)
    if not log or log.meta_message_id != message_id or log.direction != 'Inbound':
        frappe.db.commit()
        raise ValueError('Inbound log does not match the queued message.')
    if log.processing_state:
        frappe.db.commit()
        return False
    frappe.db.set_value('WhatsApp Message Log',log_name,'processing_state','Claimed',update_modified=False)
    # Durable before tools/LLM/network; a job replay cannot repeat a write or send.
    frappe.db.commit()
    return True


def set_worker_state(log_name,state):
    frappe = _frappe()
    if frappe.get_meta('WhatsApp Message Log').has_field('processing_state'):
        frappe.db.set_value('WhatsApp Message Log',log_name,'processing_state',state,update_modified=False)
        frappe.db.commit()


def duplicate_or_claim_inbound(message_id):
    frappe = _frappe()
    if not message_id:
        return True
    if frappe.db.exists('WhatsApp Message Log', {'meta_message_id': message_id, 'direction': 'Inbound'}):
        return True
    if not claim_once('ingress',message_id):
        raise InboundBusy('Inbound message is still being accepted.')
    return False
