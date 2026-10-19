"""Credential preflight must never disclose Stripe responses or secret values."""
import contextlib
import importlib.util
import io
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'deploy/hostinger/verify-stripe-sandbox.py'


class StripeSandboxKeyTests(unittest.TestCase):
    def verifier(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing private sandbox credential preflight')
        spec = importlib.util.spec_from_file_location('stripe_preflight', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_check(self, key, payload=None, error=None):
        module = self.verifier()
        output = io.StringIO()
        response = io.BytesIO(json.dumps(payload or {'object': 'list', 'data': []}).encode())
        with patch.dict('os.environ', {'MLED_STRIPE_SANDBOX_KEY': key}, clear=True), \
                patch.object(module, 'urlopen', side_effect=error, return_value=response) as request, \
                contextlib.redirect_stdout(output):
            result = module.main()
        return result, output.getvalue(), request

    def test_missing_or_non_sandbox_key_never_reaches_network(self):
        for key in ['', 'sk_test_fixture', 'rk_live_fixture', 'pk_test_fixture', 'rk_test_a\nX']:
            with self.subTest(key=key):
                code, output, request = self.run_check(key)
                self.assertNotEqual(code, 0)
                request.assert_not_called()
                if key:
                    self.assertNotIn(key, output)

    def test_read_only_request_and_minimal_success_report(self):
        key = 'rk_test_PrivateFixture123'
        payload = {'object': 'list', 'data': [{'id': 'cs_test_PrivateSession', 'livemode': False,
                   'customer_email': 'private@example.invalid'}]}
        code, output, request = self.run_check(key, payload)
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertTrue(report['checkout_read_verified'])
        for field in ['checkout_write_verified', 'website_configured', 'webhook_verified', 'live_activation']:
            self.assertIs(report[field], False)
        self.assertNotIn(key, output)
        self.assertNotIn('PrivateSession', output)
        self.assertNotIn('private@example.invalid', output)
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, 'https://api.stripe.com/v1/checkout/sessions?limit=1')
        self.assertEqual(sent.get_method(), 'GET')
        self.assertEqual(sent.get_header('Authorization'), 'Bearer ' + key)
        self.assertEqual(request.call_args.kwargs['timeout'], 20)

    def test_live_or_malformed_session_data_fails_closed(self):
        for payload in [{'object': 'list', 'data': [{'id': 'cs_live_Secret', 'livemode': True}]},
                        {'object': 'list', 'data': [{'id': 'cs_test_Secret'}]},
                        {'object': 'error', 'data': []}, {'object': 'list', 'data': 'private'}]:
            with self.subTest(payload=payload):
                code, output, _ = self.run_check('rk_test_Fixture123', payload)
                self.assertNotEqual(code, 0)
                self.assertNotIn('Secret', output)

    def test_provider_errors_are_redacted(self):
        for status in [301, 401, 403, 429, 500]:
            error = HTTPError('https://api.stripe.com/private', status, 'SECRET response', {},
                              io.BytesIO(b'{"error":"PRIVATE customer and key"}'))
            code, output, _ = self.run_check('rk_test_PrivateFixture123', error=error)
            self.assertNotEqual(code, 0)
            self.assertEqual(json.loads(output)['http_status'], status)
            self.assertNotIn('SECRET', output)
            self.assertNotIn('PRIVATE', output)

    def test_unexpected_network_exception_is_redacted(self):
        code, output, _ = self.run_check('rk_test_Fixture123', error=RuntimeError('PRIVATE key data'))
        self.assertNotEqual(code, 0)
        self.assertNotIn('PRIVATE', output)

    def test_redirect_is_not_followed(self):
        module = self.verifier()
        visited = []

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                visited.append(self.path)
                self.send_response(302)
                self.send_header('Location', '/must-not-receive-authorization')
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Redirect)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with self.assertRaises(HTTPError) as caught:
                module.urlopen('http://127.0.0.1:' + str(server.server_port) + '/', timeout=2)
            self.assertEqual(caught.exception.code, 302)
            self.assertEqual(visited, ['/'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
