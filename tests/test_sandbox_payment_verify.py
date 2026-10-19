"""Verify private payment evidence and duplicate processing without exposing records."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import unittest
import test_sandbox_checkout_enable as activation
from test_customer_portal_backend import PHP

SCRIPT = activation.ROOT / 'deploy/hostinger/verify-sandbox-payment.py'

@unittest.skipUnless(PHP, 'PHP required')
class PaymentVerifyTests(unittest.TestCase):
    def setUp(self):
        self.a = activation.SandboxEnableTests(); self.a.setUp(); self.addCleanup(self.a.doCleanups)
        self.a.activate()
        self.web = self.a.q.sandbox.web
        spec = importlib.util.spec_from_file_location('payment_verify', SCRIPT)
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.ids = [self.a.q.order['id'], 'cs_test_CanonicalFixture', 'evt_CanonicalFixture', 'pi_CanonicalFixture']
        self.hashes = [hashlib.sha256(v.encode()).hexdigest() for v in self.ids]
        with sqlite3.connect(self.a.q.dbpath) as db:
            terms = json.loads(db.execute('SELECT terms FROM commerce_offers').fetchone()[0])
            snapshot = {**terms, 'orderId': self.ids[0], 'mode': 'test'}
            db.execute("INSERT INTO commerce_checkouts(order_id,offer_version,attempt,snapshot,provider_id,state,payment_intent,paid_cents,tax_cents,created_at,paid_at) VALUES(?,1,1,?,?,'paid',?,109,9,1,1)", (self.ids[0], json.dumps(snapshot), self.ids[1], self.ids[3]))
            db.execute('UPDATE business_orders SET finance_reference=?', (self.ids[3],))
            uid = db.execute('SELECT user_id FROM business_orders').fetchone()[0]
            db.execute("INSERT INTO business_events(order_id,actor_id,kind,detail,customer_message,created_at) VALUES(?,?,'PAYMENT_CONFIRMED','{}','Test payment',1)", (self.ids[0], uid))
            db.execute('INSERT INTO commerce_webhooks VALUES(?,1)', (self.ids[2],))

    def run_verify(self, **kw):
        return self.m.verify(self.web, self.hashes, **kw)

    def test_audit_is_read_only_and_redacts_customer_and_provider_ids(self):
        with sqlite3.connect(self.a.q.dbpath) as db: before = list(db.iterdump())
        result = self.run_verify()
        self.assertTrue(result['canonical_test_payment_recorded'])
        self.assertTrue(result['actual_provider_event_processed'])
        self.assertFalse(result['known_event_self_signed_replay_verified'])
        with sqlite3.connect(self.a.q.dbpath) as db: self.assertEqual(list(db.iterdump()), before)
        for value in self.ids: self.assertNotIn(value, json.dumps(result))

    def test_missing_actual_event_or_wrong_amount_refuses(self):
        with sqlite3.connect(self.a.q.dbpath) as db: db.execute('DELETE FROM commerce_webhooks')
        with self.assertRaises(ValueError): self.run_verify()
        with sqlite3.connect(self.a.q.dbpath) as db:
            db.execute('INSERT INTO commerce_webhooks VALUES(?,1)', (self.ids[2],))
            db.execute('UPDATE commerce_checkouts SET paid_cents=108')
        with self.assertRaises(ValueError): self.run_verify()

    def test_live_or_released_order_is_refused(self):
        with sqlite3.connect(self.a.q.dbpath) as db: db.execute("UPDATE business_orders SET status='RELEASED'")
        with self.assertRaises(ValueError): self.run_verify()
        with sqlite3.connect(self.a.q.dbpath) as db:
            db.execute("UPDATE business_orders SET status='APPROVED'")
            snapshot = json.loads(db.execute('SELECT snapshot FROM commerce_checkouts').fetchone()[0]);snapshot['mode']='live'
            db.execute('UPDATE commerce_checkouts SET snapshot=?', (json.dumps(snapshot),))
        with self.assertRaises(ValueError): self.run_verify()

    def test_duplicate_replay_uses_existing_event_and_keeps_single_confirmation(self):
        calls=[]
        class Response(io.BytesIO): status=200
        class Client:
            def open(self, request, timeout):
                calls.append(request)
                return Response(b'{"ok":true}')
        self.assertTrue(self.run_verify(replay=True, client=Client())['known_event_self_signed_replay_verified'])
        self.assertEqual(len(calls),2)
        for call in calls:
            self.assertEqual(json.loads(call.data)['id'],self.ids[2])
            self.assertTrue(call.full_url.startswith('https://mirroriedled.com/MLED_checkout_TEST/'))
        self.assertEqual(self.a.q.query("SELECT COUNT(*) FROM business_events WHERE kind='PAYMENT_CONFIRMED'"),[(1,)])

    def test_replay_cannot_bypass_missing_canonical_confirmation(self):
        with sqlite3.connect(self.a.q.dbpath) as db: db.execute("DELETE FROM business_events WHERE kind='PAYMENT_CONFIRMED'")
        with self.assertRaises(ValueError): self.run_verify(replay=True,client=object())

if __name__=='__main__':unittest.main()
