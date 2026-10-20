"""CLI release guard uses artificial private SQLite records, never customer data."""
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from test_customer_portal_backend import PHP, php_quote

SOURCE=Path(__file__).resolve().parents[1]

@unittest.skipUnless(PHP,'PHP runtime required')
class QuoteReleasePreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.domain=Path(self.temp.name)/'mirroriedled.com';self.root=self.domain/'public_html'
        self.root.mkdir(parents=True)
        self.stage=self.domain/'.mirroriedled-release-123-1';self.stage.mkdir(mode=0o700)
        self.receipt=self.stage/'private-preservation.json';self.release='a'*40
        self.private=self.domain/'mirroriedled-private';self.private.mkdir(mode=0o700)
        for name in ('customer-portal','checkout-sandbox'):
            folder=self.private/name;folder.mkdir(mode=0o700);storage=folder/'storage';storage.mkdir(mode=0o700)
            config="<?php return ['business_enabled'=>true,'premium_enabled'=>false,'commerce'=>['enabled'=>"+('false' if name=='customer-portal' else 'true')+"],'storage_path'=>"+php_quote(str(storage))+"];"
            (folder/'config.php').write_text(config);(folder/'config.php').chmod(0o600)
            with sqlite3.connect(storage/'portal.sqlite') as db:
                db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT)')
                db.execute("INSERT INTO users VALUES(1,'artificial@example.test')")
            (storage/'portal.sqlite').chmod(0o600)
            (storage/'photo.png').write_bytes(b'artificial private artwork');(storage/'photo.png').chmod(0o600)
        self.db=self.private/'customer-portal/storage/portal.sqlite'
    def guard(self,action,expected=0,receipt=None):
        result=subprocess.run([PHP,str(SOURCE/'deploy/hostinger/verify-quote-release.php'),action,str(self.root),str(receipt or self.receipt),self.release],capture_output=True,text=True)
        self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
        self.assertNotIn('artificial@example.test',result.stdout+result.stderr)
        return json.loads(result.stdout) if expected==0 else None
    def test_release_preserves_both_private_stores_and_allows_additive_schema(self):
        self.guard('before')
        with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE new_additive_table(id INTEGER PRIMARY KEY)')
        self.assertTrue(self.guard('after')['private_records_preserved'])
        self.assertEqual(self.receipt.stat().st_mode&0o777,0o600)
    def test_changed_existing_private_row_fails(self):
        self.guard('before')
        with sqlite3.connect(self.db) as db:db.execute("UPDATE users SET email='changed@example.test'")
        self.guard('after',1)
    def test_deleted_private_artwork_fails(self):
        self.guard('before');(self.private/'checkout-sandbox/storage/photo.png').unlink()
        self.guard('after',1)
    def test_enabled_production_payment_stops_before_installation(self):
        config=self.private/'customer-portal/config.php';config.write_text(config.read_text().replace("'enabled'=>false","'enabled'=>true"))
        self.guard('before',1);self.assertFalse(self.receipt.exists())
    def test_public_or_symlinked_receipt_is_rejected(self):
        self.guard('before',1,self.root/'private-preservation.json')
        (self.stage/'linked.json').symlink_to(self.stage/'other.json')
        self.guard('before',1,self.stage/'linked.json')

if __name__=='__main__':unittest.main()
