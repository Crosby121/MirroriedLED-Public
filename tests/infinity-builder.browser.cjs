// Requires Playwright in the execution environment. No browser dependency is added to the storefront.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {spawn}=require('node:child_process'),readline=require('node:readline');
const {chromium}=require('playwright');
(async()=>{
  const server=spawn('python3',[path.join(__dirname,'_builder_browser_server.py')],{stdio:['pipe','pipe','inherit']});
  let browser;
  try {
    const line=await new Promise((resolve,reject)=>{const rl=readline.createInterface({input:server.stdout});rl.once('line',line=>{rl.close();resolve(line);});server.once('exit',code=>reject(new Error('Test server exited '+code)));});
    const {url}=JSON.parse(line);
    browser=await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE||undefined,headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
    const context=await browser.newContext({viewport:{width:1440,height:1050}}),page=await context.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);await page.getByRole('link',{name:'Build my Infinity Mirror',exact:true}).click();
    await page.waitForSelector('#sizeOptions label');
    assert.equal(new URL(page.url()).pathname,'/infinity-builder/');
    assert.equal(await page.locator('#addBuild').isEnabled(),false);
    assert.equal(await page.locator('#priceGrandTotal').textContent(),'Quote pending');
    assert.ok((await page.locator('[data-price-item=frame]').textContent()).includes('$20.40'));
    assert.ok((await page.locator('[data-price-item=mirror]').textContent()).includes('$6.00'));
    assert.ok((await page.locator('[data-price-item=frame]').textContent()).includes('20%'));
    await page.locator('input[name=controller][value="digi-quad"]').check();
    assert.ok((await page.locator('[data-price-item=controller]').textContent()).includes('$50.00'));
    await page.locator('input[name=controller][value="digi-uno"]').check();
    await page.getByRole('button',{name:'Review Orbital geometry'}).click();
    assert.equal(await page.locator('#addBuild').isEnabled(),false);
    await page.getByRole('button',{name:'Approve & add to mirror'}).click();
    await page.locator('input[name=rows][value="3"]').check({force:true});
    await page.locator('#ledCount').fill('120');
    assert.equal(await page.locator('#statRim').textContent(),'360');
    assert.ok((await page.locator('[data-price-item=rim]').textContent()).includes('Quote needed'));
    await page.locator('input[name=fulfillment][value="rush"]').check({force:true});
    assert.ok((await page.locator('[data-price-item=rim]').textContent()).includes('Amazon'));
    assert.ok((await page.locator('[data-price-item=panels]').textContent()).includes('Amazon'));
    await page.locator('input[name=fulfillment][value="standard"]').check({force:true});
    await page.locator('#remote').check();assert.equal(await page.locator('[data-price-item=remote]').count(),1);
    await page.locator('#remote').uncheck();assert.equal(await page.locator('[data-price-item=remote]').count(),0);
    await page.locator('#audioReactive').check();
    await page.locator('input[name=rear][value="hub75"]').check({force:true});
    assert.equal(await page.locator('input[name=controller][value="beast"]').isDisabled(),true);
    assert.ok((await page.locator('#controllerOptions').textContent()).includes('Coming Soon'));
    assert.ok((await page.locator('[data-price-item=controller]').textContent()).includes('out of stock'));
    assert.equal(await page.locator('input[name=controller][value="matrixportal-s3"]').isChecked(),true);
    assert.equal(await page.locator('#rimControllerField').isVisible(),true);
    await page.getByRole('button',{name:'Panel layout',exact:true}).click();
    assert.ok(await page.locator('#mirrorPreview [data-panel]').count()>0);
    await page.locator('#artScale').fill('100');
    assert.equal(await page.locator('#addBuild').isEnabled(),false);
    await page.locator('#artScale').fill('50');
    assert.equal(await page.locator('#addBuild').isEnabled(),true);
    await page.getByRole('button',{name:'Mirror',exact:true}).click();
    await page.locator('input[name=size][value="24x24"]').check({force:true});
    await page.locator('#saveDraft').click();
    await page.waitForFunction(()=>document.querySelector('#draftStatus').textContent.includes('saved'));
    await page.reload();await page.waitForFunction(()=>document.querySelector('#approvedArt').hidden===false);
    assert.equal(await page.locator('input[name=rows][value="3"]').isChecked(),true);
    assert.equal(await page.locator('#audioReactive').isChecked(),true);
    assert.equal(await page.locator('input[name=rear][value="hub75"]').isChecked(),true);
    // Keep the preview route on screen; capture before the quote handoff.
    const screenshotDir=process.env.BUILDER_SCREENSHOT_DIR;
    if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,'Infinity_Mirror_Builder_Preview.png'),fullPage:false});}
    await page.locator('#ledCount').fill('0');
    await page.locator('#audioReactive').uncheck();
    assert.equal(await page.locator('#addBuild').isEnabled(),false);
    await page.locator('#ledCount').fill('120');
    await page.locator('input[name=fulfillment][value="rush"]').check({force:true});
    // Upload a real image and confirm the mask is held until customer approval.
    await page.getByRole('tab',{name:'Upload image'}).click();
    // Use the existing approved design as a nontrivial PNG upload fixture.
    const data=await page.locator('#mirrorPreview image').first().getAttribute('href');
    await page.locator('#uploadPolarity').selectOption('light');
    await page.locator('#artUpload').setInputFiles({name:'uploaded-engraving.png',mimeType:'image/png',buffer:Buffer.from(data.split(',')[1],'base64')});
    await page.waitForFunction(()=>document.querySelector('#artReview').hidden===false);
    await page.locator('#approveArt').click();
    await page.getByRole('tab',{name:'Create with AI'}).click();
    await page.locator('#aiSubject').fill('A trumpet with flowing music and the name Croz');
    await page.locator('#askAI').click();
    assert.ok(await page.locator('#aiQuestions input').count()>=3);
    assert.ok((await page.locator('#aiAvailability').textContent()).includes('Sign in'));
    // Activate a local test account, without an AI key or any external submission.
    const login=await page.evaluate(async()=>{const s=await (await fetch('../customer-portal/backend/api.php?action=session')).json();return(await fetch('../customer-portal/backend/api.php?action=signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf:s.csrf,name:'Browser Fixture',email:'browser-'+crypto.randomUUID()+'@example.com',password:'local fixture password 123',requestedPlan:'free'})})).json();});
    assert.equal(login.ok,true);
    await page.locator('#addBuild').click();await page.waitForURL('**/shop/#builds');
    await page.waitForFunction(()=>document.querySelector('#saveBuild').disabled===false);
    await page.locator('#saveBuildForm [name=name]').fill('Browser Fixture');await page.locator('#saveBuildForm [name=line1]').fill('100 Test Way');await page.locator('#saveBuildForm [name=city]').fill('West Covina');await page.locator('#saveBuildForm [name=state]').selectOption('CA');await page.locator('#saveBuildForm [name=postalCode]').fill('91790');await page.locator('#designConsent').check();
    await page.locator('#saveBuild').click();
    await page.waitForFunction(()=>document.querySelector('#buildMessage').textContent.includes('Build MLED-'));
    assert.ok((await page.locator('#orderList').textContent()).includes('360 rim LEDs'));
    const orders=await page.evaluate(async()=>await(await fetch('../customer-portal/backend/api.php?action=business-orders')).json());
    assert.equal(orders.orders.length,1);assert.ok(orders.orders[0].files.some(f=>f.name.endsWith('engraving.png')));assert.ok(orders.orders[0].files.some(f=>f.name.endsWith('original.png')));assert.equal(orders.orders[0].commerce.address.postalCode,'91790');
    assert.equal(orders.orders[0].items[0].builder.state.rim.rows,3);assert.equal(orders.orders[0].items[0].builder.pricing.frameMarkupPercent,20);
    await page.goto(url+'/address-builder/');await page.locator('[name=number]').fill('128');await page.locator('[name=street]').fill('Test Way');await page.locator('#signForm input[type=checkbox]').check();await page.getByRole('button',{name:'Review price & delivery'}).click();await page.waitForURL('**/shop/#builds');
    assert.ok((await page.locator('#draftItems').textContent()).includes('128 · Test Way'));
    await page.locator('#saveBuildForm [name=name]').fill('Browser Fixture');await page.locator('#saveBuildForm [name=line1]').fill('100 Test Way');await page.locator('#saveBuildForm [name=city]').fill('West Covina');await page.locator('#saveBuildForm [name=state]').selectOption('CA');await page.locator('#saveBuildForm [name=postalCode]').fill('91790');await page.locator('#designConsent').check();await page.locator('#saveBuild').click();await page.waitForFunction(()=>document.querySelectorAll('.order-card').length===2);
    if(screenshotDir){await page.screenshot({path:path.join(screenshotDir,'Customer_Orders_Preview.png'),fullPage:false});await page.goto(url);await page.screenshot({path:path.join(screenshotDir,'MirroriedLED_Landing_Page.png'),fullPage:true});}
    // Separate mobile context checks responsive overflow and uploaded artwork approval.
    const mobile=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});const phone=await mobile.newPage();phone.on('pageerror',e=>errors.push(e.message));
    await phone.goto(url+'/infinity-builder/');await phone.waitForSelector('#sizeOptions label');
    assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await phone.getByRole('button',{name:'Review Sound & motion'}).click();await phone.locator('#approveArt').click();
    await phone.locator('input[name=rear][value="flex"]').check({force:true});
    assert.equal(await phone.locator('#addBuild').isEnabled(),true);
    await phone.locator('.price-breakdown summary').first().click();
    assert.equal(await phone.locator('#priceLines').isVisible(),true);
    assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    if(screenshotDir){await phone.screenshot({path:path.join(screenshotDir,'Infinity_Mirror_Builder_Mobile.png'),fullPage:false});}
    for(const route of ['/','/address-builder/','/shop/']){await phone.goto(url+route);assert.equal(await phone.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
    assert.deepEqual(errors,[]);
    console.log('BROWSER_CHECKS_PASSED: storefront routing; live LED rows/counts/prices; 20% frame markup; rush suppliers; quote estimates; Coming Soon gating; approval; fit; drafts; original/mask uploads; phone layout; no page errors');
    await mobile.close();await context.close();
  }finally{if(browser)await browser.close();server.stdin.end();await new Promise(resolve=>server.once('exit',resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
