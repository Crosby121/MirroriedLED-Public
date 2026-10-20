"""Staged mirror payments with an in-process provider double; no real charges/builds."""
import json
import copy
from pathlib import Path
import sqlite3
import subprocess
import time
import unittest
import test_commerce_backend as legacy
from test_customer_portal_backend import PHP,php_quote

@unittest.skipUnless(PHP,'PHP runtime required')
class StagedPaymentTests(unittest.TestCase):
    def setUp(self):
        self.c=legacy.CommerceTests();self.c.setUp();self.h=self.c.h;self.server=self.h.server
        self.c.enable_test()
    def tearDown(self):self.c.tearDown()
    def offer(self,product=15000,shipping=2000):
        order,terms=self.c.quoted()
        order=self.h.post(self.h.staff,'business-proof',{'orderId':order['id'],'revision':order['revision'],'fileId':order['proof']['file_id'],'quoteCents':product,'summary':'Confirmed mirror scope before deposit.'})['order']
        terms.update(proofId=order['proof']['id'],shippingCents=shipping)
        offer=self.h.post(self.h.staff,'commerce-offer',terms)['commerce']['offer']
        order=self.h.post(self.h.customer,'business-approve',{'orderId':order['id'],'revision':order['revision'],'proofId':order['proof']['id'],'acceptQuote':True})['order']
        return order,offer
    def db(self):return self.c.db()
    def cli(self,order,operation='commerce-checkout',session=None,expected=200,fail=False):
        source=self.server.public/'customer-portal/backend/portal.php'
        fixture=self.server.root/'stage-provider.json';fixture.write_text(json.dumps(session or {}))
        code="<?php require "+php_quote(str(source))+"; $config=require "+php_quote(str(self.server.config))+"; $db=new PDO('sqlite:'.$config['storage_path'].'/portal.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]); $user=$db->query('SELECT * FROM users WHERE id="+str(self.h.customer_id)+"')->fetch();"
        code+="$transport=function($method,$path,$params,$key) {file_put_contents("+php_quote(str(self.server.root/'stage-calls.jsonl'))+",json_encode([$method,$path,$params,$key]).PHP_EOL,FILE_APPEND); if($method==='GET')return json_decode(file_get_contents("+php_quote(str(fixture))+"),true); if($path==='/customers')return ['id'=>'cus_STAGE']; if($path==='/checkout/sessions'){"+("throw new RuntimeException('Timeout fixture');" if fail else '')+"return ['id'=>'cs_test_STAGE'.$params['metadata']['checkout_record'],'url'=>'https://checkout.stripe.com/c/pay/cs_test_STAGE'.$params['metadata']['checkout_record'],'expires_at'=>time()+3600];} throw new RuntimeException('Unexpected provider call');}; $service=new CommercePortal($db,$config,$user,$transport);"
        if operation=='reconcile':code+="$service->reconcile(json_decode(file_get_contents("+php_quote(str(fixture))+"),true));echo json_encode(CommercePortal::publicTerms($db,"+php_quote(order['id'])+"));"
        else:
            version=self.db().execute('SELECT version FROM commerce_offers WHERE order_id=?',(order['id'],)).fetchone()[0]
            code+="try{$service->handle("+php_quote(operation)+",['orderId'=>"+php_quote(order['id'])+",'offerVersion'=>"+str(version)+",'acceptTerms'=>true]);}catch(PortalError $e){echo json_encode(['httpStatus'=>$e->httpStatus,'error'=>$e->getMessage()]);}"
        script=self.server.root/'stage-action.php';script.write_text(code)
        r=subprocess.run([PHP,str(script)],capture_output=True,text=True)
        if fail:self.assertNotEqual(r.returncode,0);return
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);data=json.loads(r.stdout)
        self.assertEqual(data.get('httpStatus',200),expected,data);return data
    def row(self,order):
        db=self.db();db.row_factory=sqlite3.Row
        return dict(db.execute('SELECT * FROM commerce_checkouts WHERE order_id=? ORDER BY id DESC',(order['id'],)).fetchone())
    def canonical(self,order,status='paid'):
        r=self.row(order);s=json.loads(r['snapshot']);tax=round((s['productCents']+s['shippingCents'])*.09);total=s['productCents']+s['shippingCents']+tax
        result={'id':r['provider_id'],'mode':'payment','currency':'usd','livemode':s['mode']=='live','status':'complete','payment_status':status,'client_reference_id':order['id'],'metadata':{'order_id':order['id'],'checkout_record':str(r['id']),'proof_id':s['proofId']},'amount_subtotal':s['productCents'],'amount_total':total,'total_details':{'amount_shipping':s['shippingCents'],'amount_tax':tax,'amount_discount':0},'automatic_tax':{'status':'complete'},'line_items':{'data':[{'quantity':1,'amount_subtotal':s['productCents']}]},'payment_intent':{'id':'pi_STAGE'+str(r['id']),'status':'succeeded' if status=='paid' else 'processing','amount':total,'amount_received':total if status=='paid' else 0,'amount_capturable':0,'livemode':s['mode']=='live','currency':'usd','metadata':{'order_id':order['id']}}}
        result['metadata']['payment_stage']=s.get('paymentStage','full')
        if s.get('engravingReviewId'):result['metadata']['engraving_review']=s['engravingReviewId']
        return result
    def paid_deposit(self,product=15000,shipping=2000):
        o,offer=self.offer(product,shipping);self.cli(o);self.cli(o,'reconcile',self.canonical(o));return self.h.current(o),offer
    def building_fixture(self,order):
        # Simulates local build state only. Test payments never authorize real production.
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:db.execute("UPDATE business_orders SET status='BUILDING' WHERE id=?",(order['id'],))
        return self.h.current(order)
    def review(self,order,product=15000,shipping=2000,expected=200):
        photo=self.h.upload(self.h.staff,order,'engraving')['file']
        data=self.h.post(self.h.staff,'business-engraving-review',{'orderId':order['id'],'revision':order['revision'],'fileId':photo['id'],'summary':'Actual engraving and final price for customer review.','finalProductCents':product,'finalShippingCents':shipping},expected)
        return data.get('order')
    def approve(self,order,accept=True,expected=200):
        return self.h.post(self.h.customer,'business-engraving-approve',{'orderId':order['id'],'revision':order['revision'],'reviewId':order['engravingReview']['id'],'acceptEngraving':True,'acceptFinalPrice':accept},expected).get('order')
    def test_new_mirror_collects_half_product_plus_tax_and_defers_shipping(self):
        o,offer=self.offer();self.assertEqual(offer['paymentSchedule'],'deposit50');self.assertEqual(offer['depositProductCents'],7500)
        self.cli(o);s=json.loads(self.row(o)['snapshot']);self.assertEqual((s['paymentStage'],s['productCents'],s['shippingCents']),('deposit',7500,0))
        self.cli(o,'reconcile',self.canonical(o));p=self.h.current(o)['commerce']['installments']
        self.assertEqual(p['depositPaidCents'],8175);self.assertFalse(p['settled']);self.assertIsNone(p['shippingReadyAt'])
        self.cli(o,expected=409);self.assertEqual(self.db().execute('SELECT COUNT(*) FROM commerce_checkouts').fetchone()[0],1)
    def test_final_price_and_engraving_must_be_approved_before_balance(self):
        o,_=self.paid_deposit();o=self.building_fixture(o);o=self.review(o,16000,2500)
        self.cli(o,expected=409);self.approve(o,False,422)
        o=self.approve(o);p=o['commerce']['installments'];self.assertEqual(p['balanceBeforeTaxCents'],11000);self.assertTrue(p['finalPriceApproved'])
        self.assertIsNone(o['engravingReview']['ship_by_date'])
        self.cli(o);s=json.loads(self.row(o)['snapshot']);self.assertEqual((s['paymentStage'],s['productCents'],s['shippingCents']),('balance',8500,2500))
        self.cli(o,'reconcile',self.canonical(o));o=self.h.current(o);p=o['commerce']['installments']
        self.assertTrue(p['settled']);self.assertIsNotNone(p['shippingReadyAt']);self.assertIsNotNone(o['engravingReview']['ship_by_date'])
        self.assertEqual(o['quoteCents'],15000) # Initial quote remains immutable.
        self.cli(o,expected=409)
    def test_processing_balance_is_refreshed_instead_of_paid_deposit(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o)
        session=self.canonical(o,'unpaid');self.cli(o,'reconcile',session)
        p=self.cli(o,'commerce-refresh',session)['commerce']['installments'];self.assertEqual(p['balance']['state'],'processing');self.assertFalse(p['settled'])
        calls=[json.loads(x) for x in (self.server.root/'stage-calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls[-1][1],'/checkout/sessions/'+session['id'])
    def test_active_balance_locks_photo_and_final_price(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o)
        self.review(o,18000,2000,409)
    def test_odd_cent_rounding_and_zero_balance_do_not_create_another_charge(self):
        o,_=self.paid_deposit(15001,0);self.assertEqual(json.loads(self.row(o)['snapshot'])['productCents'],7501)
        o=self.building_fixture(o);self.review(o,7500,0,422)
        o=self.approve(self.review(o,7501,0));p=o['commerce']['installments'];self.assertTrue(p['settled']);self.assertEqual(p['balanceBeforeTaxCents'],0)
        self.cli(o,expected=409);self.assertEqual(self.db().execute('SELECT COUNT(*) FROM commerce_checkouts').fetchone()[0],1)
    def test_balance_timeout_reuses_identical_provider_parameters(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o,fail=True);self.cli(o)
        calls=[json.loads(x) for x in (self.server.root/'stage-calls.jsonl').read_text().splitlines()]
        sessions=[c for c in calls if c[1]=='/checkout/sessions'];self.assertEqual(sessions[-2],sessions[-1])
    def test_unexpanded_or_forged_deposit_never_becomes_verified_money(self):
        o,_=self.offer();self.cli(o);s=self.canonical(o);s['payment_intent']='pi_UNEXPANDED';self.cli(o,'reconcile',s)
        self.assertEqual(self.row(o)['state'],'review');self.assertFalse(self.h.current(o)['commerce']['installments']['settled'])

    def test_wrong_stage_on_unpaid_session_is_held_for_review(self):
        o,_=self.offer();self.cli(o);s=self.canonical(o,'unpaid');s['metadata']['payment_stage']='balance';self.cli(o,'reconcile',s)
        self.assertEqual(self.row(o)['state'],'review')

    def test_late_paid_balance_for_superseded_photo_cannot_release_shipping(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o);old=self.canonical(o)
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:db.execute("UPDATE commerce_checkouts SET state='expired' WHERE provider_id=?",(old['id'],))
        o=self.review(self.h.current(o),15500,2500);o=self.approve(o)
        self.cli(o,'reconcile',old);p=self.h.current(o)['commerce']['installments'];self.assertTrue(p['hasPaymentReview']);self.assertFalse(p['settled']);self.assertIsNone(p['shippingReadyAt'])

    def test_test_payment_cannot_authorize_production_even_after_deposit(self):
        o,_=self.paid_deposit();stock,_=self.h.receipt();o=self.h.reserved(o,stock)
        file=self.h.upload(self.h.staff,o,'production','layout.lbrn2',__import__('test_business_backend').LBRN)['file']
        self.h.post(self.h.staff,'business-release',self.h.release_data(o,file['id']),409)

    def test_verified_live_fixture_deposit_releases_but_balance_blocks_shipping(self):
        # Provider transport remains the deterministic in-process fixture for ALL calls.
        config=self.server.config.read_text().replace("'mode'=>'test'","'mode'=>'live'").replace('sk_test_TESTONLY','sk_live_TESTONLY');self.server.config.write_text(config)
        o,_=self.paid_deposit();stock,_=self.h.receipt();o=self.h.reserved(o,stock)
        file=self.h.upload(self.h.staff,o,'production','layout.lbrn2',__import__('test_business_backend').LBRN)['file']
        o=self.h.post(self.h.staff,'business-release',self.h.release_data(o,file['id']))['order']
        o=self.h.post(self.h.staff,'business-build',{'orderId':o['id'],'revision':o['revision']})['order']
        o=self.approve(self.review(o));checks={k:True for k in ['dimensions','finish','electrical','function']}
        o=self.h.post(self.h.staff,'business-qc',{'orderId':o['id'],'revision':o['revision'],'passed':True,'note':'Fixture QC only.','checks':checks})['order']
        data={'orderId':o['id'],'revision':o['revision'],'carrier':'Test fixture','tracking':'FIXTURE','note':'No real shipment.'}
        self.h.post(self.h.staff,'business-fulfill',data,409)
        self.cli(o);self.cli(o,'reconcile',self.canonical(o));o=self.h.current(o)
        p=o['commerce']['installments'];self.assertTrue(p['livePaymentsVerified']);self.assertGreaterEqual(p['shippingReadyAt'],o['engravingReview']['approved_at'])
        shipped=self.h.post(self.h.staff,'business-fulfill',{**data,'revision':o['revision']})['order'];self.assertEqual(shipped['status'],'FULFILLING')

    def test_subminimum_balance_is_not_silently_rounded_up(self):
        o,_=self.paid_deposit();o=self.building_fixture(o);self.review(o,7501,0,422)

    def test_production_role_cannot_change_sales_price_without_sales_authority(self):
        o,_=self.paid_deposit();o=self.building_fixture(o)
        self.server.roles[self.h.staff_id]=['production'];self.server.write_config()
        self.review(o,18000,2000,403)
        self.assertIsNotNone(self.review(o,15000,2000)['engravingReview'])

    def test_stale_approval_cannot_accept_a_revised_final_price(self):
        o,_=self.paid_deposit();o=self.review(self.building_fixture(o));old=o
        current=self.review(o,18000,2500)
        self.approve(old,expected=409)
        self.assertFalse(current['commerce']['installments']['finalPriceApproved'])

    def test_ship_by_uses_final_payment_time_after_earlier_approval(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)))
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:db.execute('UPDATE business_engraving_reviews SET approved_at=? WHERE id=?',(int(time.time())-7*86400,o['engravingReview']['id']))
        self.cli(o);self.cli(o,'reconcile',self.canonical(o));o=self.h.current(o);p=o['commerce']['installments']
        self.assertEqual(p['shippingReadyAt'],p['balance']['paid_at'])
        self.assertGreater(p['shippingReadyAt'],o['engravingReview']['approved_at'])

    def failed(self,session):
        failed=copy.deepcopy(session);failed['payment_status']='unpaid'
        failed['payment_intent'].update(status='requires_payment_method',amount_received=0,amount_capturable=0,last_payment_error={'code':'declined'})
        return failed

    def test_late_balance_success_holds_open_retry_then_refresh_expiry_clears_it(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o);old=self.canonical(o)
        self.cli(o,'reconcile',self.failed(old));self.cli(o);retry=self.canonical(o,'unpaid')
        self.cli(o,'reconcile',old);o=self.h.current(o);p=o['commerce']['installments']
        self.assertTrue(p['hasPaymentReview']);self.assertFalse(p['settled']);self.assertIsNone(p['shippingReadyAt']);self.assertIsNone(o['engravingReview']['ship_by_date'])
        retry['status']='expired';p=self.cli(o,'commerce-refresh',retry)['commerce']['installments']
        self.assertFalse(p['hasPaymentReview']);self.assertTrue(p['settled']);self.assertIsNotNone(self.h.current(o)['engravingReview']['ship_by_date'])

    def test_late_deposit_success_holds_processing_retry_and_production(self):
        o,_=self.offer();self.cli(o);old=self.canonical(o)
        self.cli(o,'reconcile',self.failed(old));self.cli(o);retry=self.canonical(o,'unpaid');self.cli(o,'reconcile',retry)
        self.cli(o,'reconcile',old);p=self.h.current(o)['commerce']['installments'];self.assertTrue(p['hasPaymentReview'])
        o=self.building_fixture(o);self.review(o,expected=409)

    def test_refresh_finds_older_unresolved_balance_after_a_later_attempt_paid(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o);old=self.canonical(o)
        self.cli(o,'reconcile',self.failed(old));self.cli(o);later=self.canonical(o)
        # Exercise an unresolved older provider attempt after a reconciliation race/repair.
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:db.execute("UPDATE commerce_checkouts SET state='processing' WHERE provider_id=?",(old['id'],))
        self.cli(o,'reconcile',later);self.assertFalse(self.h.current(o)['commerce']['installments']['settled'])
        expired=self.failed(old);expired['status']='expired'
        p=self.cli(o,'commerce-refresh',expired)['commerce']['installments'];self.assertTrue(p['settled'])
        calls=[json.loads(x) for x in (self.server.root/'stage-calls.jsonl').read_text().splitlines()]
        self.assertEqual(calls[-1][1],'/checkout/sessions/'+old['id'])

    def test_two_paid_balances_stay_held_for_support_review(self):
        o,_=self.paid_deposit();o=self.approve(self.review(self.building_fixture(o)));self.cli(o);old=self.canonical(o)
        self.cli(o,'reconcile',self.failed(old));self.cli(o);later=self.canonical(o)
        self.cli(o,'reconcile',old);self.cli(o,'reconcile',later)
        p=self.h.current(o)['commerce']['installments'];self.assertTrue(p['hasPaymentReview']);self.assertFalse(p['settled']);self.assertIsNone(p['shippingReadyAt'])

if __name__=='__main__':unittest.main()
