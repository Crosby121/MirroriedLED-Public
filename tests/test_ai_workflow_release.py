"""Verify that connector installation cannot replace the rest of the website."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("connector_release", ROOT / "deploy/hostinger/ai-workflow-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ConnectorReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.webroot = self.root / "mirroriedled.com/public_html"
        self.webroot.mkdir(parents=True)
        (self.webroot / "index.html").write_text("Original live homepage")
        (self.webroot / "customer-data.json").write_text("Unrelated existing private data")
        self.home_sha = hashlib.sha256((self.webroot / "index.html").read_bytes()).hexdigest()
        self.source = self.root / "stage"
        self.source.mkdir()
        for name in ("mcp.php", ".htaccess"):
            (self.source / name).write_bytes((ROOT / "ai-workflow" / name).read_bytes())
        (self.source / "server.php").write_bytes((ROOT / "services/ai-workflow/server.php").read_bytes())
        self.config = self.source / "config.json"
        self.config.write_text(json.dumps({"repository": "Crosby121/MirroriedLED-Public", "branch": "main", "expected_github_account": "Crosby121",
                                           "github_token": "fixture-token-" + "A" * 40, "allowed_origins": ["https://mirroriedled.com"],
                                           "clients": {"copilot": {"application": "GitHub Copilot", "token_sha256": "a" * 64}}}))
        self.receipt = self.source / "receipt.json"

    def install(self, receipt=None, home_sha=None):
        return release.install(self.webroot, self.source, self.config, receipt or self.receipt, "1" * 40, home_sha or self.home_sha)

    def test_install_and_rollback_preserve_website_and_private_configuration(self):
        self.install()
        private = self.webroot.parent / "mirroriedled-private/ai-workflow"
        self.assertEqual((self.webroot / "index.html").read_text(), "Original live homepage")
        self.assertEqual((self.webroot / "customer-data.json").read_text(), "Unrelated existing private data")
        self.assertFalse((self.webroot / "ai-workflow/config.json").exists())
        self.assertEqual((private / "config.json").stat().st_mode & 0o777, 0o600)
        release.rollback(self.webroot, self.receipt)
        self.assertFalse((self.webroot / "ai-workflow/mcp.php").exists())
        self.assertFalse((private / "config.json").exists())
        self.assertEqual(json.loads((private / "managed.json").read_text())["state"], "rolled_back")
        self.install(receipt=self.source / "retry-after-rollback.json")
        self.assertEqual((self.webroot / "index.html").read_text(), "Original live homepage")
        self.assertTrue((private / "config.json").exists())

    def test_wrong_domain_or_homepage_is_rejected_before_modification(self):
        with self.assertRaises(ValueError):
            self.install(home_sha="f" * 64)
        self.assertFalse((self.webroot / "ai-workflow").exists())
        with self.assertRaises(ValueError):
            release.locations(self.root / "sponsors.mirroriedled.com/public_html")

    def test_unowned_existing_endpoint_is_not_overwritten(self):
        public = self.webroot / "ai-workflow"
        public.mkdir()
        (public / "mcp.php").write_text("Existing different service")
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((public / "mcp.php").read_text(), "Existing different service")

    def test_symlinks_and_public_receipts_are_rejected(self):
        with self.assertRaises(ValueError):
            self.install(receipt=self.webroot / "receipt.json")
        (self.webroot / "ai-workflow").symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.install()

    def test_installation_failure_restores_already_changed_files(self):
        original = release.atomic
        def fail_on_config(path, data, mode):
            if Path(path).name == "config.json":
                raise OSError("Fixture installation failure")
            original(path, data, mode)
        with patch.object(release, "atomic", fail_on_config), self.assertRaises(OSError):
            self.install()
        self.assertFalse((self.webroot / "ai-workflow/.htaccess").exists())
        self.assertFalse((self.webroot.parent / "mirroriedled-private/ai-workflow/server.php").exists())
        self.assertEqual((self.webroot / "index.html").read_text(), "Original live homepage")
        self.install(receipt=self.source / "retry-after-failure.json")
        self.assertTrue((self.webroot / "ai-workflow/mcp.php").exists())

    def test_rollback_refuses_to_overwrite_a_later_config_change(self):
        self.install()
        target = self.webroot.parent / "mirroriedled-private/ai-workflow/config.json"
        target.write_text("A later configuration change")
        with self.assertRaises(ValueError):
            release.rollback(self.webroot, self.receipt)
        self.assertEqual(target.read_text(), "A later configuration change")
        self.assertTrue((self.webroot / "ai-workflow/mcp.php").exists())


if __name__ == "__main__":
    unittest.main()
