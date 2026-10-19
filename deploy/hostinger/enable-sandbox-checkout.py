#!/usr/bin/env python3
"""Enable only the isolated sandbox after a selected artificial quote is approved."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time

spec = importlib.util.spec_from_file_location('checkout_sandbox', Path(__file__).with_name('checkout-sandbox.py'))
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)
COMMERCE = 'customer-portal/backend/commerce.php'


def safe(path, directory=False, private=False):
    sandbox.release.no_symlinks(path)
    info = path.stat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & (0o077 if private else 0o022) or (not directory and info.st_nlink != 1):
        raise ValueError('Unsafe sandbox path')


def atomic(path, data, mode=0o600):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mled-checkout-', delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def activate(webroot, patch, source_sha, fingerprint, tax_confirmed, fake_fulfillment_confirmed):
    if tax_confirmed is not True or fake_fulfillment_confirmed is not True:
        raise ValueError('Fresh sandbox tax and artificial fulfillment confirmations required')
    if not re.fullmatch(r'[a-f0-9]{40}', source_sha) or not re.fullmatch(r'[a-f0-9]{64}', fingerprint):
        raise ValueError('Exact source and authorized order fingerprint required')
    webroot = webroot.absolute()
    if webroot.name != 'public_html' or webroot.parent.name != 'mirroriedled.com':
        raise ValueError('Isolated main-domain sandbox required')
    private = webroot.parent / 'mirroriedled-private/checkout-sandbox'
    for path in (webroot.parent, webroot, private.parent):
        safe(path, directory=True)
    safe(private, directory=True, private=True)
    stage = webroot / sandbox.STAGE
    target = stage / COMMERCE
    for path in (stage, *target.parents):
        if path == webroot.parent:
            break
        safe(path, directory=True)
    safe(target)
    config_path = private / 'config.php'
    receipt_path = private / 'receipt.json'
    for path in (config_path, receipt_path, private / 'credentials.json'):
        safe(path, private=True)
    safe(private / 'storage', directory=True, private=True)
    safe(private / 'storage/portal.sqlite', private=True)
    lock = private / '.checkout-enable.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        safe(lock, private=True)
        if os.fstat(fd).st_ino != lock.stat().st_ino:
            raise ValueError('Invalid sandbox activation lock')
        fcntl.flock(fd, fcntl.LOCK_EX)
        disabled = sandbox.sandbox_config().replace(b"'stripe_webhook_secret' => ''", b"'stripe_webhook_secret' => $credentials['stripe_webhook_secret'] ?? ''")
        enabled = disabled.replace(b"'enabled' => false", b"'enabled' => true").replace(b"'tax_setup_confirmed' => false", b"'tax_setup_confirmed' => true").replace(b"'fulfillment_setup_confirmed' => false", b"'fulfillment_setup_confirmed' => true")
        if config_path.read_bytes() not in (disabled, enabled):
            raise ValueError('Unknown sandbox configuration preserved')
        credentials = json.loads((private / 'credentials.json').read_bytes())
        if not re.fullmatch(r'rk_test_[A-Za-z0-9]+', str(credentials.get('stripe_secret_key', ''))) or not re.fullmatch(r'whsec_[A-Za-z0-9]+', str(credentials.get('stripe_webhook_secret', ''))):
            raise ValueError('Restricted test key and installed signer required')
        receipt = json.loads(receipt_path.read_bytes())
        if not re.fullmatch(r'[a-f0-9]{40}', str(receipt.get('source_sha', ''))):
            raise ValueError('Sandbox base source receipt required')
        api = stage / 'customer-portal/backend/api.php'
        safe(api)
        api_source = api.read_text()
        if '/mirroriedled-private/checkout-sandbox/config.php' not in api_source or 'X-MLED-Sandbox-Source: ' + receipt['source_sha'] not in api_source:
            raise ValueError('Isolated sandbox API required')
        with sqlite3.connect((private / 'storage/portal.sqlite').as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            orders = [row for row in db.execute('SELECT * FROM business_orders') if hashlib.sha256(row['id'].encode()).hexdigest() == fingerprint]
            if len(orders) != 1:
                raise ValueError('Authorized test order not found')
            order = orders[0]
            if order['status'] != 'APPROVED' or not order['proof_id'] or order['approved_proof_id'] != order['proof_id'] or order['quote_cents'] != 100:
                raise ValueError('Actual customer approval of the one-dollar test proof required')
            proof = db.execute('SELECT summary FROM business_proofs WHERE id=? AND order_id=?', (order['proof_id'], order['id'])).fetchone()
            offer = db.execute('SELECT terms FROM commerce_offers WHERE order_id=?', (order['id'],)).fetchone()
            items = json.loads(order['configuration'])
            if len(items) != 1 or items[0].get('product') != 'Custom Infinity Mirror' or items[0].get('size') != '12×12' or items[0].get('quantity') != 1 or not proof or not proof['summary'].startswith('SANDBOX CHECKOUT TEST ONLY:') or not offer:
                raise ValueError('Explicitly artificial approved mirror quote required')
            terms = json.loads(offer['terms'])
            if terms.get('proofId') != order['proof_id'] or terms.get('productCents') != 100 or terms.get('shippingCents') != 0 or terms.get('expiresAt', 0) <= time.time() or terms.get('address', {}).get('country') != 'US' or terms.get('address', {}).get('state') != 'CA':
                raise ValueError('Current California test offer required')
            if db.execute('SELECT COUNT(*) FROM commerce_checkouts').fetchone()[0] != 0:
                raise ValueError('Existing checkout records require separate review')
        if sandbox.release.within(patch.resolve(strict=True), webroot.resolve()):
            raise ValueError('Reviewed patch transport must be outside public_html')
        data = patch.read_bytes()
        if not data.startswith(b'<?php') or len(data) > 131072 or data.count(b'declare(strict_types=1);') != 1 or b"STRIPE_API_VERSION = '2026-09-30.endive'" not in data:
            raise ValueError('Reviewed versioned commerce source required')
        generated = data.replace(b'declare(strict_types=1);', b"declare(strict_types=1);\nheader('X-MLED-Checkout-Source: " + source_sha.encode() + b"');", 1)
        digest = hashlib.sha256(generated).hexdigest()
        base_digest = receipt.get('public_hashes', {}).get(COMMERCE)
        saved_patch = receipt.get('checkout_patch')
        if saved_patch and (saved_patch.get('source_sha') != source_sha or saved_patch.get('sha256') != digest):
            raise ValueError('Existing different checkout patch preserved')
        current = target.read_bytes()
        if hashlib.sha256(current).hexdigest() not in (base_digest, digest):
            raise ValueError('Unknown sandbox backend edit preserved')
        backup = private / 'commerce-before-checkout.php'
        if backup.exists() or backup.is_symlink():
            safe(backup, private=True)
            if hashlib.sha256(backup.read_bytes()).hexdigest() != (saved_patch or {}).get('base_sha256', base_digest):
                raise ValueError('Original sandbox backend backup mismatch')
        else:
            if hashlib.sha256(current).hexdigest() != base_digest:
                raise ValueError('Original backend backup required')
            atomic(backup, current)
        try:
            atomic(target, generated, 0o644)
            receipt['checkout_patch'] = {'source_sha': source_sha, 'sha256': digest,
                                        'base_sha256': (saved_patch or {}).get('base_sha256', base_digest)}
            receipt['public_hashes'][COMMERCE] = digest
            receipt['payments_enabled'] = True
            atomic(receipt_path, json.dumps(receipt, sort_keys=True).encode())
            # Publish readiness last; private data and account roles are never rewritten.
            atomic(config_path, enabled)
        except Exception:
            atomic(config_path, disabled)
            raise
    finally:
        os.close(fd)
    return {'customer_approval_verified': True, 'sandbox_checkout_enabled': True,
            'checkout_patch_source': source_sha, 'production_files_changed': False,
            'checkout_write_verified': False, 'stripe_signed_delivery_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webroot', required=True)
    parser.add_argument('--commerce', required=True, type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--order-fingerprint', required=True)
    parser.add_argument('--sandbox-tax-confirmed', action='store_true')
    parser.add_argument('--fake-fulfillment-confirmed', action='store_true')
    args = parser.parse_args()
    try:
        result = activate(sandbox.release.webroot_path(args.webroot), args.commerce, args.source,
                          args.order_fingerprint, args.sandbox_tax_confirmed, args.fake_fulfillment_confirmed)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        raise SystemExit('Sandbox checkout activation stopped; inspect private prerequisites. No production activation performed.') from None
