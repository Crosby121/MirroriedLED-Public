"""Recovery patching preserves the paid test and refuses unrelated edits or keys."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import subprocess
import sqlite3
import unittest
from unittest.mock import patch
import test_sandbox_payment_verify as verification
from test_customer_portal_backend import PHP
ROOT=verification.activation.ROOT
SCRIPT=ROOT/'deploy/hostinger/update-sandbox-recovery.py'

@unittest.skipUnless(PHP,'PHP required')
class RecoveryUpdateTests(unittest.TestCase):
    def setUp(self):
        self.v=verification.PaymentVerifyTests();self.v.setUp();self.addCleanup(self.v.doCleanups)
        self.a=self.v.a;self.web=self.v.web;self.private=self.a.q.private
        spec=importlib.util.spec_from_file_location('recovery_update',SCRIPT);self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.folder=Path(tempfile.mkdtemp());self.addCleanup(__import__('shutil').rmtree,self.folder)
        for name in self.m.FILES:
            target=self.folder/Path(name).name;target.write_bytes((ROOT/name).read_bytes())
        order=self.v.ids[0];self.data={'id':self.v.ids[1],'livemode':False,'status':'complete','payment_status':'paid','currency':'usd','amount_subtotal':100,'amount_total':109,'client_reference_id':order,'metadata':{'order_id':order},'total_details':{'amount_tax':9,'amount_shipping':0},'line_items':{'data':[{'quantity':1,'amount_subtotal':100}]},'payment_intent':{'id':self.v.ids[3],'status':'succeeded','livemode':False,'amount_received':109,'metadata':{'order_id':order}}}
        self.calls=[]
        owner=self
        class Response(io.BytesIO):status=200
        class Client:
            def open(self,request,timeout):owner.calls.append(request);return Response(json.dumps(owner.data).encode())
        self.client=Client()
        self.original={name:(self.web/'MLED_checkout_TEST'/name).read_bytes() for name in self.m.FILES}

    def run_update(self):return self.m.patch(self.web,self.folder,'c'*40,'b'*40,self.a.q.fingerprint,client=self.client)

    def test_patch_preflights_key_and_preserves_paid_records_and_configuration(self):
        config=(self.private/'config.php').read_bytes()
        self.assertTrue(self.run_update()['restricted_key_expanded_intent_read_verified'])
        self.assertEqual((self.private/'config.php').read_bytes(),config)
        self.assertEqual(self.a.q.query('SELECT state,paid_cents,tax_cents FROM commerce_checkouts'),[('paid',109,9)])
        self.assertEqual(self.a.q.query("SELECT COUNT(*) FROM business_events WHERE kind='PAYMENT_CONFIRMED'"),[(1,)])
        for name,data in self.a.q.sandbox.old.items():self.assertEqual((self.a.q.sandbox.domain/name).read_bytes(),data)
        self.assertIn('expand%5B%5D=payment_intent',self.calls[0].full_url)
        self.run_update()
        self.assertTrue(self.v.run_verify()['canonical_test_payment_recorded'])

    def test_unknown_edit_or_wrong_canonical_intent_prevents_publication(self):
        self.data['payment_intent']='pi_NotExpanded'
        with self.assertRaises(ValueError):self.run_update()
        for name,data in self.original.items():self.assertEqual((self.web/'MLED_checkout_TEST'/name).read_bytes(),data)
        target=self.web/'MLED_checkout_TEST/shop/shop.js';target.write_bytes(self.original['shop/shop.js']+b'\n// unrelated')
        with self.assertRaises(ValueError):self.run_update()
        self.assertTrue(target.read_bytes().endswith(b'// unrelated'))

    def test_live_credentials_are_refused_before_network_or_publication(self):
        p=self.private/'credentials.json';d=json.loads(p.read_text());d['stripe_secret_key']='rk_live_Fixture';p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):self.run_update()
        self.assertEqual(self.calls,[])
        for name,data in self.original.items():self.assertEqual((self.web/'MLED_checkout_TEST'/name).read_bytes(),data)

    def test_unknown_receipt_edit_is_preserved_after_completed_patch(self):
        self.run_update()
        p=self.private/'receipt.json';data=json.loads(p.read_text());data['unrelated_owner_note']='preserve';p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.run_update()
        self.assertEqual(json.loads(p.read_text())['unrelated_owner_note'],'preserve')

    def test_partial_publication_resumes_using_verified_original_backups(self):
        replace=self.m.enable.os.replace
        class Interrupted(BaseException):pass
        def interrupt(src,dst):
            replace(src,dst)
            if Path(dst)==self.web/'MLED_checkout_TEST/customer-portal/backend/commerce.php':raise Interrupted()
        with patch.object(self.m.enable.os,'replace',interrupt):
            with self.assertRaises(Interrupted):self.run_update()
        self.run_update()
        self.assertTrue(self.v.run_verify()['canonical_test_payment_recorded'])

    def test_engraving_backend_and_team_customer_assets_are_patched_together(self):
        result=self.run_update()
        for name in ('customer-portal/backend/business.php','customer-portal/business.js','customer-portal/operations.html','shop/shop.js','shop/index.html'):
            self.assertIn(name,result['hashes'])
        backend=(self.web/'MLED_checkout_TEST/customer-portal/backend/business.php').read_text()
        self.assertIn('X-MLED-Business-Source: '+'c'*40,backend)
        self.assertIn('business-engraving-approve',backend)

    def test_installed_schema_initializes_without_altering_existing_private_records(self):
        self.run_update()
        with sqlite3.connect(self.a.q.dbpath) as db:
            db.execute('DROP TABLE IF EXISTS business_engraving_reviews')
            before=list(db.iterdump())
        config=(self.private/'config.php').read_bytes()
        result=subprocess.run([PHP,str(ROOT/'deploy/hostinger/verify-sandbox-engraving.php'),str(self.web),self.a.q.fingerprint],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['engraving_schema_verified'])
        self.assertNotIn(self.a.q.order['id'],result.stdout)
        with sqlite3.connect(self.a.q.dbpath) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM business_engraving_reviews').fetchone()[0],0)
            db.execute('DROP TABLE business_engraving_reviews')
            self.assertEqual(list(db.iterdump()),before)
        self.assertEqual((self.private/'config.php').read_bytes(),config)

if __name__=='__main__':unittest.main()
