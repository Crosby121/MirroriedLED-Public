"""Sandbox checkout activation must preserve records and production configuration."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
import test_sandbox_quote as quotes
from test_customer_portal_backend import PHP

ROOT=quotes.ROOT
SCRIPT=ROOT/'deploy/hostinger/enable-sandbox-checkout.py'

@unittest.skipUnless(PHP,'PHP required')
class SandboxEnableTests(unittest.TestCase):
    def setUp(self):
        self.q=quotes.SandboxQuoteTests();self.q.setUp();self.addCleanup(self.q.doCleanups)
        self.q.sandbox.helper().install_webhook_secret(self.q.sandbox.web, {'stripe_webhook_secret':'whsec_EnableFixture'})
        self.q.run_helper()
        with sqlite3.connect(self.q.dbpath) as db:
            db.execute("UPDATE business_orders SET status='APPROVED',approved_proof_id=proof_id")
        self.config=(self.q.private/'config.php').read_bytes()
        self.target=self.q.sandbox.web/'MLED_checkout_TEST/customer-portal/backend/commerce.php'
        self.before=self.target.read_bytes()
        self.patch=ROOT/'customer-portal/backend/commerce.php'
        self.source='b'*40

    def helper(self):
        self.assertTrue(SCRIPT.is_file(),'Missing scoped sandbox checkout activation helper')
        spec=importlib.util.spec_from_file_location('sandbox_enable',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def activate(self,module=None,**kwargs):
        return (module or self.helper()).activate(self.q.sandbox.web,self.patch,self.source,self.q.fingerprint,
            kwargs.get('tax_confirmed',True),kwargs.get('fake_fulfillment_confirmed',True))

    def test_activation_is_test_only_and_preserves_accounts_approval_and_production(self):
        result=self.activate()
        self.assertIs(result['customer_approval_verified'],True)
        self.assertIs(result['sandbox_checkout_enabled'],True)
        self.assertIs(result['production_files_changed'],False)
        self.assertNotIn(self.q.order['id'],json.dumps(result))
        config=json.loads(subprocess.check_output([PHP,'-r', '$c=require $argv[1];echo json_encode([$c["commerce"]["enabled"],$c["commerce"]["mode"],$c["commerce"]["tax_setup_confirmed"],$c["commerce"]["fulfillment_setup_confirmed"],$c["staff_users"]]);',str(self.q.private/'config.php')],text=True))
        self.assertEqual(config,[True,'test',True,True,[]])
        for name,data in self.q.sandbox.old.items():self.assertEqual((self.q.sandbox.domain/name).read_bytes(),data)
        self.assertEqual(self.q.query('SELECT status,approved_proof_id=proof_id FROM business_orders'),[('APPROVED',1)])
        self.assertEqual(self.q.query('SELECT COUNT(*) FROM commerce_checkouts'),[(0,)])
        receipt=json.loads((self.q.private/'receipt.json').read_text())
        self.assertEqual(receipt['checkout_patch']['source_sha'],self.source)
        self.assertEqual(receipt['public_hashes']['customer-portal/backend/commerce.php'],hashlib.sha256(self.target.read_bytes()).hexdigest())
        self.assertEqual((self.q.private/'commerce-before-checkout.php').read_bytes(),self.before)
        self.activate()

    def test_missing_approval_or_wrong_order_refuses_all_changes(self):
        m=self.helper()
        with sqlite3.connect(self.q.dbpath) as db:db.execute('UPDATE business_orders SET approved_proof_id=NULL')
        with self.assertRaises(ValueError):self.activate(m)
        self.assertEqual((self.q.private/'config.php').read_bytes(),self.config)
        self.assertEqual(self.target.read_bytes(),self.before)
        with self.assertRaises(ValueError):m.activate(self.q.sandbox.web,self.patch,self.source,'f'*64,True,True)

    def test_tax_and_fake_terms_must_be_confirmed(self):
        m=self.helper()
        for tax,terms in [(False,True),(True,False)]:
            with self.assertRaises(ValueError):self.activate(m,tax_confirmed=tax,fake_fulfillment_confirmed=terms)
        self.assertEqual((self.q.private/'config.php').read_bytes(),self.config)

    def test_unknown_backend_changes_are_preserved_and_refused(self):
        m=self.helper();self.target.write_bytes(self.before+b'\n// unreviewed edit')
        with self.assertRaises(ValueError):self.activate(m)
        self.assertEqual(self.target.read_bytes(),self.before+b'\n// unreviewed edit')
        self.assertEqual((self.q.private/'config.php').read_bytes(),self.config)

    def test_live_key_or_missing_signer_is_refused(self):
        m=self.helper();p=self.q.private/'credentials.json';original=json.loads(p.read_text())
        for update in [{'stripe_secret_key':'rk_live_Fixture'}, {'stripe_webhook_secret':''}]:
            p.write_text(json.dumps({**original,**update}))
            with self.assertRaises(ValueError):self.activate(m)
        self.assertEqual(self.target.read_bytes(),self.before)

    def test_backup_is_atomically_published(self):
        m=self.helper()
        def partial(destination, data):
            destination.write_bytes(data[:10])
            raise OSError('interrupted legacy copy')
        m.sandbox.exclusive=partial
        # Backup must use atomic publication rather than leave a partial final file.
        self.activate(m)
        self.assertEqual((self.q.private/'commerce-before-checkout.php').read_bytes(), self.before)

    def test_interruption_after_backend_publication_can_resume(self):
        self.helper()
        code="""import importlib.util,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('interrupted_enable',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
replace=m.os.replace
wanted=Path(sys.argv[2])/'MLED_checkout_TEST/customer-portal/backend/commerce.php'
def interrupt(src,dst):
    replace(src,dst)
    if Path(dst)==wanted:os._exit(23)
m.os.replace=interrupt
m.activate(Path(sys.argv[2]),Path(sys.argv[3]),'b'*40,sys.argv[4],True,True)
"""
        result=subprocess.run([sys.executable,'-c',code,str(SCRIPT),str(self.q.sandbox.web),str(self.patch),self.q.fingerprint],capture_output=True)
        self.assertEqual(result.returncode,23)
        self.assertEqual((self.q.private/'config.php').read_bytes(),self.config)
        self.activate()

if __name__=='__main__':unittest.main()
