"""Physical-product checkout acceptance with a deterministic provider double.
No actual merchant connection or live charge is claimed by these tests.
"""
import copy
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import unittest
import uuid
import test_business_backend as business_tests
from test_customer_portal_backend import PHP, php_quote

ADDRESS={'name':'Test Customer','line1':'100 Test Way','line2':'','city':'West Covina','state':'CA','postalCode':'91790','country':'US'}

@unittest.skipUnless(PHP,'PHP runtime required')
class CommerceTests(unittest.TestCase):
    def setUp(self):
        self.h=business_tests.BusinessTests();self.h.setUp();self.server=self.h.server
    def tearDown(self): self.h.tearDown()
    def post(self,client,action,data,expected=200): return self.h.post(client,action,data,expected)
    def enable_test(self):
        # Clearly artificial, test-only credentials; not a merchant account.
        s=self.server.config.read_text();s=s.rsplit('];',1)[0]+"'commerce'=>['enabled'=>true,'mode'=>'test','stripe_secret_key'=>'sk_test_TESTONLY','stripe_webhook_secret'=>'whsec_TESTONLY','tax_setup_confirmed'=>true,'fulfillment_setup_confirmed'=>true],\n];\n";self.server.config.write_text(s)
    def quoted(self,sign=False):
        if not sign: order=self.h.quoted()
        else:
            spec={'version':1,'number':'128','street':'Test Way','size':'18×8','finish':'Matte black','mount':'Wall mount','lighting':'Addressable effects','font':'Modern','color':'Turquoise'}
            order=self.post(self.h.customer,'business-request',{'items':[{'product':'Address Sign or Mailbox','size':'18×8','artwork':'128 Test Way','artworkSource':'team-design','quantity':1,'addressBuilder':spec}]})['order']
            file=self.h.upload(self.h.staff,order,'proof')['file'];order=self.post(self.h.staff,'business-proof',{'orderId':order['id'],'revision':order['revision'],'fileId':file['id'],'quoteCents':35000,'summary':'Complete tested sign scope.'})['order']
        self.post(self.h.customer,'commerce-address',{'orderId':order['id'],'address':ADDRESS})
        terms={'orderId':order['id'],'proofId':order['proof']['id'],'shippingCents':2500,'productionMinDays':7,'productionMaxDays':14,'transitMinDays':2,'transitMaxDays':5,'fulfillmentConfirmed':True}
        return order,terms
    def approved_offer(self,sign=False):
        order,terms=self.quoted(sign);offer=self.post(self.h.staff,'commerce-offer',terms)['commerce']['offer'];order=self.post(self.h.customer,'business-approve',{'orderId':order['id'],'revision':order['revision'],'proofId':order['proof']['id'],'acceptQuote':True})['order'];return order,offer
    def cli(self,order_id,operation='checkout',session=None):
        # A PHP callable is injected by this test process only; the HTTP app cannot select one.
        source=self.server.public/'customer-portal/backend/portal.php'
        script=self.server.root/'acceptance.php'
        fixture=self.server.root/'payment.json';fixture.write_text(json.dumps(session or {}))
        code="<?php require "+php_quote(str(source))+"; $config=require "+php_quote(str(self.server.config))+"; $db=new PDO('sqlite:' . $config['storage_path'] . '/portal.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]); $user=$db->query('SELECT * FROM users WHERE id="+str(self.h.customer_id)+"')->fetch();"
        code+=" $transport=function($method,$path,$params,$key) { file_put_contents("+php_quote(str(self.server.root/'provider-requests.jsonl'))+",json_encode([$method,$path,$params,$key]).PHP_EOL,FILE_APPEND); if($path==='/customers')return ['id'=>'cus_TESTONLY']; if($path==='/checkout/sessions')return ['id'=>'cs_test_ACCEPTANCE','url'=>'https://checkout.stripe.com/c/pay/cs_test_ACCEPTANCE','expires_at'=>time()+3600]; throw new RuntimeException('Unexpected provider request'); }; $service=new CommercePortal($db,$config,$user,$transport);"
        if operation=='checkout':
            version=self.db().execute('SELECT version FROM commerce_offers WHERE order_id=?',(order_id,)).fetchone()[0]
            code+="$service->handle('commerce-checkout',['orderId'=>"+php_quote(order_id)+",'offerVersion'=>"+str(version)+",'acceptTerms'=>true]);"
        else: code+="$service->reconcile(json_decode(file_get_contents("+php_quote(str(fixture))+"),true)); echo json_encode(CommercePortal::publicTerms($db,"+php_quote(order_id)+"));"
        script.write_text(code)
        result=subprocess.run([PHP,str(script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return json.loads(result.stdout)
    def db(self):
        db=sqlite3.connect(self.server.storage/'portal.sqlite');self.addCleanup(db.close);return db
    def paid_session(self,order):
        row=self.db().execute('SELECT id FROM commerce_checkouts WHERE order_id=?',(order['id'],)).fetchone()
        return {'id':'cs_test_ACCEPTANCE','mode':'payment','currency':'usd','livemode':False,'client_reference_id':order['id'], 'metadata':{'order_id':order['id'],'checkout_record':str(row[0]),'proof_id':order['proof']['id']},'amount_subtotal':35000,'amount_total':40750,'total_details':{'amount_shipping':2500,'amount_tax':3250,'amount_discount':0},'automatic_tax':{'status':'complete'},'payment_status':'paid','status':'complete','payment_intent':'pi_TESTONLY','line_items':{'data':[{'quantity':1,'amount_subtotal':35000}]}}
    def test_unconfigured_status_and_checkout_do_not_claim_payments(self):
        data=self.h.customer.json('commerce-status')[1];self.assertFalse(data['paymentsAvailable'])
        order,offer=self.approved_offer();self.post(self.h.customer,'commerce-checkout',{'orderId':order['id'],'offerVersion':offer['version'],'acceptTerms':True},503)
        self.assertEqual(self.db().execute('SELECT COUNT(*) FROM commerce_checkouts').fetchone()[0],0)
    def test_two_products_preserve_quotes_and_scope_proof_before_payment(self):
        for sign in [False,True]:
            order,terms=self.quoted(sign);self.post(self.h.customer,'commerce-offer',terms,403)
            broken={**terms,'productionMaxDays':1};self.post(self.h.staff,'commerce-offer',broken,422)
            offer=self.post(self.h.staff,'commerce-offer',terms)['commerce']['offer'];self.assertEqual(offer['beforeTaxCents'],37500)
            self.enable_test();self.post(self.h.customer,'commerce-checkout',{'orderId':order['id'],'offerVersion':offer['version'],'acceptTerms':True},409)
            self.post(self.h.staff,'business-release',{'orderId':order['id'],'revision':order['revision']},409)
            # Reset config for the next product, avoiding duplicate fake keys.
            self.server.write_config()
        self.post(self.h.customer,'business-request',{'items':[{'product':'Layered Stadium Model','size':'Mini','artwork':'Venue','quantity':1}]},403)
    def test_provider_parameters_retry_reconciliation_and_no_double_charge(self):
        order,offer=self.approved_offer(True);self.enable_test()
        result=self.cli(order['id']);self.assertEqual(result['checkoutUrl'],'https://checkout.stripe.com/c/pay/cs_test_ACCEPTANCE')
        calls=(self.server.root/'provider-requests.jsonl').read_text().splitlines();self.assertEqual(len(calls),2)
        session_params=json.loads(calls[1])[2];self.assertEqual(session_params['line_items'][0]['price_data']['unit_amount'],35000);self.assertEqual(session_params['shipping_options'][0]['shipping_rate_data']['fixed_amount']['amount'],2500)
        self.assertEqual(session_params['automatic_tax']['enabled'],'true');self.assertNotIn('shipping_address_collection',session_params)
        again=self.cli(order['id']);self.assertEqual(result,again);self.assertEqual(len((self.server.root/'provider-requests.jsonl').read_text().splitlines()),2)
        paid=self.paid_session(order);confirmed=self.cli(order['id'],'reconcile',paid);self.assertEqual(confirmed['payment']['state'],'paid');self.assertEqual(confirmed['payment']['paid_cents'],40750)
        self.cli(order['id'],'reconcile',paid)
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM business_events WHERE kind='PAYMENT_CONFIRMED'").fetchone()[0],1)
        current=self.h.current(order);self.post(self.h.staff,'business-release',{'orderId':order['id'],'revision':current['revision']},409)
        self.post(self.h.staff,'business-cancel',{'orderId':order['id'],'revision':current['revision'],'note':'Payment unresolved'},409)
    def test_forged_paid_return_and_mismatched_amount_never_mark_paid(self):
        order,offer=self.approved_offer();self.enable_test();self.cli(order['id'])
        unpaid=self.paid_session(order);unpaid['payment_status']='unpaid';self.cli(order['id'],'reconcile',unpaid)
        self.assertEqual(self.db().execute('SELECT state FROM commerce_checkouts').fetchone()[0],'open')
        wrong=self.paid_session(order);wrong['amount_total']=1;result=self.cli(order['id'],'reconcile',wrong);self.assertEqual(result['payment']['state'],'review')
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM business_events WHERE kind='PAYMENT_CONFIRMED'").fetchone()[0],0)
    def test_delivery_change_invalidates_shipping_offer_and_owner_boundaries(self):
        order,offer=self.approved_offer();other,_=self.h.account()
        self.post(other,'commerce-address',{'orderId':order['id'],'address':ADDRESS},404)
        self.post(self.h.customer,'commerce-address',{'orderId':order['id'],'address':{**ADDRESS,'state':'XX'}},422)
        result=self.post(self.h.customer,'commerce-address',{'orderId':order['id'],'address':{**ADDRESS,'postalCode':'91791'}});self.assertIsNone(result['commerce']['offer'])
    def test_invalid_webhook_signature_and_csrf_are_rejected(self):
        self.enable_test();status,raw,_=self.h.customer.raw('commerce-webhook',b'{}',{'Content-Type':'application/json','Stripe-Signature':'t=0,v1=fake'});self.assertEqual(status,400)
        status,_,_=self.h.customer.raw('commerce-address',b'{"orderId":"MLED-00000000000000000000"}',{'Content-Type':'application/json'});self.assertEqual(status,419)
        # A signed non-payment event is accepted and deduplicated without provider calls.
        body=json.dumps({'id':'evt_TESTONLY','type':'unrelated.event'}).encode();stamp=str(int(time.time()));sig=hmac.new(b'whsec_TESTONLY',stamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
        for _ in range(2):
            status,_,_=self.h.customer.raw('commerce-webhook',body,{'Content-Type':'application/json','Stripe-Signature':f't={stamp},v1={sig}'});self.assertEqual(status,200)
        self.assertEqual(self.db().execute('SELECT COUNT(*) FROM commerce_webhooks').fetchone()[0],1)
    def test_active_checkout_locks_price_proof_and_delivery(self):
        order,offer=self.approved_offer();self.enable_test();self.cli(order['id'])
        self.post(self.h.customer,'commerce-address',{'orderId':order['id'],'address':ADDRESS},409)
        self.post(self.h.staff,'business-proof',{'orderId':order['id'],'revision':order['revision']},409)

    def test_shipping_offer_versions_do_not_repeat_after_invalidation(self):
        order,offer=self.approved_offer()
        self.post(self.h.customer,'commerce-address',{'orderId':order['id'],'address':{**ADDRESS,'postalCode':'91791'}})
        next_offer=self.post(self.h.staff,'commerce-offer',{'orderId':order['id'],'proofId':order['proof']['id'],'shippingCents':3000,'productionMinDays':7,'productionMaxDays':14,'transitMinDays':2,'transitMaxDays':5,'fulfillmentConfirmed':True})['commerce']['offer']
        self.assertGreater(next_offer['version'],offer['version'])
        self.enable_test()
        self.post(self.h.customer,'commerce-checkout',{'orderId':order['id'],'offerVersion':offer['version'],'acceptTerms':True},409)

    def test_closed_premium_media_requires_separate_operator_activation(self):
        self.server.config.write_text(self.server.config.read_text().replace("'premium_enabled'=>true","'premium_enabled'=>false"))
        status,data,_=self.h.customer.json('library');self.assertEqual(status,403,data)
        self.assertFalse(self.h.customer.json('session')[1]['capabilities']['upload'])
