const {test}=require('node:test');
const assert=require('node:assert/strict');
const E=require('../infinity-builder/engine.js');
const catalog=require('../infinity-builder/catalog.json');
function state(size=[24,24],rear='hub75',aspect=1,scale=65){const s=E.initial(catalog);s.size=size;s.rear=rear;s.artScale=scale;s.artwork={id:'orbit',name:'Orbital geometry',source:'library',approved:true,aspect};return s;}
test('three rim rows count separately and add an audio source only when selected',()=>{const s=state();s.rim.rows=3;s.rim.countPerRow=120;s.audioReactive=true;const p=E.plan(s,catalog);assert.equal(p.rimPixels,360);assert.ok(p.hardware.some(h=>h.id==='audio'));assert.ok(p.hardware.some(h=>h.id==='rim-controller'));s.audioReactive=false;assert.ok(!E.plan(s,catalog).hardware.some(h=>h.id==='audio'));});
test('all suggested layouts cover the engraving and physically fit inside each supported mirror',()=>{for(const size of catalog.sizes)for(const family of ['flex','hub75'])for(const aspect of [.4,1,2.5])for(const scale of [20,50,100]){const s=state(size,family,aspect,scale),box=E.artBox(s,catalog),room=E.interior(s,catalog);for(const p of E.candidates(s,catalog)){assert.ok(p.width+1e-7>=box.width);assert.ok(p.height+1e-7>=box.height);assert.ok(p.width<=room.width+1e-7);assert.ok(p.height<=room.height+1e-7);assert.equal(p.cells.length,p.count);for(const c of p.cells){assert.ok(c.x>=room.x-1e-7);assert.ok(c.y>=room.y-1e-7);assert.ok(c.x+c.width<=room.x+room.width+1e-7);assert.ok(c.y+c.height<=room.y+room.height+1e-7);}}}});
test('panel ranking minimizes unused area and checks both panel orientations',()=>{const s=state([20,20],'hub75',.45,55),ps=E.candidates(s,catalog);assert.ok(ps.length>0);assert.ok(ps.some(p=>p.rotated));for(let i=1;i<ps.length;i++)assert.ok(ps[i].unusedArea>=ps[i-1].unusedArea);});
test('a large rectangular HUB75 panel wins when the artwork coverage wastes less area',()=>{const s=state([30,30],'hub75',2,50);const ps=E.candidates(s,catalog);assert.ok(ps.some(p=>p.panelId==='hub-p5-64x32'));assert.equal(ps[0].unusedArea,Math.min(...ps.map(p=>p.unusedArea)));});
test('out of stock and insufficient stock panels are excluded',()=>{const c=structuredClone(catalog);c.panels.forEach(p=>p.stock=0);const s=state();assert.equal(E.candidates(s,c).length,0);assert.equal(E.plan(s,c).ready,false);c.panels[0].stock=1;assert.ok(E.candidates(s,c).every(p=>p.count<=1));});
test('unapproved artwork never produces a panel plan or a complete build',()=>{const s=state();s.artwork.approved=false;assert.equal(E.plan(s,catalog).layout,null);assert.equal(E.plan(s,catalog).ready,false);});
test('flexible and HUB75 controllers are incompatible; Beast remains unavailable',()=>{const s=state();s.controllerId='digi-quad';assert.equal(E.plan(s,catalog).controller.id,'matrixportal-s3');s.controllerId='beast';assert.equal(E.plan(s,catalog).controller.id,'matrixportal-s3');s.rear='flex';assert.deepEqual(E.controllers(s,catalog).map(c=>c.id),['digi-uno','digi-quad']);});
test('HUB75 does not acquire a fabricated power rating',()=>{const p=E.plan(state(),catalog);assert.equal(p.hub75PowerPending,true);assert.equal(p.addressableEstimateAmps,4.32);});
test('a build with neither rim nor rear LEDs cannot be completed',()=>{const s=state([12,12],'none');s.rim.enabled=false;assert.equal(E.plan(s,catalog).ready,false);});
test('owner frame estimate supersedes old sales and applies exactly 20% only to the frame',()=>{
  const s=state([12,12],'none'),p=E.pricing(s,catalog),f=p.lines.find(l=>l.id==='frame');
  assert.equal(f.unitCents,1700);assert.equal(f.markupCents,340);assert.equal(f.minCents,2040);
  assert.equal(f.offerId,'owner-michaels-12-frame');assert.equal(p.frameAlternatives.length,1);
  assert.equal(p.lines.find(l=>l.id==='controller').minCents,3500);
  assert.ok(p.lines.filter(l=>l.id!=='frame').every(l=>l.markupCents===0));
  const c=structuredClone(catalog);c.pricing.frames=c.pricing.historicalSupplierSnapshot.frames.filter(f=>!f.id.includes('retail'));
  const bulk=E.pricing(s,c).lines.find(l=>l.id==='frame');assert.equal(bulk.unitCents,675);assert.equal(bulk.minCents,810);assert.equal(bulk.purchaseQuantity,1);
});
test('unmatched frame sizes and finishes do not inherit the cheap 12-inch frame price',()=>{
  const s=state([12,12],'none');s.finish='Natural birch';assert.equal(E.pricing(s,catalog).lines.find(l=>l.id==='frame').minCents,null);
  for(const size of catalog.sizes.slice(1)){s.size=size;s.finish='Matte black';const p=E.pricing(s,catalog);assert.equal(p.lines.find(l=>l.id==='frame').minCents,null);assert.equal(p.frameMarkupPercent,20);assert.equal(p.frameAlternatives.length,1);}
});
test('LED quantities still round up while deferred strip pricing stays pending',()=>{
  const s=state([20,20],'none');s.rim.countPerRow=100;
  const one=E.pricing(s,catalog);s.rim.rows=3;const three=E.pricing(s,catalog);
  assert.equal(three.lines.find(l=>l.id==='rim').purchaseQuantity,1);
  s.rim.countPerRow=101;const over=E.pricing(s,catalog),rim=over.lines.find(l=>l.id==='rim');
  assert.equal(rim.purchaseQuantity,2);assert.equal(rim.minCents,null);assert.equal(rim.maxCents,null);
  assert.equal(over.subtotalMinCents,one.subtotalMinCents);assert.equal(over.grandTotalCents,null);
  s.controllerId='digi-quad';assert.equal(E.pricing(s,catalog).subtotalMinCents-over.subtotalMinCents,1500);
});
test('rush addressable LEDs use Amazon while HUB75 and controllers retain their suppliers',()=>{
  const s=state([12,12],'flex');let p=E.pricing(s,catalog);
  assert.equal(p.lines.find(l=>l.id==='rim').supplier,'Alibaba / AliExpress');
  s.fulfillment='rush';p=E.pricing(s,catalog);
  assert.equal(p.lines.find(l=>l.id==='rim').supplier,'Amazon');assert.equal(p.lines.find(l=>l.id==='rim').status,'range');
  assert.equal(p.lines.find(l=>l.id==='panels').supplier,'Amazon');assert.equal(p.lines.find(l=>l.id==='controller').supplier,'Dr. Zzs');
  s.rear='hub75';s.artScale=50;s.layoutKey='hub-p3-64x32-n';p=E.pricing(s,catalog);
  assert.equal(p.lines.find(l=>l.id==='panels').supplier,'Alibaba');assert.equal(p.lines.find(l=>l.id==='panels').quantity,2);assert.equal(p.lines.find(l=>l.id==='panels').minCents,2800);
  assert.equal(p.lines.find(l=>l.id==='controller').minCents,2000);assert.equal(p.lines.find(l=>l.id==='rim-controller').minCents,3500);
  assert.match(p.lines.find(l=>l.id==='controller').availability,/out of stock/);
});
test('unpriced add-ons remain quote items and an incomplete estimate never becomes a grand total',()=>{
  const s=state([12,12],'none'),before=E.pricing(s,catalog);s.extras.remote=true;s.audioReactive=true;
  const after=E.pricing(s,catalog);assert.equal(after.pendingCount,before.pendingCount+2);
  assert.equal(after.grandTotalCents,null);assert.equal(after.lines.find(l=>l.id==='remote').minCents,null);
  assert.ok(after.lines.some(l=>l.id==='assembly'));assert.ok(after.lines.some(l=>l.id==='shipping'));assert.ok(after.lines.some(l=>l.id==='tax'));
  s.extras.remote=false;assert.ok(!E.pricing(s,catalog).lines.some(l=>l.id==='remote'));
});
test('12-inch build uses one $6 mirror without pricing larger glass from that estimate',()=>{
  const s=state([12,12],'none'),p=E.pricing(s,catalog),m=p.lines.find(l=>l.id==='mirror');
  assert.equal(m.quantity,1);assert.equal(m.unitCents,600);assert.equal(m.minCents,600);assert.equal(m.markupCents,0);
  assert.equal(E.plan(s,catalog).hardware.find(h=>h.id==='mirror').quantity,1);
  for(const size of catalog.sizes.slice(1)){s.size=size;assert.equal(E.pricing(s,catalog).lines.find(l=>l.id==='mirror').minCents,null);}
});
test('flexible panel ranges scale by layout count and keep the final total pending',()=>{
  const c=structuredClone(catalog);c.panels=c.panels.filter(p=>p.id==='flex-16x16');
  const s=state([24,24],'flex'),p=E.pricing(s,c),l=p.lines.find(l=>l.id==='panels');
  assert.equal(l.minCents,1600*l.quantity);assert.equal(l.maxCents,1800*l.quantity);assert.equal(l.status,'range');
  assert.equal(p.grandTotalCents,null);assert.equal(p.finalQuoteRequired,true);
});
test('the 12-inch LED budget is one build allowance and does not price larger quantities',()=>{
  const s=state([12,12],'none');s.rim.rows=2;s.rim.countPerRow=120;
  let p=E.pricing(s,catalog),rim=p.lines.find(l=>l.id==='rim');
  assert.equal(rim.quantity,1);assert.equal(rim.minCents,500);assert.equal(rim.maxCents,3000);assert.equal(p.grandTotalCents,null);
  s.rim.rows=3;p=E.pricing(s,catalog);rim=p.lines.find(l=>l.id==='rim');assert.equal(rim.minCents,null);assert.equal(rim.quantity,2);
});
test('confirmed catalog prices respect order minimums and can produce a complete estimated total',()=>{
  const c=structuredClone(catalog),s=state([12,12],'none');c.pricing.standardRim={supplier:'Alibaba',priceCents:1500,minimumQuantity:2};
  for(const v of Object.values(c.pricing.components))v.priceCents=100;
  const p=E.pricing(s,c),rim=p.lines.find(l=>l.id==='rim');
  assert.equal(rim.purchaseQuantity,2);assert.equal(rim.minCents,3000);assert.equal(p.pendingCount,0);assert.equal(p.rangeCount,0);
  assert.equal(p.grandTotalCents,p.lines.reduce((sum,l)=>sum+l.minCents,0));assert.equal(p.finalQuoteRequired,true);
});
test('multirow and oversized HUB75 plans carry WLED-MM mapping and memory review notes',()=>{
  const s=state([36,36],'hub75',1,90),p=E.plan(s,catalog);assert.ok(p.layout.rows>1);assert.ok(p.layout.pixels>4096);
  assert.ok(p.warnings.some(w=>w.includes('custom WLED-MM panel mapping')));assert.ok(p.warnings.some(w=>w.includes('pixel budget')));
  assert.match(catalog.controllers.find(c=>c.id==='beast').reason,/Coming Soon/);
});
