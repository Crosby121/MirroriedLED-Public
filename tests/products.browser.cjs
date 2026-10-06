// Run with Playwright available in NODE_PATH; this storefront has no npm runtime.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {spawn}=require('node:child_process'),readline=require('node:readline');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const cartKey='mirroriedled_storefront_cart_vnext',draftKey='mirroriedled_quote_draft_v1';
const serverCode='import http.server,json\ns=http.server.ThreadingHTTPServer(("127.0.0.1",0),http.server.SimpleHTTPRequestHandler)\nprint(json.dumps({"url":"http://127.0.0.1:%d"%s.server_port}),flush=True)\ns.serve_forever()';
(async()=>{
  const server=spawn('python3',['-u','-c',serverCode],{cwd:root,stdio:['ignore','pipe','ignore']});
  let browser;
  try{
    const line=await new Promise((resolve,reject)=>{const rl=readline.createInterface({input:server.stdout});rl.once('line',l=>{rl.close();resolve(l)});server.once('exit',code=>reject(new Error('Static test server exited '+code)));});
    const {url}=JSON.parse(line);
    browser=await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE||undefined,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
    const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url+'/');await page.getByRole('link',{name:'View Products',exact:true}).click();
    assert.equal(new URL(page.url()).pathname,'/products/');
    assert.equal(await page.locator('.product-card').count(),4);
    await page.getByRole('link',{name:'Browse stadiums',exact:true}).click();
    await page.waitForSelector('.stadium-card');
    assert.equal(await page.locator('.stadium-card').count(),92);
    await page.locator('#sportFilter').selectOption('baseball');assert.equal(await page.locator('.stadium-card').count(),30);
    await page.locator('#teamFilter').selectOption({label:'Los Angeles Dodgers'});
    assert.equal(await page.locator('.stadium-card').count(),1);
    await page.locator('.stadium-card button').click();
    await page.waitForFunction(()=>{const im=document.querySelector('#detailImage img');return im?.complete&&im.naturalWidth>0});
    const first=await page.locator('#detailImage img').getAttribute('src');await page.locator('#nextImage').click();
    assert.notEqual(await page.locator('#detailImage img').getAttribute('src'),first);
    await page.locator('#buildSize').selectOption('collector');assert.equal(await page.locator('#buildPrice').textContent(),'$299.99');
    assert.equal(await page.locator('#emailQuote').count(),1,'Stadium customers need an email quote option');
    const stadiumMail=decodeURIComponent(await page.locator('#emailQuote').getAttribute('href'));
    assert.match(stadiumMail,/^mailto:quotes@mirroriedled\.com\?/);assert.match(stadiumMail,/Los Angeles Dodgers/);assert.match(stadiumMail,/Collector/);assert.doesNotMatch(stadiumMail,/299\.99/);
    await page.locator('#addTest').click();assert.equal(await page.evaluate(k=>localStorage.getItem(k),cartKey),null);
    await page.locator('#closeDetail').click();assert.equal(await page.locator('#testTotal').textContent(),'$299.99');
    await page.reload();assert.equal(await page.locator('#testTotal').textContent(),'$299.99');
    await page.locator('#sportFilter').selectOption('football');assert.equal(await page.locator('.stadium-card').count(),32);
    assert.equal(await page.locator('#teamFilter').inputValue(),'all');
    await page.locator('#sportFilter').selectOption('basketball');assert.equal(await page.locator('.stadium-card').count(),30);
    await page.locator('#resetFilters').click();assert.equal(await page.locator('.stadium-card').count(),92);
    await page.locator('#teamFilter').selectOption({label:'Los Angeles Dodgers'});await page.locator('.stadium-card button').click();
    await page.locator('#buildSize').selectOption('mini');await page.locator('#requestQuote').click();
    await page.waitForURL('**/customer-portal/#builds');
    const draft=await page.evaluate(k=>JSON.parse(sessionStorage.getItem(k)),draftKey);
    assert.equal(draft.length,1);assert.equal(draft[0].product,'Layered Stadium Model');assert.equal(draft[0].size,'Mini');
    assert.match(draft[0].artwork,/Los Angeles Dodgers/);assert.equal(Object.hasOwn(draft[0],'testUnitPrice'),false);
    assert.ok((await page.locator('#importedBuilds').textContent()).includes('Los Angeles Dodgers'));
    // A full saved list must not be replaced by the new request.
    await page.goto(url+'/stadiums/');await page.evaluate(k=>localStorage.setItem(k,JSON.stringify(Array.from({length:20},(_,i)=>({id:String(i),product:'Saved build'})))),cartKey);
    await page.locator('#teamFilter').selectOption({label:'Boston Celtics'});await page.locator('.stadium-card button').click();
    await page.locator('#requestQuote').click();assert.match(await page.locator('#selectionStatus').textContent(),/full/);
    assert.equal(await page.evaluate(k=>JSON.parse(localStorage.getItem(k)).length,cartKey),20);
    // A browser that rejects session storage must leave the existing cart intact.
    const limited=await browser.newContext();await limited.addInitScript(()=>{const native=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===sessionStorage)throw new DOMException('Session storage unavailable','SecurityError');return native.call(this,k,v)};});
    const restricted=await limited.newPage();await restricted.goto(url+'/stadiums/');
    await restricted.locator('#teamFilter').selectOption({label:'Boston Celtics'});await restricted.locator('.stadium-card button').click();await restricted.locator('#requestQuote').click();
    assert.equal(await restricted.evaluate(k=>localStorage.getItem(k),cartKey),null);
    assert.match(await restricted.locator('#selectionStatus').textContent(),/storage unavailable/i);
    await page.goto(url+'/infinity-builder/');await page.waitForSelector('#artGallery .gallery-item');
    assert.equal(await page.locator('#artGallery .gallery-item').count(),8);
    assert.equal(await page.locator('input[name=size]').count(),8);
    await page.getByRole('button',{name:'Review Dodgers bats and skyline',exact:true}).click();await page.locator('#approveArt').click();
    assert.match(await page.locator('#approvedArtName').textContent(),/Dodgers bats and skyline/);
    assert.equal(await page.locator('#emailQuote').count(),1,'Mirror customers need an email quote option');
    assert.equal(await page.locator('#emailQuote').isVisible(),true);
    const mirrorMail=decodeURIComponent(await page.locator('#emailQuote').getAttribute('href'));
    assert.match(mirrorMail,/^mailto:quotes@mirroriedled\.com\?/);assert.match(mirrorMail,/Dodgers bats and skyline/);assert.match(mirrorMail,/12 × 12/);
    await page.locator('#ledCount').fill('1');assert.equal(await page.locator('#emailQuote').isVisible(),false);
    await page.locator('#ledCount').fill('72');assert.equal(await page.locator('#emailQuote').isVisible(),true);
    assert.ok((await page.locator('[data-price-item=frame]').textContent()).includes('$7.20'));
    assert.ok((await page.locator('[data-price-item=frame]').textContent()).includes('20%'));
    await page.locator('#changeArt').click();await page.getByRole('tab',{name:'Upload image',exact:true}).click();
    await page.locator('#artUpload').setInputFiles(path.join(root,'infinity-builder/artwork/generated/dodgers-la.webp'));
    await page.waitForFunction(()=>!document.querySelector('#artReview').hidden);await page.locator('#approveArt').click();
    assert.match(await page.locator('#approvedArtName').textContent(),/dodgers-la.webp/);
    if(process.env.PRODUCT_SCREENSHOT_DIR){fs.mkdirSync(process.env.PRODUCT_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.PRODUCT_SCREENSHOT_DIR,'mirror-builder.png'),fullPage:true});}
    const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true}),phone=await mobile.newPage();phone.on('pageerror',e=>errors.push(e.message));
    for(const route of ['/products/','/stadiums/','/infinity-builder/']){
      await phone.goto(url+route);await phone.waitForTimeout(180);
      assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Horizontal overflow at '+route);
    }
    await phone.goto(url+'/stadiums/');await phone.locator('#teamFilter').selectOption({label:'Los Angeles Rams'});await phone.locator('.stadium-card button').click();
    assert.equal(await phone.locator('#requestQuote').isVisible(),true);
    if(process.env.PRODUCT_SCREENSHOT_DIR)await phone.screenshot({path:path.join(process.env.PRODUCT_SCREENSHOT_DIR,'stadium-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);console.log('PRODUCT_BROWSER_PASS: product links, 92 team filters, image cycling, samples, quote handoff, storage recovery, gallery/upload approval and mobile layouts');
  }finally{if(browser)await browser.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
