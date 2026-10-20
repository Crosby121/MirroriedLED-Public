#!/usr/bin/env python3
"""Create an isolated, initially payment-disabled copy of the reviewed storefront."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
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


def sandbox_config():
    return b'''<?php
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
        config = sandbox_config()
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


def install_webhook_secret(webroot, supplied):
    """Add only the signer to this installer's disabled, isolated configuration."""
    if not isinstance(supplied, dict) or set(supplied) != {'stripe_webhook_secret'}:
        raise ValueError('One sandbox webhook secret is required')
    signer = supplied['stripe_webhook_secret']
    if not isinstance(signer, str) or not re.fullmatch(r'whsec_[A-Za-z0-9]{1,200}', signer):
        raise ValueError('Sandbox webhook signing secret required')
    webroot = webroot.absolute()
    if webroot.name != 'public_html' or webroot.parent.name != 'mirroriedled.com':
        raise ValueError('Use the main domain public_html directory')
    private = webroot.parent / 'mirroriedled-private/checkout-sandbox'
    for path in (webroot, webroot.parent, private.parent, private):
        release.no_symlinks(path)
        info = path.stat()
        mask = 0o077 if path == private else 0o022
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & mask:
            raise ValueError('Unsafe sandbox directory')

    def read_private(name):
        path = private / name
        release.no_symlinks(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 65536:
            raise ValueError('Unsafe sandbox private file')
        return path.read_bytes()

    def replace_private(name, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=private, prefix='.signer-', delete=False) as output:
                temporary = Path(output.name)
                os.fchmod(output.fileno(), 0o600)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, private / name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    lock = private / '.signer-install.lock'
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Unsafe sandbox lock file')
        # Kernel releases this lock even if the worker is killed or times out.
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        receipt = json.loads(read_private('receipt.json'))
        if receipt.get('payments_enabled') is not False or not re.fullmatch(r'[a-f0-9]{40}', str(receipt.get('source_sha', ''))):
            raise ValueError('Disabled sandbox receipt required')
        api = webroot / STAGE / 'customer-portal/backend/api.php'
        release.no_symlinks(api)
        api_source = api.read_text()
        if '/mirroriedled-private/checkout-sandbox/config.php' not in api_source or 'X-MLED-Sandbox-Source: ' + receipt['source_sha'] not in api_source:
            raise ValueError('Isolated sandbox API required')
        original = sandbox_config()
        configured = original.replace(b"'stripe_webhook_secret' => ''", b"'stripe_webhook_secret' => $credentials['stripe_webhook_secret'] ?? ''")
        if read_private('config.php') not in (original, configured):
            raise ValueError('Sandbox configuration changed; owner review required')
        credentials = json.loads(read_private('credentials.json'))
        if not isinstance(credentials, dict) or set(credentials) - {'stripe_secret_key', 'stripe_webhook_secret'} or not re.fullmatch(r'rk_test_[A-Za-z0-9]+', str(credentials.get('stripe_secret_key', ''))):
            raise ValueError('Restricted sandbox credential required')
        if credentials.get('stripe_webhook_secret') not in (None, signer):
            raise ValueError('Existing signer preserved; rotation needs separate review')
        credentials['stripe_webhook_secret'] = signer
        replace_private('credentials.json', json.dumps(credentials).encode())
        # Publish the configuration reference last. Interruption leaves checkout off.
        replace_private('config.php', configured)
    finally:
        os.close(descriptor)
    return {'webhook_signing_secret_installed': True, 'payments_enabled': False,
            'signed_delivery_verified': False, 'production_files_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--webroot', required=True)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--template', type=Path)
    parser.add_argument('--source')
    parser.add_argument('--webhook-secret-stdin', action='store_true')
    args = parser.parse_args()
    try:
        webroot = release.webroot_path(args.webroot)
        if args.webhook_secret_stdin:
            raw = sys.stdin.buffer.read(65537)
            if len(raw) > 65536:
                raise ValueError('Invalid signing-secret transport')
            result = install_webhook_secret(webroot, json.loads(raw))
        else:
            if not all((args.archive, args.credentials, args.template, args.source)):
                raise ValueError('Installation arguments are required')
            result = install(webroot, args.archive, args.credentials, args.template, args.source)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        raise SystemExit('Sandbox installation failed; inspect paths and permissions without exposing credentials. Existing production data was not modified.') from None
