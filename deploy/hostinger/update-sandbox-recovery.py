#!/usr/bin/env python3
"""Patch only the isolated payment-recovery files, preserving paid records and configuration."""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

spec=importlib.util.spec_from_file_location('sandbox_enable',Path(__file__).with_name('enable-sandbox-checkout.py'))
enable=importlib.util.module_from_spec(spec);spec.loader.exec_module(enable)
FILES=('customer-portal/backend/commerce.php','shop/shop.js','shop/index.html')
KEYS=('mirroriedled_storefront_cart_vnext','mirroriedled_quote_draft_v1','mled_pending_build','mirroriedled_infinity_drafts_v1','mledStadiumTestSelectionV1')


def sha(data): return hashlib.sha256(data).hexdigest()


def paid_record(database, order_hash):
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        orders=[dict(r) for r in db.execute('SELECT * FROM business_orders') if sha(r['id'].encode())==order_hash]
        if len(orders)!=1: raise ValueError('Selected paid test order required')
        order=orders[0]
        rows=[dict(r) for r in db.execute('SELECT * FROM commerce_checkouts')]
        if len(rows)!=1: raise ValueError('Exactly one completed test checkout required')
        row=rows[0];snapshot=json.loads(row['snapshot'])
        if row['order_id']!=order['id'] or row['state']!='paid' or row['paid_cents']!=109 or row['tax_cents']!=9 or snapshot.get('mode')!='test' or snapshot.get('productCents')!=100 or snapshot.get('shippingCents')!=0 or order['status']!='APPROVED' or order['finance_reference']!=row['payment_intent'] or order['approved_proof_id']!=order['proof_id']:
            raise ValueError('Preserved artificial paid test order required')
        if db.execute("SELECT COUNT(*) FROM business_events WHERE order_id=? AND kind='PAYMENT_CONFIRMED'",(order['id'],)).fetchone()[0]!=1:
            raise ValueError('Single payment confirmation required')
        return order,row


def expanded_key_check(credentials, order, row, client=None):
    if not re.fullmatch(r'rk_test_[A-Za-z0-9]+',credentials.get('stripe_secret_key','')) or not re.fullmatch(r'whsec_[A-Za-z0-9]+',credentials.get('stripe_webhook_secret','')):
        raise ValueError('Installed restricted test credentials required')
    if not re.fullmatch(r'cs_test_[A-Za-z0-9]+',row['provider_id'] or ''):raise ValueError('Canonical sandbox checkout required')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    client=client or build_opener(NoRedirect)
    url='https://api.stripe.com/v1/checkout/sessions/'+row['provider_id']+'?'+urlencode({'expand[]':['line_items','payment_intent']},doseq=True)
    request=Request(url,headers={'Authorization':'Bearer '+credentials['stripe_secret_key'],'Stripe-Version':'2026-09-30.endive'})
    with client.open(request,timeout=25) as response:
        if response.status!=200:raise ValueError('Restricted-key expanded read refused')
        data=json.loads(response.read(2097153))
    intent=data.get('payment_intent');items=data.get('line_items',{}).get('data',[])
    if data.get('id')!=row['provider_id'] or data.get('livemode') is not False or data.get('status')!='complete' or data.get('payment_status')!='paid' or data.get('amount_total')!=109 or data.get('amount_subtotal')!=100 or data.get('currency')!='usd' or data.get('client_reference_id')!=order['id'] or data.get('metadata',{}).get('order_id')!=order['id'] or data.get('total_details',{}).get('amount_tax')!=9 or data.get('total_details',{}).get('amount_shipping')!=0 or len(items)!=1 or items[0].get('amount_subtotal')!=100 or items[0].get('quantity')!=1:
        raise ValueError('Canonical completed test checkout mismatch')
    if not isinstance(intent,dict) or intent.get('id')!=row['payment_intent'] or intent.get('status')!='succeeded' or intent.get('livemode') is not False or intent.get('amount_received')!=109 or intent.get('metadata',{}).get('order_id')!=order['id']:
        raise ValueError('Restricted key must expand canonical PaymentIntent')


def patch(webroot, folder, source, expected_source, order_hash, client=None):
    webroot=webroot.absolute();folder=folder.absolute()
    if webroot.name!='public_html' or webroot.parent.name!='mirroriedled.com' or any(not re.fullmatch(r'[a-f0-9]{40}',v) for v in (source,expected_source)) or not re.fullmatch(r'[a-f0-9]{64}',order_hash):raise ValueError('Exact isolated source and selection required')
    private=webroot.parent/'mirroriedled-private/checkout-sandbox';stage=webroot/'MLED_checkout_TEST'
    for p in (webroot.parent,webroot,private.parent,stage,stage/'customer-portal',stage/'customer-portal/backend',stage/'shop'):enable.safe(p,directory=True)
    for p in (private,private/'storage'):enable.safe(p,directory=True,private=True)
    for name in ('config.php','credentials.json','receipt.json','storage/portal.sqlite'):enable.safe(private/name,private=True)
    if enable.sandbox.release.within(folder.resolve(strict=True),webroot.resolve()):raise ValueError('Patch transport must be private')
    config_path=private/'config.php';config=config_path.read_bytes()
    wanted=enable.sandbox.sandbox_config().replace(b"'stripe_webhook_secret' => ''",b"'stripe_webhook_secret' => $credentials['stripe_webhook_secret'] ?? ''").replace(b"'enabled' => false",b"'enabled' => true").replace(b"'tax_setup_confirmed' => false",b"'tax_setup_confirmed' => true").replace(b"'fulfillment_setup_confirmed' => false",b"'fulfillment_setup_confirmed' => true")
    if config!=wanted:raise ValueError('Recognized enabled test configuration required')
    lock=private/'.checkout-enable.lock';fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        enable.safe(lock,private=True)
        if os.fstat(fd).st_ino!=lock.stat().st_ino:raise ValueError('Unsafe patch lock')
        fcntl.flock(fd,fcntl.LOCK_EX)
        backup=private/('recovery-'+source)
        if not backup.exists():backup.mkdir(mode=0o700)
        enable.safe(backup,directory=True,private=True)
        receipt_path=private/'receipt.json';receipt=json.loads(receipt_path.read_bytes());journal=backup/'journal.json'
        if journal.exists():
            enable.safe(journal,private=True);saved=json.loads(journal.read_bytes())
            if saved.get('source')!=source or saved.get('expected_source')!=expected_source:raise ValueError('Different recovery journal preserved')
            original=saved['original_receipt']
        else:
            if receipt.get('checkout_patch',{}).get('source_sha')!=expected_source:raise ValueError('Expected reviewed checkout patch required')
            original=copy.deepcopy(receipt)
        if receipt.get('checkout_patch',{}).get('source_sha') not in (expected_source,source):raise ValueError('Unrelated checkout patch preserved')
        generated={}
        for name in FILES:
            target=stage/name;enable.safe(target)
            incoming=folder/Path(name).name;enable.safe(incoming);data=incoming.read_bytes()
            if len(data)>131072:raise ValueError('Oversized recovery source')
            if name.endswith('.php'):
                if not data.startswith(b'<?php') or data.count(b'declare(strict_types=1);')!=1:raise ValueError('Reviewed PHP required')
                data=data.replace(b'declare(strict_types=1);',b"declare(strict_types=1);\nheader('X-MLED-Checkout-Source: "+source.encode()+b"');",1)
            elif name.endswith('.js'):
                if b'checkout_sandbox_' in data:raise ValueError('Untransformed reviewed JS required')
                for key in KEYS:data=data.replace(key.encode(),('checkout_sandbox_'+key).encode())
            else:
                text=data.decode();text=re.sub(r'(<head\b[^>]*>)',r'\1<meta name="robots" content="noindex,nofollow">',text,count=1,flags=re.I);text=re.sub(r'(<body\b[^>]*>)',r'\1<p role="status" style="padding:12px;background:#172a41;color:white;text-align:center">SANDBOX — test data only. No real payments or production orders.</p>',text,count=1,flags=re.I);data=text.encode()
            generated[name]=data
            if sha(target.read_bytes()) not in (original['public_hashes'][name],sha(data)):raise ValueError('Unknown sandbox edit preserved')
        if receipt.get('source_sha')!=original.get('source_sha'):raise ValueError('Original sandbox base changed')
        api=stage/'customer-portal/backend/api.php';enable.safe(api)
        if '/mirroriedled-private/checkout-sandbox/config.php' not in api.read_text() or ('X-MLED-Sandbox-Source: '+original['source_sha']) not in api.read_text():raise ValueError('Isolated base API required')
        desired_receipt=copy.deepcopy(original);desired_receipt['public_hashes'].update({name:sha(data) for name,data in generated.items()})
        desired_receipt['checkout_patch']={'source_sha':source,'sha256':sha(generated[FILES[0]]),'base_sha256':original['checkout_patch']['base_sha256'],'previous_source_sha':expected_source,'previous_sha256':original['public_hashes'][FILES[0]]}
        desired_receipt['recovery_patch']={'source_sha':source,'hashes':{name:sha(data) for name,data in generated.items()}}
        if receipt not in (original,desired_receipt):raise ValueError('Unknown receipt edit preserved')
        before=paid_record(private/'storage/portal.sqlite',order_hash)
        expanded_key_check(json.loads((private/'credentials.json').read_bytes()),*before,client=client)
        if not journal.exists():enable.atomic(journal,json.dumps({'source':source,'expected_source':expected_source,'original_receipt':original},sort_keys=True).encode())
        for i,name in enumerate(FILES):
            saved=backup/(str(i)+'.original')
            if saved.exists():
                enable.safe(saved,private=True)
                if sha(saved.read_bytes())!=original['public_hashes'][name]:raise ValueError('Original patch backup mismatch')
            else:
                old=(stage/name).read_bytes()
                if sha(old)!=original['public_hashes'][name]:raise ValueError('Original recovery backup missing')
                enable.atomic(saved,old)
        for name,data in generated.items():enable.atomic(stage/name,data,0o644)
        enable.atomic(receipt_path,json.dumps(desired_receipt,sort_keys=True).encode())
        if paid_record(private/'storage/portal.sqlite',order_hash)!=before or config_path.read_bytes()!=config:raise ValueError('Concurrent private record/configuration change; review required')
    finally:os.close(fd)
    return {'sandbox_recovery_patch_installed':True,'restricted_key_expanded_intent_read_verified':True,'paid_test_record_preserved':True,'private_configuration_changed':False,'production_payment_activation':False,'patch_source':source,'hashes':{name:sha(data) for name,data in generated.items()}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--webroot',type=Path,required=True);p.add_argument('--folder',type=Path,required=True);p.add_argument('--source',required=True);p.add_argument('--expected-source',required=True);p.add_argument('--order-fingerprint',required=True);a=p.parse_args()
    try:print(json.dumps(patch(a.webroot,a.folder,a.source,a.expected_source,a.order_fingerprint),sort_keys=True))
    except Exception:raise SystemExit('Sandbox recovery update stopped; inspect private preflight/patch state. No production activation performed.') from None
