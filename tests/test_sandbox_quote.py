"""Prepare only a user-selected sandbox quote, preserving production and approval."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest
import test_business_backend as business
import test_checkout_sandbox as sandbox_tests
ROOT = sandbox_tests.ROOT
from test_customer_portal_backend import PHP

SCRIPT = ROOT / 'deploy/hostinger/prepare-sandbox-quote.php'

@unittest.skipUnless(PHP, 'PHP is required')
class SandboxQuoteTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = sandbox_tests.CheckoutSandboxTests()
        self.sandbox.setUp()
        self.addCleanup(self.sandbox.doCleanups)
        self.sandbox.install(self.sandbox.helper())
        self.h = business.BusinessTests()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.order = self.h.post(self.h.customer, 'business-request', {'items':[{'product':'Custom Infinity Mirror','size':'12×12','quantity':1,'artwork':'Sandbox artwork','artworkSource':'upload'}]})['order']
        self.h.upload(self.h.customer, self.order, 'artwork')
        self.h.post(self.h.customer, 'commerce-address', {'orderId':self.order['id'],'address':{'name':'Test Customer','line1':'100 Test Way','line2':'','city':'West Covina','state':'CA','postalCode':'91790','country':'US'}})
        self.private = self.sandbox.domain / 'mirroriedled-private/checkout-sandbox'
        self.dbpath = self.private / 'storage/portal.sqlite'
        with sqlite3.connect(self.h.server.storage / 'portal.sqlite') as source, sqlite3.connect(self.dbpath) as target:
            source.backup(target)
        self.dbpath.chmod(0o600)
        shutil.copytree(self.h.server.storage / 'business-files', self.private / 'storage/business-files')
        self.fingerprint = hashlib.sha256(self.order['id'].encode()).hexdigest()
        self.public = {str(p):p.read_bytes() for p in self.sandbox.web.rglob('*') if p.is_file()}
        self.config = (self.private / 'config.php').read_bytes()

    def run_helper(self, fingerprint=None, expected=0):
        result = subprocess.run([PHP, str(SCRIPT), str(self.sandbox.web), fingerprint or self.fingerprint], capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def query(self, sql):
        with sqlite3.connect(self.dbpath) as db:
            return db.execute(sql).fetchall()

    def test_prepares_one_dollar_proof_and_offer_without_approving_or_enabling_payments(self):
        result = self.run_helper()
        report = json.loads(result.stdout)
        self.assertEqual(report['product_cents'], 100)
        self.assertEqual(report['shipping_cents'], 0)
        self.assertIs(report['customer_approval_required'], True)
        self.assertIs(report['payments_enabled'], False)
        self.assertNotIn(self.order['id'], result.stdout)
        self.assertNotIn('Test Customer', result.stdout)
        self.assertNotIn('100 Test Way', result.stdout)
        self.assertEqual(self.query('SELECT status, quote_cents, approved_proof_id FROM business_orders'), [('QUOTED',100,None)])
        summary = self.query('SELECT summary FROM business_proofs')[0][0]
        self.assertIn('SANDBOX', summary)
        self.assertIn('No fabrication or shipping', summary)
        self.assertEqual(len(self.query('SELECT * FROM commerce_offers')), 1)
        self.assertEqual(self.config, (self.private / 'config.php').read_bytes())
        self.assertEqual(self.public, {str(p):p.read_bytes() for p in self.sandbox.web.rglob('*') if p.is_file()})
        for name, data in self.sandbox.old.items():
            self.assertEqual((self.sandbox.domain/name).read_bytes(), data)

    def test_retry_does_not_duplicate_proof_offer_or_reset_customer_approval(self):
        self.run_helper()
        before = self.query('SELECT revision,proof_id FROM business_orders')
        with sqlite3.connect(self.dbpath) as db:
            db.execute("UPDATE business_orders SET status='APPROVED', approved_proof_id=proof_id")
        self.run_helper()
        self.assertEqual(before, self.query('SELECT revision,proof_id FROM business_orders'))
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('APPROVED',)])
        self.assertEqual(len(self.query('SELECT * FROM business_proofs')), 1)
        self.assertEqual(len(self.query('SELECT * FROM commerce_offer_history')), 1)

    def test_wrong_order_fingerprint_never_changes_any_order(self):
        self.run_helper('f'*64, expected=1)
        self.assertEqual(self.query('SELECT status,proof_id FROM business_orders'), [('REQUESTED',None)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM business_proofs'), [(0,)])

    def test_active_or_live_configuration_is_refused(self):
        config = self.private/'config.php'
        for old, new in [(b"'enabled' => false", b"'enabled' => true"),(b"'mode' => 'test'", b"'mode' => 'live'")]:
            config.write_bytes(self.config.replace(old,new))
            self.run_helper(expected=1)
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('REQUESTED',)])

    def test_missing_delivery_is_refused_before_quote(self):
        with sqlite3.connect(self.dbpath) as db:
            db.execute('DELETE FROM commerce_addresses')
        self.run_helper(expected=1)
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('REQUESTED',)])

    def test_symlinked_artwork_is_refused_and_original_is_preserved(self):
        name = self.query('SELECT filename FROM business_files')[0][0]
        art = self.private / 'storage/business-files' / name
        original = art.read_bytes()
        other = self.private / 'original-artwork'
        art.rename(other)
        art.symlink_to(other)
        self.run_helper(expected=1)
        self.assertEqual(other.read_bytes(), original)
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('REQUESTED',)])

    def test_other_order_is_preserved(self):
        with sqlite3.connect(self.dbpath) as db:
            row = db.execute('SELECT * FROM business_orders').fetchone()
            other = ('MLED-'+'f'*20, *row[1:])
            db.execute('INSERT INTO business_orders VALUES('+','.join('?' for _ in other)+')', other)
        self.run_helper()
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute('SELECT * FROM business_orders WHERE id=?',(other[0],)).fetchone(),other)

    def test_interrupted_proof_copy_does_not_permanently_block_retry(self):
        code = SCRIPT.read_text().replace('stream_copy_to_stream($input, $output);', "fwrite($output, 'partial'); exit(23);")
        fixture = self.private / 'interrupted-copy.php'
        fixture.write_text(code)
        first = subprocess.run([PHP,str(fixture),str(self.sandbox.web),self.fingerprint], capture_output=True)
        self.assertEqual(first.returncode,23)
        self.run_helper()
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('QUOTED',)])

    def test_concurrent_retry_creates_only_one_offer(self):
        self.run_helper()
        with sqlite3.connect(self.dbpath) as db:
            db.execute('DELETE FROM commerce_offers')
        fixture = self.private / 'concurrent-quote.php'
        fixture.write_text(SCRIPT.read_text().replace("if ($terms['offer'] === null) {", "usleep(500000); if ($terms['offer'] === null) {"))
        processes = [subprocess.Popen([PHP,str(fixture),str(self.sandbox.web),self.fingerprint],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            output,error=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,output+error)
        self.assertEqual(self.query('SELECT COUNT(*) FROM commerce_offer_history'),[(2,)])

    def test_interruption_after_proof_publication_can_recover(self):
        code = SCRIPT.read_text().replace("} finally { if (isset($temporary)", "exit(23); } finally { if (isset($temporary)")
        fixture = self.private / 'interrupted-publication.php'
        fixture.write_text(code)
        first = subprocess.run([PHP,str(fixture),str(self.sandbox.web),self.fingerprint],capture_output=True)
        self.assertEqual(first.returncode,23)
        self.run_helper()
        self.assertEqual(self.query('SELECT status FROM business_orders'), [('QUOTED',)])

    def test_existing_different_proof_file_is_never_overwritten(self):
        filename = hashlib.sha256(('sandbox-proof-'+self.order['id']).encode()).hexdigest()[:32]+'.asset'
        existing = self.private/'storage/business-files'/filename
        existing.write_bytes(b'Existing unrelated private file')
        existing.chmod(0o600)
        self.run_helper(expected=1)
        self.assertEqual(existing.read_bytes(),b'Existing unrelated private file')

if __name__ == '__main__':
    unittest.main()
