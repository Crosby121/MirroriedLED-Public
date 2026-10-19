"""Private account setup must preserve existing configuration and reject symlinks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'deploy/hostinger/setup-customer-accounts.py'
TEMPLATE = ROOT / 'customer-portal/backend/config.example.php'


class CustomerAccountSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.webroot = self.base / 'public_html'
        self.webroot.mkdir()
        (self.webroot / 'index.html').write_text('Existing website')
        self.private = self.base / 'mirroriedled-private/customer-portal'

    def run_setup(self):
        return subprocess.run([sys.executable, str(SCRIPT), '--webroot', str(self.webroot),
                               '--template', str(TEMPLATE)], capture_output=True, text=True)

    def test_creates_private_configuration_atomically_with_restrictive_permissions(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['created'])
        config = self.private / 'config.php'
        self.assertEqual(config.read_bytes(), TEMPLATE.read_bytes())
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.private / 'storage').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.webroot / 'index.html').read_text(), 'Existing website')
        self.assertNotIn('stripe_secret_key', result.stdout)

    def test_existing_private_data_and_configuration_are_not_replaced(self):
        self.private.mkdir(parents=True, mode=0o700)
        (self.private / 'config.php').write_text('PRIVATE_EXISTING_CONFIG')
        (self.private / 'storage').mkdir(mode=0o700)
        (self.private / 'storage/portal.sqlite').write_bytes(b'PRIVATE_EXISTING_DATA')
        before = {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['created'])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.base.rglob('*') if p.is_file()})
        self.assertNotIn('PRIVATE_EXISTING', result.stdout)

    def test_private_parent_symlink_is_rejected_without_touching_its_target(self):
        target = self.webroot / 'public-escape'
        target.mkdir()
        (self.base / 'mirroriedled-private').symlink_to(target, target_is_directory=True)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertEqual(list(target.iterdir()), [])

    def test_existing_config_symlink_is_rejected(self):
        self.private.mkdir(parents=True, mode=0o700)
        target = self.webroot / 'keep.php'
        target.write_text('KEEP')
        (self.private / 'config.php').symlink_to(target)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertEqual(target.read_text(), 'KEEP')

    def test_storage_symlink_is_rejected_before_publishing_config(self):
        self.private.mkdir(parents=True, mode=0o700)
        (self.private / 'storage').symlink_to(self.webroot, target_is_directory=True)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertFalse((self.private / 'config.php').exists())

    def test_shared_private_parent_cannot_be_writable_by_other_users(self):
        shared = self.base / 'mirroriedled-private'
        shared.mkdir()
        shared.chmod(0o777)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('permissions', result.stderr.lower())
        self.assertFalse(self.private.exists())

    def test_domain_parent_writable_by_others_is_rejected_before_changes(self):
        self.base.chmod(0o777)
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('parent', result.stderr.lower())
        self.assertFalse((self.base / 'mirroriedled-private').exists())

    def test_symlinked_domain_ancestor_is_rejected_before_changes(self):
        alias = self.base / 'domain-link'
        domain = self.base / 'actual-domain'
        domain.mkdir()
        (domain / 'public_html').mkdir()
        alias.symlink_to(domain, target_is_directory=True)
        self.webroot = alias / 'public_html'
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr.lower())
        self.assertFalse((domain / 'mirroriedled-private').exists())
