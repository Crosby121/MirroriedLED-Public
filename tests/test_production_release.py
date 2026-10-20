"""Verify the complete storefront can deploy and roll back in an isolated webroot."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from threading import Thread
import unittest

SOURCE = Path(__file__).resolve().parents[1]
IMAGES = ("infinity-mirror.webp", "stadium-model.webp", "led-display.webp", "address-sign.webp")
ASSETS = ("index.html", "styles.css", "app.js", "repair.js") + IMAGES


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
            if asset in IMAGES:
                # Deployment treats image bytes as opaque; visual validation is separate.
                (self.package / asset).write_bytes(b"new image " + asset.encode() + b"\x00\xff")
            else:
                shutil.copyfile(SOURCE / asset, self.package / asset)
        (self.public / "api").mkdir()
        (self.public / "api/keep.txt").write_text("existing service")
        (self.public / "customer-photo.webp").write_bytes(b"existing customer image\x00\xff")
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
        self.assertEqual((self.public / "customer-photo.webp").read_bytes(), b"existing customer image\x00\xff")
        return next(self.backups.glob("storefront-*"))

    def assert_unchanged(self):
        for asset in ASSETS:
            self.assertEqual((self.public / asset).read_bytes(), self.previous[asset])
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")
        self.assertEqual((self.public / "customer-photo.webp").read_bytes(), b"existing customer image\x00\xff")

    def test_all_eight_assets_are_backed_up_deployed_and_restored(self):
        backup = self.deploy()
        with tarfile.open(next(self.backups.glob("public_html-full-*.tar.gz"))) as archive:
            for asset in ASSETS:
                self.assertEqual(archive.extractfile("public_html/" + asset).read(), self.previous[asset])
            self.assertEqual(archive.extractfile("public_html/api/keep.txt").read(), b"existing service")
            self.assertEqual(archive.extractfile("public_html/customer-photo.webp").read(), b"existing customer image\x00\xff")
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

    def test_missing_image_changes_no_live_files(self):
        (self.package / "address-sign.webp").unlink()
        self.assertNotEqual(self.run_helper("deploy-storefront.sh", self.package).returncode, 0)
        self.assert_unchanged()

    def test_corrupt_image_checksum_changes_no_live_files(self):
        (self.package / "address-sign.webp").write_bytes(b"corrupted image\x00\xff")
        self.assertNotEqual(self.run_helper("deploy-storefront.sh", self.package).returncode, 0)
        self.assert_unchanged()

    def test_rollback_restores_original_absence_of_repair_asset(self):
        (self.public / "repair.js").unlink()
        backup = self.deploy()
        result = self.run_helper("rollback-storefront.sh", backup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.public / "repair.js").exists())
        for asset in ASSETS:
            if asset == "repair.js":
                continue
            self.assertEqual((self.public / asset).read_bytes(), self.previous[asset])
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")
        self.assertEqual((self.public / "customer-photo.webp").read_bytes(), b"existing customer image\x00\xff")

    def test_rollback_restores_original_absence_of_product_images(self):
        for image in IMAGES:
            (self.public / image).unlink()
        backup = self.deploy()
        self.assertEqual(set((backup / "ABSENT_FILES.txt").read_text().splitlines()), set(IMAGES))
        with tarfile.open(next(self.backups.glob("public_html-full-*.tar.gz"))) as archive:
            for image in IMAGES:
                self.assertNotIn("public_html/" + image, archive.getnames())
        result = self.run_helper("rollback-storefront.sh", backup)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for image in IMAGES:
            self.assertFalse((self.public / image).exists())
        for asset in ASSETS:
            if asset not in IMAGES:
                self.assertEqual((self.public / asset).read_bytes(), self.previous[asset])
        self.assertEqual((self.public / "api/keep.txt").read_text(), "existing service")
        self.assertEqual((self.public / "customer-photo.webp").read_bytes(), b"existing customer image\x00\xff")

    def test_missing_live_image_fails_public_verification(self):
        curl = self.bin / "curl"
        curl.write_text('#!/bin/sh\nurl=""\nout=""\nwhile [ "$#" -gt 0 ]; do\n'
                        '  if [ "$1" = "-o" ]; then shift; out="$1"; fi\n'
                        '  url="$1"\n  shift\ndone\n'
                        'body="Mirroried LED Infinity Mirrors Address signs"\n'
                        'if [ -n "$out" ]; then printf "%s" "$body" > "$out"; else printf "%s" "$body"; fi\n'
                        'case "$url" in\n'
                        '  *address-sign.webp) printf "404" ;;\n'
                        '  *) printf "200" ;;\nesac\n')
        result = self.run_helper("verify-storefront.sh", "")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("address-sign.webp", result.stderr)
        self.assert_unchanged()

    @unittest.skipUnless(shutil.which("curl"), "curl is required to exercise HTTP redirects")
    def test_public_verification_follows_canonical_domain_asset_redirects(self):
        package = self.package

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if not self.path.startswith("/canonical/"):
                    self.send_response(301)
                    self.send_header("Location", "/canonical/" + self.path.lstrip("/"))
                    self.end_headers()
                    return
                asset = self.path.removeprefix("/canonical/") or "index.html"
                body = (package / asset).read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        Thread(target=server.serve_forever, daemon=True).start()
        self.env.update(PATH=os.environ["PATH"], NO_PROXY="127.0.0.1", no_proxy="127.0.0.1",
                        DOMAIN=f"http://127.0.0.1:{server.server_port}",
                        SPONSOR_URL=f"http://127.0.0.1:{server.server_port}/")
        result = self.run_helper("verify-storefront.sh", "")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PUBLIC STOREFRONT VERIFICATION SUCCESS", result.stdout)
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
