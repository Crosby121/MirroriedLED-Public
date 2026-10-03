"""Verify the complete storefront can deploy and roll back in an isolated webroot."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
ASSETS = ("index.html", "styles.css", "app.js", "repair.js")


class ProductionReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.public = self.root / "public_html"
        self.public.mkdir()
        self.package = self.root / "package"
        self.package.mkdir()
        self.backups = self.root / "backups"
        self.helpers = self.root / "helpers"
        shutil.copytree(SOURCE / "deploy/hostinger", self.helpers)
        for helper in self.helpers.glob("*.sh"):
            helper.chmod(0o700)
        self.previous = {}
        for asset in ASSETS:
            content = ("previous " + asset).encode()
            self.previous[asset] = content
            (self.public / asset).write_bytes(content)
            shutil.copyfile(SOURCE / asset, self.package / asset)
        (self.public / "api").mkdir()
        (self.public / "api/keep.txt").write_text("existing service")
        # HTTP verification is isolated from the real website.
        self.bin = self.root / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do\n'
                        '  if [ "$1" = "-o" ]; then shift; printf "Mirroried LED" > "$1"; fi\n'
                        '  shift\ndone\nprintf "200"\n')
        curl.chmod(0o700)
        self.env = dict(os.environ, PUBLIC_HTML=str(self.public),
                        BACKUP_ROOT=str(self.backups),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        self.write_checksums()

    def write_checksums(self):
        manifest = "".join(hashlib.sha256((self.package / asset).read_bytes()).hexdigest()
                           + "  " + asset + "\n" for asset in ASSETS)
        (self.package / "SHA256SUMS.txt").write_text(manifest)

    def run_helper(self, name, arg):
        return subprocess.run(["bash", str(self.helpers / name), str(arg)],
                              env=self.env, text=True, capture_output=True)

    def deploy(self):
        result = self.run_helper("deploy-storefront.sh", self.package)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for asset in ASSETS:
            self.assertEqual((self.public / asset).read_bytes(), (self.package / asset).read_bytes())
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")
        return next(self.backups.glob("storefront-*"))

    def assert_unchanged(self):
        for asset in ASSETS:
            self.assertEqual((self.public / asset).read_bytes(), self.previous[asset])
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")

    def test_all_four_assets_are_backed_up_deployed_and_restored(self):
        backup = self.deploy()
        with tarfile.open(next(self.backups.glob("public_html-full-*.tar.gz"))) as archive:
            for asset in ASSETS:
                self.assertEqual(archive.extractfile("public_html/" + asset).read(), self.previous[asset])
            self.assertEqual(archive.extractfile("public_html/api/keep.txt").read(), b"existing service")
        result = self.run_helper("rollback-storefront.sh", backup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_unchanged()

    def test_missing_repair_asset_changes_no_live_files(self):
        (self.package / "repair.js").unlink()
        self.assertNotEqual(self.run_helper("deploy-storefront.sh", self.package).returncode, 0)
        self.assert_unchanged()

    def test_invalid_repair_javascript_changes_no_live_files(self):
        (self.package / "repair.js").write_text("function {")
        self.write_checksums()
        self.assertNotEqual(self.run_helper("deploy-storefront.sh", self.package).returncode, 0)
        self.assert_unchanged()

    def test_rollback_restores_original_absence_of_repair_asset(self):
        (self.public / "repair.js").unlink()
        backup = self.deploy()
        result = self.run_helper("rollback-storefront.sh", backup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.public / "repair.js").exists())
        for asset in ASSETS[:-1]:
            self.assertEqual((self.public / asset).read_bytes(), self.previous[asset])
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")


if __name__ == "__main__":
    unittest.main()
