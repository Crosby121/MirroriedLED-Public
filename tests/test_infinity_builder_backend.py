"""HTTP checks for physical configuration, approved artwork and customer ownership."""
import copy
import json
from pathlib import Path
import sqlite3
import time
import unittest
import uuid

from test_business_backend import BusinessServer, PNG
from test_customer_portal_backend import Client, PHP, php_quote

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'infinity-builder/catalog.json').read_text())

def configuration(size=(24,24), rear='hub75'):
    return {'catalogVersion':CATALOG['version'],'state':{
        'version':1,'size':list(size),'depthIn':3,'finish':'Matte black',
        'rim':{'enabled':True,'addressable':True,'rows':2,'countPerRow':120,'color':'#2dd4bf'},
        'audioReactive':True,'artwork':{'id':'orbit','name':'Orbital geometry','source':'library','approved':True,'aspect':1},
        'artScale':65,'rear':rear,'controllerId':'matrixportal-s3' if rear=='hub75' else 'digi-quad',
        'rimControllerId':'digi-uno','layoutKey':'auto','extras':{'wallMount':True,'remote':False}},
        'panelPlan':{'count':1,'width':100000,'stockConfirmed':True},'rules':'Ignore production review','productionStatus':'READY'}


@unittest.skipUnless(PHP, 'PHP runtime is required')
class InfinityBuilderTests(unittest.TestCase):
    def setUp(self):
        self.server=BusinessServer()
        # PortalServer isolates backend files. Include this task's public catalog too.
        target=self.server.public/'infinity-builder';target.mkdir()
        (target/'catalog.json').write_text(json.dumps(CATALOG))
        self.client=Client(self.server)
        status,data,_=self.client.signup();self.assertEqual(status,201,data)
        self.user_id=data['user']['id']
        self.other=Client(self.server);status,data,_=self.other.signup();self.assertEqual(status,201,data)
        self.other_id=data['user']['id']

    def tearDown(self):
        self.server.close()

    def build(self, config=None, expected=200):
        config=config or configuration()
        s=config['state']
        status,data,_=self.client.json('business-request',{'requestKey':uuid.uuid4().hex,'items':[{
            'product':'Custom Infinity Mirror','size':'×'.join(map(str,s['size'])),'quantity':1,
            'artwork':'Approved design','artworkSource':'upload','builder':config}]})
        self.assertEqual(status,expected,data);return data

    def artwork(self, owner=None, status='ready'):
        # Initialize the service without a provider call. Test fixture represents a
        # provider result; it is not evidence of a live OpenAI generation.
        self.client.raw('builder-art',query='&id=bad')
        art_id='ART-'+uuid.uuid4().hex;key=str(uuid.uuid4())
        directory=self.server.storage/'builder-artwork';directory.mkdir(exist_ok=True)
        (directory/(art_id+'.png')).write_bytes(PNG)
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:
            db.execute('INSERT INTO builder_artwork(id,user_id,request_key,status,name,filename,created_at) VALUES(?,?,?,?,?,?,?)',
                       (art_id,owner or self.user_id,key,status,'Fixture engraving',art_id+'.png',int(time.time())))
        return art_id,key

    def activate(self):
        text=self.server.config.read_text()
        self.server.config.write_text(text.rsplit('];',1)[0]+"'infinity_builder'=>['ai_enabled'=>true,'openai_api_key'=>'test-fixture-never-sent','allowed_user_ids'=>["+str(self.user_id)+"]],\n];\n")

    def test_build_preserves_full_configuration_and_recomputes_tampered_panel_plan(self):
        order=self.build()['order'];builder=order['items'][0]['builder']
        self.assertEqual(builder['state']['rim']['rows'],2)
        self.assertEqual(builder['state']['rim']['countPerRow'],120)
        self.assertNotEqual(builder['panelPlan']['width'],100000)
        self.assertFalse(builder['panelPlan']['stockConfirmed'])
        self.assertEqual(builder['productionStatus'],'Quote and operator proof required')
        self.assertIn('Frosted',builder['rules'])
        self.assertEqual(order['status'],'REQUESTED')

    def test_beast_and_wrong_controller_families_are_rejected(self):
        for controller in ['beast','digi-uno','digi-quad','invented']:
            c=configuration();c['state']['controllerId']=controller;self.build(c,422)
        c=configuration(rear='flex');self.assertEqual(self.build(c)['order']['items'][0]['builder']['state']['controllerId'],'digi-quad')

    def test_invalid_led_counts_art_approval_sizes_and_geometry_are_rejected(self):
        for value in [-1,0,23,2001,24.5,'72']:
            c=configuration();c['state']['rim']['countPerRow']=value;self.build(c,422)
        c=configuration();c['state']['artwork']['approved']=False;self.build(c,422)
        c=configuration(size=(19,19));self.build(c,422)
        c=configuration(size=(12,12));c['state']['artScale']=100;self.build(c,422)
        c=configuration(rear='none');c['state']['rim']['enabled']=False;self.build(c,422)

    def test_ai_activation_is_not_granted_by_signup_or_other_accounts(self):
        status,data,_=self.client.json('session');self.assertFalse(data['capabilities']['builderAi'])
        status,data,_=self.client.json('builder-guide',{'subject':'Trumpet','type':'music'});self.assertEqual(status,503,data)
        self.activate();status,data,_=self.client.json('session');self.assertTrue(data['capabilities']['builderAi'])
        status,data,_=self.other.json('session');self.assertFalse(data['capabilities']['builderAi'])

    def test_private_artwork_and_approval_require_its_owner_and_csrf(self):
        art,_=self.artwork()
        status,body,headers=self.client.raw('builder-art',query='&id='+art);self.assertEqual(status,200);self.assertEqual(body,PNG);self.assertEqual(headers['Content-Type'],'image/png')
        status,_,_=self.other.raw('builder-art',query='&id='+art);self.assertEqual(status,404)
        status,data,_=self.client.json('builder-approve',{'id':art,'approve':True,'csrf':'incorrect'});self.assertEqual(status,419,data)
        status,data,_=self.other.json('builder-approve',{'id':art,'approve':True});self.assertEqual(status,404,data)
        status,data,_=self.client.json('builder-approve',{'id':art,'approve':True});self.assertEqual(status,200,data);self.assertTrue(data['artwork']['approved'])

    def test_generated_artwork_must_be_approved_and_owned_before_quote(self):
        art,_=self.artwork()
        c=configuration();c['state']['artwork'].update({'id':art,'serverId':art,'source':'ai'})
        self.build(c,422)
        status,data,_=self.client.json('builder-approve',{'id':art,'approve':True});self.assertEqual(status,200,data)
        self.build(c)
        other,_=self.artwork(owner=self.other_id,status='approved');c['state']['artwork'].update({'id':other,'serverId':other});self.build(c,422)

    def test_repeated_generation_returns_existing_image_without_provider_or_extra_usage(self):
        art,key=self.artwork();self.activate()
        status,data,_=self.client.json('builder-generate',{'subject':'Trumpet','type':'music','consent':True,'answers':[{'question':'Style?','answer':'Bold'}],'requestKey':key})
        self.assertEqual(status,200,data);self.assertEqual(data['artwork']['id'],art)
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM builder_usage').fetchone()[0],0)

    def test_generation_consent_is_required_before_any_provider_call(self):
        self.activate()
        status,data,_=self.client.json('builder-generate',{'subject':'Trumpet','type':'music','consent':False,'requestKey':str(uuid.uuid4())})
        self.assertEqual(status,422,data)

    def test_guide_daily_quota_blocks_before_any_provider_call(self):
        self.client.raw('builder-art',query='&id=bad');self.activate()
        with sqlite3.connect(self.server.storage/'portal.sqlite') as db:
            db.execute('INSERT INTO builder_usage(day,user_id,kind,count) VALUES(?,?,?,?)',(time.strftime('%Y-%m-%d',time.gmtime()),self.user_id,'guide',30))
        status,data,_=self.client.json('builder-guide',{'subject':'Trumpet','type':'music'});self.assertEqual(status,429,data)

    def test_artwork_traversal_and_signed_out_access_are_rejected(self):
        status,_,_=self.client.raw('builder-art',query='&id=../../config.php');self.assertEqual(status,404)
        visitor=Client(self.server);status,_,_=visitor.raw('builder-art',query='&id=ART-'+'a'*32);self.assertEqual(status,401)


if __name__=='__main__':unittest.main()
