"""HTTP tests for real business records, private files and production prerequisites."""
from __future__ import annotations

import base64
import json
import sqlite3
import subprocess
import time
import unittest
import uuid

from test_customer_portal_backend import Client, PHP, PortalServer, php_quote


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ioAAAAASUVORK5CYII=')
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"><rect width="50" height="50"/></svg>'
LBRN = b'<?xml version="1.0"?><LightBurnProject AppVersion="1.7"><Notes>Test fixture; not a machine job</Notes></LightBurnProject>'


class BusinessServer(PortalServer):
    def __init__(self, enabled=True, **kwargs):
        super().__init__(**kwargs)
        self.base_config = self.config.read_text()
        self.enabled = enabled
        self.roles = {}
        self.write_config()

    def write_config(self):
        roles = ','.join(f"{user}=>[" + ','.join(php_quote(role) for role in values) + ']' for user, values in self.roles.items())
        self.config.write_text(self.base_config.rsplit('];', 1)[0] + f"'business_enabled'=>{'true' if self.enabled else 'false'},\n'staff_users'=>[{roles}],\n];\n")


@unittest.skipUnless(PHP, 'PHP runtime is required')
class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.server = BusinessServer()
        self.customer, self.customer_id = self.account()
        self.staff, self.staff_id = self.account()
        self.server.roles[self.staff_id] = ['admin']
        self.server.write_config()

    def test_fixture_config_changes_are_visible_without_cache_delay(self):
        self.server.enabled = False
        self.server.write_config()
        self.post(self.customer, 'business-request', {'items': []}, 503)
        self.server.enabled = True
        self.server.write_config()
        self.assertEqual(self.request()['status'], 'REQUESTED')

    def tearDown(self):
        self.server.close()

    def account(self):
        client = Client(self.server)
        status, data, _ = client.signup()
        self.assertEqual(status, 201, data)
        return client, data['user']['id']

    def post(self, client, action, data, expected=200, key=None):
        status, result, _ = client.json(action, {'requestKey': key or uuid.uuid4().hex, **data})
        self.assertEqual(status, expected, result)
        return result

    def request(self, customer=None, artwork_source='team-design'):
        return self.post(customer or self.customer, 'business-request', {'items': [{
            'product':'Custom Infinity Mirror', 'size':'24×24', 'quantity':1,
            'artwork':'Frosted blue logo', 'artworkSource':artwork_source, 'lighting':'WLED',
            'price':1, 'status':'COMPLETED', 'roles':['admin'],
        }]})['order']

    def dashboard(self):
        status, data, _ = self.staff.json('business-dashboard')
        self.assertEqual(status,200,data)
        return data

    def current(self, order):
        return next(item for item in self.dashboard()['orders'] if item['id'] == order['id'])

    def upload(self, client, order, purpose='artwork', name='artwork.png', content=PNG, expected=200, key=None):
        boundary='mled'+uuid.uuid4().hex
        fields={'csrf':client.csrf,'requestKey':key or uuid.uuid4().hex,'orderId':order['id'],'purpose':purpose}
        parts=[]
        for name_field,value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name_field}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+content+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        status,raw,_=client.raw('business-upload',b''.join(parts),{'Content-Type':'multipart/form-data; boundary='+boundary})
        data=json.loads(raw);self.assertEqual(status,expected,data);return data

    def quoted(self, customer=None):
        order=self.request(customer)
        file=self.upload(self.staff,order,'proof')['file']
        return self.post(self.staff,'business-proof',{'orderId':order['id'],'revision':order['revision'],'fileId':file['id'],'quoteCents':35000,'summary':'24×24 mirror; diffused logo; black frame; installation by quote.'})['order']

    def approved(self, customer=None):
        order=self.quoted(customer)
        return self.post(customer or self.customer,'business-approve',{'orderId':order['id'],'revision':order['revision'],'proofId':order['proof']['id'],'acceptQuote':True})['order']

    def receipt(self, quality='PASSED', quantity='10', sku=None):
        sku=sku or uuid.uuid4().hex[:12]
        data={'sku':sku,'name':'Inspected mirror','lot':'LOT-'+sku,'location':'Shelf A','unit':'pieces','quantity':quantity,'threshold':'2','costCents':1800,'quality':quality}
        stock=self.post(self.staff,'business-receive',data)['stock']
        return next(item for item in stock if item['sku']==sku),data

    def reserved(self, order, stock, quantity='1'):
        order=self.current(order)
        return self.post(self.staff,'business-reserve',{'orderId':order['id'],'revision':order['revision'],'stockId':stock['id'],'quantity':quantity})['order']

    def release_data(self, order, file_id, machine=None):
        return {'orderId':order['id'],'revision':order['revision'],'fileId':file_id,
                'financeReference':'Test manual release record; no payment captured',
                'materialsComplete':True,'assetReviewed':True,'machine':machine or uuid.uuid4().hex,
                'scheduledAt':int(time.time())+60,'minutes':60}

    def ready(self, machine=None):
        order=self.approved()
        stock,_=self.receipt()
        order=self.reserved(order,stock)
        file=self.upload(self.staff,order,'production','layout.lbrn2',LBRN)['file']
        data=self.release_data(order,file['id'],machine)
        result=self.post(self.staff,'business-release',data)
        self.assertFalse(result['physicalExecution'])
        return result['order'],stock,data

    def test_requests_are_owner_scoped_and_ignore_client_authority(self):
        order=self.request()
        self.assertEqual(order['status'],'REQUESTED')
        self.assertIsNone(order['quoteCents'])
        self.assertNotIn('roles',order['items'][0])
        other,_=self.account()
        self.assertEqual(other.json('business-orders')[1]['orders'],[])
        self.post(other,'business-approve',{'orderId':order['id'],'revision':1,'proofId':'fake','acceptQuote':True},404)
        self.post(self.customer,'business-receive',{},403)
        self.assertEqual(self.customer.json('business-dashboard')[0],403)

    def test_request_idempotency_and_conflicting_reuse(self):
        key=uuid.uuid4().hex
        payload={'items':[{'product':'Address Sign or Mailbox','size':'House Sign','artwork':'12345','quantity':1}]}
        first=self.post(self.customer,'business-request',payload,key=key)
        second=self.post(self.customer,'business-request',payload,key=key)
        self.assertEqual(first['order']['id'],second['order']['id'])
        payload['items'][0]['artwork']='Different'
        self.post(self.customer,'business-request',payload,409,key=key)
        self.assertEqual(len(self.customer.json('business-orders')[1]['orders']),1)

    def test_private_artwork_download_and_cross_customer_denial(self):
        order=self.request(artwork_source='upload')
        file=self.upload(self.customer,order)['file']
        status,body,headers=self.customer.raw('business-file',query='&id='+file['id'])
        self.assertEqual(status,200);self.assertEqual(body,PNG)
        self.assertTrue(headers['Content-Disposition'].startswith('attachment'))
        other,_=self.account()
        self.assertEqual(other.raw('business-file',query='&id='+file['id'])[0],404)
        self.assertEqual(self.customer.raw('business-file',query='&id=../../config.php')[0],404)
        self.upload(other,order,expected=404)
        self.upload(self.customer,order,'proof',expected=403)
        self.assertFalse((self.server.public/'business-files').exists())

    def test_uploaded_artwork_types_and_xml_boundary(self):
        order=self.request()
        self.upload(self.customer,order,name='image.php.png',expected=422)
        self.upload(self.customer,order,name='image.png',content=b'<?php echo 1;',expected=422)
        self.upload(self.customer,order,name='drawing.svg',content=b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg/>',expected=422)
        file=self.upload(self.customer,order,name='drawing.svg',content=SVG)['file']
        status,body,headers=self.customer.raw('business-file',query='&id='+file['id'])
        self.assertEqual(status,200);self.assertEqual(body,SVG)
        self.assertEqual(headers['Content-Security-Policy'],'sandbox')
        self.upload(self.staff,order,'production','layout.lbrn2',b'<invalid/>',expected=422)

    def test_current_proof_revision_and_approval_are_required(self):
        first=self.quoted()
        file=self.upload(self.staff,first,'proof')['file']
        second=self.post(self.staff,'business-proof',{'orderId':first['id'],'revision':first['revision'],'fileId':file['id'],'quoteCents':40000,'summary':'Revised proof and amount.'})['order']
        self.post(self.customer,'business-approve',{'orderId':first['id'],'revision':first['revision'],'proofId':first['proof']['id'],'acceptQuote':True},409)
        self.post(self.customer,'business-approve',{'orderId':second['id'],'revision':second['revision'],'proofId':second['proof']['id'],'acceptQuote':False},422)
        approved=self.post(self.customer,'business-approve',{'orderId':second['id'],'revision':second['revision'],'proofId':second['proof']['id'],'acceptQuote':True})['order']
        self.assertEqual(approved['status'],'APPROVED')
        self.assertEqual(approved['quoteCents'],40000)
        self.upload(self.customer,approved,expected=409)

    def test_quarantine_and_over_reservation_are_blocked(self):
        order=self.approved()
        stock,_=self.receipt('QUARANTINED')
        self.post(self.staff,'business-reserve',{'orderId':order['id'],'revision':order['revision'],'stockId':stock['id'],'quantity':'1'},409)
        inspected,_=self.receipt(quantity='1')
        order=self.reserved(order,inspected)
        second=self.approved()
        self.post(self.staff,'business-reserve',{'orderId':second['id'],'revision':second['revision'],'stockId':inspected['id'],'quantity':'1'},409)
        self.assertEqual(self.current(order)['reservations'][0]['quantity'],1000)

    def test_release_requires_proof_materials_reviewed_file_and_reference(self):
        order=self.approved()
        file=self.upload(self.staff,order,'production','layout.svg',SVG)['file']
        data=self.release_data(order,file['id'])
        self.post(self.staff,'business-release',data,409)
        stock,_=self.receipt();order=self.reserved(order,stock);data=self.release_data(order,file['id'])
        self.post(self.staff,'business-release',{**data,'assetReviewed':False},409)
        self.post(self.staff,'business-release',{**data,'financeReference':''},422)
        self.assertEqual(self.current(order)['status'],'APPROVED')

    def test_schedule_collision_and_start_consumption_are_transactional(self):
        machine=uuid.uuid4().hex
        order,stock,_=self.ready(machine)
        second=self.approved();second=self.reserved(second,stock)
        file=self.upload(self.staff,second,'production','layout.svg',SVG)['file']
        self.post(self.staff,'business-release',self.release_data(second,file['id'],machine),409)
        key=uuid.uuid4().hex;payload={'orderId':order['id'],'revision':order['revision']}
        first=self.post(self.staff,'business-build',payload,key=key)
        replay=self.post(self.staff,'business-build',payload,key=key)
        self.assertFalse(first['physicalExecution']);self.assertEqual(first,replay)
        self.post(self.staff,'business-build',payload,409)
        current_stock=next(s for s in self.dashboard()['stock'] if s['id']==stock['id'])
        self.assertEqual(current_stock['quantity'],9000)
        self.assertEqual(current_stock['reserved'],1000)

    def test_qc_hold_cannot_skip_to_fulfillment_and_pass_needs_checks(self):
        order,_,_=self.ready()
        order=self.post(self.staff,'business-build',{'orderId':order['id'],'revision':order['revision']})['order']
        self.post(self.staff,'business-qc',{'orderId':order['id'],'revision':order['revision'],'passed':True,'note':'Missing evidence','checks':{}},409)
        hold=self.post(self.staff,'business-qc',{'orderId':order['id'],'revision':order['revision'],'passed':False,'note':'Diffusion requires rework.'})['order']
        self.post(self.staff,'business-fulfill',{'orderId':hold['id'],'revision':hold['revision'],'carrier':'Pickup','tracking':'P1','note':'Testing'},409)
        self.assertTrue(any(t['kind']=='QC_REVIEW' and t['state']=='OPEN' for t in self.dashboard()['tasks']))
        checks={k:True for k in ['dimensions','finish','electrical','function']}
        passed=self.post(self.staff,'business-qc',{'orderId':hold['id'],'revision':hold['revision'],'passed':True,'note':'Inspection log TEST-1; all checks passed.','checks':checks})['order']
        self.post(self.staff,'business-fulfill',{'orderId':passed['id'],'revision':passed['revision'],'carrier':'Pickup','tracking':'P1','note':'Must wait for customer engraving approval.'},409)
        passed=self.approve_engraving(self.publish_engraving(passed))
        shipped=self.post(self.staff,'business-fulfill',{'orderId':passed['id'],'revision':passed['revision'],'carrier':'Customer pickup','tracking':'PICKUP-1','note':'Ready for agreed pickup.'})['order']
        complete=self.post(self.staff,'business-fulfill',{'orderId':shipped['id'],'revision':shipped['revision'],'carrier':'Customer pickup','tracking':'PICKUP-1','note':'Test pickup recorded.','complete':True})['order']
        self.assertEqual(complete['status'],'COMPLETED')

    def building(self):
        order,_,_=self.ready()
        return self.post(self.staff,'business-build',{'orderId':order['id'],'revision':order['revision']})['order']

    def publish_engraving(self, order):
        file=self.upload(self.staff,order,'engraving','finished-mirror.png')['file']
        return self.post(self.staff,'business-engraving-review',{'orderId':order['id'],'revision':order['revision'],'fileId':file['id'],'summary':'Photo of the actual finished engraving. Please check its lettering and placement.'})['order']

    def approve_engraving(self, order):
        return self.post(self.customer,'business-engraving-approve',{'orderId':order['id'],'revision':order['revision'],'reviewId':order['engravingReview']['id'],'acceptEngraving':True})['order']

    def test_finished_engraving_is_separate_private_and_owner_approved(self):
        order=self.building()
        self.assertTrue(order['engravingApprovalRequired'])
        self.assertIsNone(order['engravingReview'])
        self.assertIsNotNone(order['approvedProofId'])
        self.upload(self.customer,order,'engraving',expected=403)
        self.upload(self.staff,order,'engraving','photo.svg',SVG,expected=422)
        review=self.publish_engraving(order)
        photo=review['engravingReview']['file_id']
        other,_=self.account()
        self.assertEqual(other.raw('business-file',query='&id='+photo)[0],404)
        status,body,headers=self.customer.raw('business-file',query='&id='+photo)
        self.assertEqual(status,200);self.assertEqual(body,PNG)
        self.assertTrue(headers['Content-Disposition'].startswith('inline'))
        payload={'orderId':order['id'],'revision':review['revision'],'reviewId':review['engravingReview']['id'],'acceptEngraving':True}
        self.post(other,'business-engraving-approve',payload,404)
        self.post(self.staff,'business-engraving-approve',payload,404)
        self.post(self.customer,'business-engraving-approve',{**payload,'acceptEngraving':False},422)
        self.post(self.customer,'business-engraving-approve',{**payload,'csrf':'wrong'},419)
        key=uuid.uuid4().hex
        approved=self.post(self.customer,'business-engraving-approve',payload,key=key)
        self.assertEqual(approved,self.post(self.customer,'business-engraving-approve',payload,key=key))
        saved=approved['order']['engravingReview']
        self.assertIsNotNone(saved['approved_at']);self.assertRegex(saved['ship_by_date'],r'^\d{4}-\d{2}-\d{2}$')
        self.assertEqual(saved['timezone'],'America/Los_Angeles')
        self.assertEqual(approved['order']['approvedProofId'],order['approvedProofId'])
        self.post(self.staff,'business-fulfill',{'orderId':order['id'],'revision':approved['order']['revision'],'carrier':'Test','tracking':'T1','note':'QC still required.'},409)

    def test_revised_engraving_requires_fresh_approval_and_latest_revision(self):
        first=self.publish_engraving(self.building())
        approved=self.approve_engraving(first)
        revised=self.publish_engraving(approved)
        self.assertEqual(revised['engravingReview']['version'],2)
        self.assertIsNone(revised['engravingReview']['approved_at'])
        self.assertIsNone(revised['engravingReview']['ship_by_date'])
        self.post(self.customer,'business-engraving-approve',{'orderId':revised['id'],'revision':revised['revision'],'reviewId':first['engravingReview']['id'],'acceptEngraving':True},409)
        self.post(self.customer,'business-engraving-approve',{'orderId':revised['id'],'revision':first['revision'],'reviewId':revised['engravingReview']['id'],'acceptEngraving':True},409)
        checks={k:True for k in ['dimensions','finish','electrical','function']}
        passed=self.post(self.staff,'business-qc',{'orderId':revised['id'],'revision':revised['revision'],'passed':True,'note':'Inspection passed.','checks':checks})['order']
        self.post(self.staff,'business-fulfill',{'orderId':passed['id'],'revision':passed['revision'],'carrier':'Test','tracking':'T1','note':'Old approval must not release shipment.'},409)
        passed=self.approve_engraving(passed)
        shipped=self.post(self.staff,'business-fulfill',{'orderId':passed['id'],'revision':passed['revision'],'carrier':'Test','tracking':'T1','note':'Customer approved current actual engraving.'})['order']
        self.upload(self.staff,shipped,'engraving',expected=409)
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM business_engraving_reviews WHERE order_id=? AND approved_at IS NOT NULL',(passed['id'],)).fetchone()[0],2)

    def test_engraving_cannot_be_published_before_production_or_by_sales(self):
        order=self.approved()
        self.upload(self.staff,order,'engraving',expected=409)
        order=self.building()
        photo=self.upload(self.staff,order,'engraving')['file']
        self.server.roles[self.staff_id]=['sales'];self.server.write_config()
        self.post(self.staff,'business-engraving-review',{'orderId':order['id'],'revision':order['revision'],'fileId':photo['id'],'summary':'Not production staff'},403)

    def test_dispatch_deadline_uses_three_weekdays_in_pacific_time_across_dst(self):
        script="require "+php_quote(str(__import__('pathlib').Path(__file__).resolve().parents[1]/'customer-portal/backend/business.php'))+"; foreach (['2026-10-23T23:30:00-07:00','2026-10-31T23:30:00-07:00','2026-11-02T01:00:00Z','2026-10-19T12:00:00-07:00'] as $at) echo BusinessPortal::engravingShipBy((new DateTimeImmutable($at))->getTimestamp()).PHP_EOL;"
        result=subprocess.run([PHP,'-r',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['2026-10-28','2026-11-04','2026-11-04','2026-10-22'])

    def test_dispatch_excludes_observed_federal_holidays_across_year_boundary(self):
        script="require "+php_quote(str(__import__('pathlib').Path(__file__).resolve().parents[1]/'customer-portal/backend/business.php'))+"; foreach (['2026-11-10T12:00:00-08:00','2026-11-25T12:00:00-08:00','2026-07-02T12:00:00-07:00','2027-12-29T12:00:00-08:00'] as $at) echo BusinessPortal::engravingShipBy((new DateTimeImmutable($at))->getTimestamp()).PHP_EOL;"
        result=subprocess.run([PHP,'-r',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stdout.splitlines(),['2026-11-16','2026-12-01','2026-07-08','2028-01-04'])

    def test_late_shipment_can_be_recorded_without_rewriting_approval(self):
        order=self.approve_engraving(self.publish_engraving(self.building()))
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:
            db.execute("UPDATE business_engraving_reviews SET approved_at=1600000000,ship_by_date='2020-09-17' WHERE order_id=?",(order['id'],))
        checks={k:True for k in ['dimensions','finish','electrical','function']}
        order=self.post(self.staff,'business-qc',{'orderId':order['id'],'revision':order['revision'],'passed':True,'note':'Inspection passed.','checks':checks})['order']
        task=next(t for t in self.dashboard()['tasks'] if t['reference']==order['id'] and t['kind']=='FULFILLMENT')
        self.assertIn('2020-09-17',task['title'])
        shipped=self.post(self.staff,'business-fulfill',{'orderId':order['id'],'revision':order['revision'],'carrier':'Test','tracking':'T1','note':'Late shipment recorded truthfully.'})['order']
        self.assertEqual(shipped['engravingReview']['approved_at'],1600000000)
        self.assertEqual(shipped['engravingReview']['ship_by_date'],'2020-09-17')

    def test_cancel_releases_materials_and_records_customer_update(self):
        order=self.approved();stock,_=self.receipt(quantity='1');order=self.reserved(order,stock)
        self.post(self.staff,'business-cancel',{'orderId':order['id'],'revision':order['revision'],'note':'Customer requested cancellation.'})
        current_stock=next(s for s in self.dashboard()['stock'] if s['id']==stock['id'])
        self.assertEqual(current_stock['quantity'],1000);self.assertEqual(current_stock['reserved'],0)
        updates=self.customer.json('business-updates')[1]['updates']
        self.assertTrue(any(u['kind']=='CANCELLED' for u in updates))

    def test_support_conversations_are_private_and_warranty_is_review_only(self):
        order=self.request();other,_=self.account()
        self.post(other,'business-ticket',{'orderId':order['id'],'kind':'WARRANTY','subject':'Question','body':'Warranty request.'},404)
        ticket=self.post(self.customer,'business-ticket',{'orderId':order['id'],'kind':'WARRANTY','subject':'Warranty question','body':'Please review the product.'})['ticketId']
        self.post(other,'business-reply',{'ticketId':ticket,'body':'Attempt to access'},403)
        self.post(self.customer,'business-reply',{'ticketId':ticket,'body':'Please close','close':True},403)
        self.post(self.staff,'business-reply',{'ticketId':ticket,'body':'Team response recorded.','close':True})
        result=self.customer.json('business-tickets')[1]['tickets'][0]
        self.assertEqual(result['state'],'CLOSED');self.assertEqual(result['messages'][-1]['sender'],'TEAM')
        self.assertEqual(other.json('business-tickets')[1]['tickets'],[])

    def test_csrf_roles_and_unconfigured_business_are_enforced(self):
        self.assertEqual(self.customer.json('business-request',{'requestKey':uuid.uuid4().hex,'csrf':'wrong','items':[]})[0],419)
        self.assertEqual(self.customer.json('business-request',{'requestKey':uuid.uuid4().hex,'items':[]},headers={'Origin':'https://untrusted.example'})[0],403)
        self.server.roles[self.staff_id]=['inventory'];self.server.write_config()
        order=self.request()
        self.post(self.staff,'business-proof',{'orderId':order['id'],'revision':1},403)
        self.server.enabled=False;self.server.write_config()
        self.assertFalse(self.customer.json('session')[1]['capabilities']['business'])
        self.assertEqual(self.customer.json('business-orders')[0],503)

    def test_stadium_has_only_three_sizes_and_quantities_are_server_validated(self):
        for size in ['Custom','Mid','Huge']:
            self.post(self.staff,'business-request',{'items':[{'product':'Layered Stadium Model','size':size,'artwork':'Venue','quantity':1}]},422)
        for size in ['Mini','Medium','Collector']:
            self.post(self.staff,'business-request',{'items':[{'product':'Layered Stadium Model','size':size,'artwork':'Venue','quantity':1}]})
        self.post(self.staff,'business-request',{'items':[{'product':'Other Custom Build','size':'Custom','artwork':'Theme','quantity':-2}]},422)


if __name__ == '__main__':
    unittest.main()
