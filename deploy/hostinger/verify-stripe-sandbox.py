#!/usr/bin/env python3
"""Read-only Stripe key preflight. Never emit credentials or provider records."""
import json
import os
import re
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


urlopen = build_opener(NoRedirect()).open


def main():
    key = os.environ.get('MLED_STRIPE_SANDBOX_KEY', '')
    if not key:
        print(json.dumps({'ok': False, 'error': 'sandbox_secret_unavailable'}))
        return 1
    if not re.fullmatch(r'rk_test_[A-Za-z0-9]+', key):
        print(json.dumps({'ok': False, 'error': 'restricted_sandbox_key_required'}))
        return 1
    request = Request('https://api.stripe.com/v1/checkout/sessions?limit=1', headers={
        'Authorization': 'Bearer ' + key,
        'Stripe-Version': '2026-08-26.dahlia',
        'User-Agent': 'MirroriedLED-sandbox-key-preflight/1',
    }, method='GET')
    try:
        with urlopen(request, timeout=20) as response:
            # The payload can contain personal data. Inspect in memory and discard.
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise ValueError('Oversized response')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get('object') != 'list' or not isinstance(payload.get('data'), list):
            raise ValueError('Unexpected response')
        for session in payload['data']:
            if not isinstance(session, dict) or session.get('livemode') is not False or not re.fullmatch(
                    r'cs_test_[A-Za-z0-9]+', str(session.get('id', ''))):
                raise ValueError('Unexpected session mode')
    except HTTPError as error:
        print(json.dumps({'ok': False, 'error': 'stripe_request_rejected', 'http_status': error.code}))
        return 1
    except Exception:
        # Exception strings, response bodies and request objects must not be logged.
        print(json.dumps({'ok': False, 'error': 'sandbox_preflight_failed'}))
        return 1
    print(json.dumps({'ok': True, 'checkout_read_verified': True,
                      'checkout_write_verified': False, 'website_configured': False,
                      'webhook_verified': False, 'live_activation': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
