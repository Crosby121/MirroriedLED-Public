"""Exercise full-release installation, backups and rollback on an isolated filesystem."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("website_release", SOURCE / "deploy/hostinger/website-release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class WebsiteReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.public = self.parent / "public_html"
        self.public.mkdir()
        (self.public / "index.html").write_text("Existing Mirroried LED homepage")
        (self.public / "app.js").write_text("previous javascript")
        (self.public / "wled-bridge").mkdir()
        (self.public / "wled-bridge/keep.php").write_text("existing bridge")
        self.private = self.parent / "mirroriedled-private"
        self.private.mkdir()
        (self.private / "portal.sqlite").write_bytes(b"private customer records")
        self.before = self.snapshot()
        self.archive = self.parent / "website.zip"
        self.receipt = self.parent / "receipt.json"
        self.release_id = "a" * 40
        self.homepage_sha = release.digest(self.public / "index.html")
        self.package()

    def package(self, corrupt=None, extra=None):
        manifest = ""
        with zipfile.ZipFile(self.archive, "w") as bundle:
            for name in release.PUBLIC_FILES:
                data = (SOURCE / name).read_bytes()
                manifest += hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                bundle.writestr(name, b"corrupt" if name == corrupt else data)
            bundle.writestr(release.MANIFEST, manifest)
            if extra:
                bundle.writestr(extra, "unexpected file")

    def snapshot(self):
        return {str(path.relative_to(self.parent)): path.read_bytes()
                for directory in (self.public, self.private) for path in directory.rglob("*") if path.is_file()}

    def install(self):
        return release.install(self.public, self.archive, self.release_id, self.homepage_sha, self.receipt)

    def test_full_release_preserves_services_private_data_and_original_absence(self):
        backup = self.install()
        for name in release.PUBLIC_FILES:
            self.assertEqual((self.public / name).read_bytes(), (SOURCE / name).read_bytes())
        self.assertEqual((self.private / "portal.sqlite").read_bytes(), b"private customer records")
        self.assertEqual((self.public / "wled-bridge/keep.php").read_text(), "existing bridge")
        with tarfile.open(backup / "public_html.tar.gz") as archive:
            self.assertEqual(archive.extractfile("public_html/index.html").read(), self.before["public_html/index.html"])
            self.assertEqual(archive.extractfile("public_html/wled-bridge/keep.php").read(), b"existing bridge")
        self.assertEqual((backup / "public_html.tar.gz").stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads((backup / "receipt.json").read_text()), json.loads(self.receipt.read_text()))
        release.restore(self.public, backup)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.public / "customer-portal").exists())
        self.assertFalse((self.public / "stadiums").exists())
        self.assertFalse((self.public / "products").exists())

    def test_bad_checksum_changes_no_live_files(self):
        self.package(corrupt="customer-portal/backend/business.php")
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.install()
        self.assertEqual(self.snapshot(), self.before)

    def test_extra_config_or_traversal_is_rejected_before_changes(self):
        for extra in ("customer-portal/backend/config.php", "../outside.php"):
            with self.subTest(extra=extra):
                self.package(extra=extra)
                with self.assertRaisesRegex(ValueError, "allowlist"):
                    self.install()
                self.assertEqual(self.snapshot(), self.before)

    def test_wrong_host_homepage_changes_no_live_files(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            release.install(self.public, self.archive, self.release_id, "0" * 64, self.receipt)
        self.assertEqual(self.snapshot(), self.before)

    def test_sponsor_vps_and_staging_paths_cannot_be_production_targets(self):
        for path in ("/var/www/sponsors.mirroriedled.com", "/home/u1/domains/sponsors.mirroriedled.com/public_html",
                     "/home/u1/domains/mirroriedled.com/public_html/MLED_v5_TEST", "/public_html", "/"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                release.webroot_path(path)

    def test_symlinked_release_destination_is_rejected(self):
        (self.public / "customer-portal").symlink_to(self.private, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.install()
        self.assertEqual((self.private / "portal.sqlite").read_bytes(), b"private customer records")

    def test_failed_install_automatically_restores_already_replaced_files(self):
        real_replace = release.os.replace
        failed = False

        def fail_once(source, target):
            nonlocal failed
            if Path(target) == self.public / "index.html" and not failed:
                failed = True
                raise OSError("simulated filesystem failure")
            return real_replace(source, target)

        with patch.object(release.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.install()
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), self.before)

    def test_corrupt_rollback_backup_changes_no_live_files(self):
        backup = self.install()
        after = self.snapshot()
        (backup / "files/index.html").write_text("corrupt backup")
        with self.assertRaisesRegex(ValueError, "checksum"):
            release.restore(self.public, backup)
        self.assertEqual(self.snapshot(), after)

    def test_rollback_keeps_unrelated_new_portal_files(self):
        backup = self.install()
        (self.public / "customer-portal/keep.txt").write_text("new unrelated file")
        release.restore(self.public, backup)
        self.assertEqual((self.public / "customer-portal/keep.txt").read_text(), "new unrelated file")
        self.assertEqual((self.private / "portal.sqlite").read_bytes(), b"private customer records")


if __name__ == "__main__":
    unittest.main()
