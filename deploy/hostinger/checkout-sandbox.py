#!/usr/bin/env python3
"""Create an isolated, initially payment-disabled copy of the reviewed storefront."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load('sandbox_release', 'website-release.py')
accounts = load('sandbox_accounts', 'setup-customer-accounts.py')
STAGE = 'MLED_checkout_TEST'


def exclusive(path, data):
    with path.open('xb') as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)


def install(webroot, archive, credentials, template, source_sha):
    webroot = webroot.absolute()
    release.no_symlinks(webroot)
    if webroot.name != 'public_html' or webroot.parent.name != 'mirroriedled.com' or not webroot.is_dir():
        raise ValueError('Use the main domain public_html directory')
    root_info = webroot.stat()
    if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) & 0o022:
        raise ValueError('Unsafe public_html ownership or write permissions')
    parent = webroot.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o022:
        raise ValueError('Unsafe domain parent permissions')
    if not re.fullmatch('[a-f0-9]{40}', source_sha):
        raise ValueError('An exact source commit is required')
    stage = webroot / STAGE
    shared = webroot.parent / 'mirroriedled-private'
    private = shared / 'checkout-sandbox'
    for path in (stage, shared, private):
        release.no_symlinks(path)
    if stage.exists() or private.exists():
        raise ValueError('Existing sandbox files and private records must be preserved')
    if release.within(credentials.resolve(strict=True), webroot.resolve()):
        raise ValueError('Credentials must remain outside public_html')
    raw = credentials.read_bytes()
    if len(raw) > 65536:
        raise ValueError('Invalid sandbox credential file')
    secret = json.loads(raw)
    if not isinstance(secret, dict) or not re.fullmatch(r'rk_test_[A-Za-z0-9]+', str(secret.get('stripe_secret_key', ''))):
        raise ValueError('Only a restricted sandbox key is allowed')
    base = template.read_bytes()
    if not base.startswith(b'<?php') or len(base) > 65536:
        raise ValueError('Reviewed configuration template required')
    with tempfile.TemporaryDirectory() as temporary:
        unpacked = Path(temporary) / 'website'
        unpacked.mkdir(mode=0o700)
        release.unpack(archive, unpacked)
        api_path = unpacked / 'customer-portal/backend/api.php'
        api = api_path.read_text()
        needle = 'declare(strict_types=1);'
        if api.count(needle) != 1:
            raise ValueError('Unexpected API source')
        api_path.write_text(api.replace(needle, needle + "\n\n// Deployment-only sandbox configuration; never fall back to production.\nif (!putenv('MLED_PORTAL_CONFIG=' . dirname(__DIR__, 4) . '/mirroriedled-private/checkout-sandbox/config.php')) { http_response_code(503); exit; }\nheader('X-MLED-Sandbox-Source: " + source_sha + "');", 1))
        for path in unpacked.rglob('*'):
            if path.suffix == '.js':
                data = path.read_text()
                for key in ('mirroriedled_storefront_cart_vnext', 'mirroriedled_quote_draft_v1',
                            'mled_pending_build', 'mirroriedled_infinity_drafts_v1',
                            'mledStadiumTestSelectionV1'):
                    data = data.replace(key, 'checkout_sandbox_' + key)
                path.write_text(data)
            if path.suffix == '.html':
                data = path.read_text()
                data = re.sub(r'(<head\b[^>]*>)', r'\1<meta name="robots" content="noindex,nofollow">', data, count=1, flags=re.I)
                data = re.sub(r'(<body\b[^>]*>)', r'\1<p role="status" style="padding:12px;background:#172a41;color:white;text-align:center">SANDBOX — test data only. No real payments or production orders.</p>', data, count=1, flags=re.I)
                path.write_text(data)
        # All edits are confined to this generated copy. Keep a private exact hash receipt.
        hashes = {name: release.digest(unpacked / name) for name in release.PUBLIC_FILES}
        config = b'''<?php
declare(strict_types=1);
$config = require __DIR__ . '/base.php';
$credentials = json_decode(file_get_contents(__DIR__ . '/credentials.json'), true, 16, JSON_THROW_ON_ERROR);
if (!is_array($credentials) || !preg_match('/^rk_test_[A-Za-z0-9]+$/D', (string)($credentials['stripe_secret_key'] ?? ''))) {
    throw new RuntimeException('Invalid sandbox configuration');
}
$config['business_enabled'] = true;
$config['premium_enabled'] = false;
$config['staff_users'] = [];
$config['storage_path'] = __DIR__ . '/storage';
$config['origin'] = 'https://mirroriedled.com';
$config['commerce'] = ['enabled' => false, 'mode' => 'test',
    'stripe_secret_key' => $credentials['stripe_secret_key'], 'stripe_webhook_secret' => '',
    'tax_setup_confirmed' => false, 'fulfillment_setup_confirmed' => false];
return $config;
'''
        accounts.private_directory(shared, require_owner_only=False)
        # Atomic reservations refuse pre-existing directories, including empty ones.
        private.mkdir(mode=0o700)
        (private / 'storage').mkdir(mode=0o700)
        exclusive(private / 'credentials.json', json.dumps({'stripe_secret_key': secret['stripe_secret_key']}).encode())
        exclusive(private / 'base.php', base)
        exclusive(private / 'config.php', config)
        exclusive(private / 'receipt.json', json.dumps({'source_sha': source_sha, 'public_hashes': hashes, 'payments_enabled': False}).encode())
        stage.mkdir(mode=0o755)
        # Block requests while files are incomplete. On failure preserve for inspection.
        (stage / '.htaccess').write_text('Require all denied\n')
        for name in release.PUBLIC_FILES:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            shutil.copyfile(unpacked / name, target)
            target.chmod(0o644)
        (stage / '.htaccess').write_text('Options -Indexes\n<IfModule mod_headers.c>\nHeader always set X-Robots-Tag "noindex, nofollow"\n</IfModule>\n')
    return {'created': True, 'source_sha': source_sha, 'payments_enabled': False,
            'private_storage_isolated': True, 'production_files_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webroot', required=True)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--credentials', required=True, type=Path)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--source', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(install(release.webroot_path(args.webroot), args.archive,
                                 args.credentials, args.template, args.source), sort_keys=True))
    except Exception:
        raise SystemExit('Sandbox installation failed; inspect paths and permissions without exposing credentials. Existing production data was not modified.') from None
