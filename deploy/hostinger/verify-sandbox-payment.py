#!/usr/bin/env python3
"""Verify one canonical sandbox payment and optionally replay its already-processed event."""
import argparse
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener

spec = importlib.util.spec_from_file_location('sandbox_enable', Path(__file__).with_name('enable-sandbox-checkout.py'))
enable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enable)


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


def inspect(webroot, order_hash, session_hash, event_hash, intent_hash, total_cents, tax_cents):
    if any(not re.fullmatch(r'[a-f0-9]{64}', value) for value in (order_hash, session_hash, event_hash, intent_hash)):
        raise ValueError('Exact canonical record fingerprints required')
    if total_cents != 109 or tax_cents != 9:
        raise ValueError('Only the authorized one-dollar California test payment is in scope')
    webroot = webroot.absolute()
    if webroot.name != 'public_html' or webroot.parent.name != 'mirroriedled.com':
        raise ValueError('Isolated sandbox required')
    private = webroot.parent / 'mirroriedled-private/checkout-sandbox'
    for path in (webroot.parent, webroot, private.parent):
        enable.safe(path, directory=True)
    enable.safe(private, directory=True, private=True)
    enable.safe(private / 'storage', directory=True, private=True)
    database = private / 'storage/portal.sqlite'
    enable.safe(database, private=True)
    enable.safe(private / 'receipt.json', private=True)
    receipt = json.loads((private / 'receipt.json').read_bytes())
    stage = webroot / 'MLED_checkout_TEST'
    for path in (stage, stage / 'customer-portal', stage / 'customer-portal/backend'):
        enable.safe(path, directory=True)
    api = stage / 'customer-portal/backend/api.php'
    commerce = stage / 'customer-portal/backend/commerce.php'
    enable.safe(api)
    enable.safe(commerce)
    if '/mirroriedled-private/checkout-sandbox/config.php' not in api.read_text() or hashlib.sha256(commerce.read_bytes()).hexdigest() != receipt.get('checkout_patch', {}).get('sha256'):
        raise ValueError('Reviewed isolated checkout source required')
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        orders = [r for r in db.execute('SELECT * FROM business_orders') if fingerprint(r['id']) == order_hash]
        if len(orders) != 1:
            raise ValueError('Selected order not found')
        order = orders[0]
        rows = db.execute('SELECT * FROM commerce_checkouts WHERE order_id=?', (order['id'],)).fetchall()
        if len(rows) != 1:
            raise ValueError('Exactly one checkout expected')
        row = rows[0]
        snapshot = json.loads(row['snapshot'])
        if row['state'] != 'paid' or row['paid_cents'] != total_cents or row['tax_cents'] != tax_cents or not row['paid_at'] or fingerprint(row['provider_id'] or '') != session_hash or fingerprint(row['payment_intent'] or '') != intent_hash:
            raise ValueError('Canonical paid checkout is not recorded')
        if snapshot.get('mode') != 'test' or snapshot.get('productCents') != 100 or snapshot.get('shippingCents') != 0 or snapshot.get('orderId') != order['id'] or snapshot.get('proofId') != order['approved_proof_id']:
            raise ValueError('Approved artificial test snapshot required')
        if order['status'] != 'APPROVED' or order['proof_id'] != order['approved_proof_id'] or order['finance_reference'] != row['payment_intent'] or order['quote_cents'] != 100:
            raise ValueError('Approved unreleased order and matching payment reference required')
        proof = db.execute('SELECT summary FROM business_proofs WHERE id=? AND order_id=?', (order['proof_id'], order['id'])).fetchone()
        if not proof or not proof['summary'].startswith('SANDBOX CHECKOUT TEST ONLY:'):
            raise ValueError('Artificial proof required')
        if db.execute("SELECT COUNT(*) FROM business_events WHERE order_id=? AND kind='PAYMENT_CONFIRMED'", (order['id'],)).fetchone()[0] != 1:
            raise ValueError('Exactly one payment confirmation expected')
        if db.execute("SELECT COUNT(*) FROM business_events WHERE order_id=? AND kind='PAYMENT_REVIEW'", (order['id'],)).fetchone()[0] != 0:
            raise ValueError('Payment review unresolved')
        events = [r['event_id'] for r in db.execute('SELECT event_id FROM commerce_webhooks') if fingerprint(r['event_id']) == event_hash]
        if len(events) != 1:
            raise ValueError('Actual canonical provider event has not been processed')
        return {'event_id': events[0], 'session_id': row['provider_id']}


def verify(webroot, hashes, total_cents=109, tax_cents=9, replay=False, client=None):
    record = inspect(webroot, *hashes, total_cents, tax_cents)
    if replay:
        path = webroot.parent / 'mirroriedled-private/checkout-sandbox/credentials.json'
        enable.safe(path, private=True)
        credentials = json.loads(path.read_bytes())
        secret = credentials.get('stripe_webhook_secret', '')
        if not re.fullmatch(r'whsec_[A-Za-z0-9]+', secret) or not re.fullmatch(r'rk_test_[A-Za-z0-9]+', credentials.get('stripe_secret_key', '')):
            raise ValueError('Installed restricted sandbox credentials required')
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        client = client or build_opener(NoRedirect)
        raw = json.dumps({'id': record['event_id'], 'type': 'checkout.session.completed', 'livemode': False, 'data': {'object': {'id': record['session_id']}}}, separators=(',', ':')).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        for _ in range(2):
            request = Request('https://mirroriedled.com/MLED_checkout_TEST/customer-portal/backend/api.php?action=commerce-webhook', data=raw, headers={'Content-Type': 'application/json', 'Stripe-Signature': 't=' + stamp + ',v1=' + signature}, method='POST')
            with client.open(request, timeout=20) as response:
                if response.status != 200 or json.load(response).get('ok') is not True:
                    raise ValueError('Duplicate canonical-event replay failed')
        inspect(webroot, *hashes, total_cents, tax_cents)
    return {'canonical_test_payment_recorded': True, 'paid_total_cents': total_cents,
            'tax_cents': tax_cents, 'actual_provider_event_processed': True,
            'single_payment_confirmation': True, 'known_event_self_signed_replay_verified': replay,
            'production_release_performed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webroot', type=Path, required=True)
    for name in ('order', 'session', 'event', 'intent'):
        parser.add_argument('--' + name + '-fingerprint', required=True)
    parser.add_argument('--replay-known-event', action='store_true')
    args = parser.parse_args()
    try:
        hashes = [getattr(args, name + '_fingerprint') for name in ('order', 'session', 'event', 'intent')]
        print(json.dumps(verify(args.webroot, hashes, replay=args.replay_known_event), sort_keys=True))
    except Exception:
        raise SystemExit('Sandbox payment verification stopped; inspect private acceptance records. No production release performed.') from None
