"""Check that live verification cannot confuse packaging with an installed website."""

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("website_verification", SOURCE / "deploy/hostinger/verify-website.py")
verification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verification)


class WebsiteVerificationTests(unittest.TestCase):
    def response(self, _base, path, _release):
        if path in verification.PUBLIC_ASSETS:
            return 200, (SOURCE / path).read_bytes()
        if path == "":
            return 200, (SOURCE / "index.html").read_bytes()
        if path == "customer-portal/backend/api.php?action=session":
            return 200, json.dumps({"ok": True, "configured": False}).encode()
        if path == "customer-portal/backend/api.php?action=commerce-status":
            return 200, json.dumps({"ok": True, "paymentsAvailable": False, "paymentMode": None}).encode()
        return 403, b""

    def test_unconfigured_portal_is_reported_without_claiming_activation(self):
        with patch.object(verification, "fetch", side_effect=self.response), patch("builtins.print") as output:
            self.assertFalse(verification.verify(SOURCE, "https://mirroriedled.com", "abc123"))
        self.assertTrue(any("private setup remains required" in str(call) for call in output.call_args_list))

    def test_older_root_homepage_fails_even_when_direct_assets_match(self):
        def response(base, path, release):
            return (200, b"Old homepage") if path == "" else self.response(base, path, release)
        with patch.object(verification, "fetch", side_effect=response), self.assertRaisesRegex(ValueError, "homepage"):
            verification.verify(SOURCE, "https://mirroriedled.com", "abc123")

    def test_missing_customer_portal_fails_verification(self):
        def response(base, path, release):
            return (404, b"") if path == "customer-portal/index.html" else self.response(base, path, release)
        with patch.object(verification, "fetch", side_effect=response), self.assertRaisesRegex(ValueError, "differs"):
            verification.verify(SOURCE, "https://mirroriedled.com", "abc123")

    def test_public_internal_file_fails_verification(self):
        def response(base, path, release):
            return (200, b"configuration") if path.endswith("/config.php") else self.response(base, path, release)
        with patch.object(verification, "fetch", side_effect=response), self.assertRaisesRegex(ValueError, "publicly reachable"):
            verification.verify(SOURCE, "https://mirroriedled.com", "abc123")

    def test_php_source_or_broken_api_cannot_count_as_a_successful_deployment(self):
        def response(base, path, release):
            return (200, b"<?php source") if "?action=session" in path else self.response(base, path, release)
        with patch.object(verification, "fetch", side_effect=response), self.assertRaises(json.JSONDecodeError):
            verification.verify(SOURCE, "https://mirroriedled.com", "abc123")

    def test_sponsor_vps_cannot_be_the_verification_url(self):
        with self.assertRaisesRegex(ValueError, "main Mirroried"):
            verification.verify(SOURCE, "https://sponsors.mirroriedled.com", "abc123")

    def test_two_product_launch_cannot_pass_without_live_accounts_and_payments(self):
        with patch.object(verification, "fetch", side_effect=self.response), self.assertRaisesRegex(ValueError, "live merchant"):
            verification.verify(SOURCE, "https://mirroriedled.com", "abc123", require_commerce=True)


if __name__ == "__main__":
    unittest.main()
