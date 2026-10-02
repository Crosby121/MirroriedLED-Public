"""Exercise real filesystem boundaries without connecting to Hostinger."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/hostinger/staging-release.sh"
ASSETS = ("index.html", "styles.css", "app.js", "repair.js")


class StagingReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.public = self.root / "public_html"
        self.public.mkdir()
        self.stage = self.public / "MLED_v5_TEST"
        self.release_name = ".release-12345-1"
        self.release = self.stage / self.release_name
        for asset in ASSETS:
            (self.public / asset).write_bytes(b"production " + asset.encode())

    def run_script(self, mode, stage=None, release=None):
        return subprocess.run(
            ["bash", str(SCRIPT), mode, str(stage or self.stage), release or self.release_name],
            capture_output=True, text=True,
        )

    def prepare_bundle(self):
        result = self.run_script("prepare")
        self.assertEqual(result.returncode, 0, result.stderr)
        for asset in ASSETS:
            (self.stage / asset).write_bytes(b"previous staging " + asset.encode())
            (self.release / asset).write_bytes(b"new staging " + asset.encode())
        manifest = "".join(
            hashlib.sha256((self.release / asset).read_bytes()).hexdigest() + "  " + asset + "\n"
            for asset in ASSETS
        )
        (self.release / "SHA256SUMS.txt").write_text(manifest)

    def assert_production_unchanged(self):
        for asset in ASSETS:
            self.assertEqual((self.public / asset).read_bytes(), b"production " + asset.encode())

    def assert_previous_staging_unchanged(self):
        for asset in ASSETS:
            self.assertEqual((self.stage / asset).read_bytes(), b"previous staging " + asset.encode())

    def test_staging_release_installs_all_four_assets_without_changing_production(self):
        self.prepare_bundle()
        result = self.run_script("activate")
        self.assertEqual(result.returncode, 0, result.stderr)
        for asset in ASSETS:
            self.assertEqual((self.stage / asset).read_bytes(), b"new staging " + asset.encode())
        self.assertFalse(self.release.exists())
        self.assert_production_unchanged()

    def test_corrupt_upload_changes_no_files(self):
        self.prepare_bundle()
        (self.release / "repair.js").write_bytes(b"corrupted transfer")
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        self.assert_previous_staging_unchanged()
        self.assert_production_unchanged()

    def test_missing_asset_changes_no_files(self):
        self.prepare_bundle()
        (self.release / "repair.js").unlink()
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        self.assert_previous_staging_unchanged()
        self.assert_production_unchanged()

    def test_checksum_manifest_cannot_target_production(self):
        self.prepare_bundle()
        (self.release / "SHA256SUMS.txt").write_text("0" * 64 + "  ../../index.html\n")
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        self.assert_previous_staging_unchanged()
        self.assert_production_unchanged()

    def test_duplicate_checksums_are_rejected(self):
        self.prepare_bundle()
        manifest = self.release / "SHA256SUMS.txt"
        first_line = manifest.read_text().splitlines()[0]
        manifest.write_text((first_line + "\n") * 4)
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        self.assert_previous_staging_unchanged()

    def test_staging_symlink_to_production_is_rejected(self):
        self.stage.symlink_to(self.public, target_is_directory=True)
        self.assertNotEqual(self.run_script("prepare").returncode, 0)
        self.assert_production_unchanged()

    def test_symlinked_parent_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        path = alias / "public_html/MLED_v5_TEST"
        self.assertNotEqual(self.run_script("prepare", stage=path).returncode, 0)
        self.assertFalse(self.stage.exists())
        self.assert_production_unchanged()

    def test_symlinked_release_is_rejected(self):
        self.stage.mkdir()
        self.release.symlink_to(self.public, target_is_directory=True)
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        self.assert_production_unchanged()

    def test_symlinked_destination_is_rejected_before_any_file_moves(self):
        self.prepare_bundle()
        (self.stage / "repair.js").unlink()
        (self.stage / "repair.js").symlink_to(self.public / "repair.js")
        self.assertNotEqual(self.run_script("activate").returncode, 0)
        for asset in ASSETS[:-1]:
            self.assertEqual((self.stage / asset).read_bytes(), b"previous staging " + asset.encode())
        self.assert_production_unchanged()

    def test_existing_release_is_not_reused(self):
        self.prepare_bundle()
        self.assertNotEqual(self.run_script("prepare").returncode, 0)
        self.assert_previous_staging_unchanged()

    def test_invalid_paths_and_release_names_are_rejected(self):
        paths = [str(self.public), "/", "public_html/MLED_v5_TEST",
                 str(self.public / "other"), str(self.public / "../public_html/MLED_v5_TEST"),
                 str(self.public) + "//MLED_v5_TEST", str(self.stage) + "/",
                 "/tmp/.." + str(self.stage), str(self.stage) + ";echo bad"]
        for path in paths:
            with self.subTest(path=path):
                self.assertNotEqual(self.run_script("validate", stage=path).returncode, 0)
        for name in ["../index.html", ".release-tmp", ".release-1-1/../../", ".release-1-1;bad"]:
            with self.subTest(release=name):
                self.assertNotEqual(self.run_script("prepare", release=name).returncode, 0)
        self.assertFalse(self.stage.exists())
        self.assert_production_unchanged()


if __name__ == "__main__":
    unittest.main()
