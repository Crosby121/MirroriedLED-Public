(() => {
  'use strict';
  const $ = id => document.getElementById(id), E = MirrorBuilderEngine;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const endpoint = new URL('../customer-portal/backend/api.php', location.href);
  let catalog, state, result, price, candidate = null, approvedMask = null, originalBlob = null, rearView = false;
  let session = { configured: false, authenticated: false, csrf: null, capabilities: {} }, saveTimer, artSequence = 0, aiBusy = false;
  let aiQuestions = [], guideBrief = '', guideFingerprint = '', generationKey = null, generationFingerprint = '', drafting = false;
  const message = (id, text, error = false) => { $(id).textContent = text; $(id).classList.toggle('error', error); };
  const uid = () => crypto.randomUUID();
  async function api(action, body) {
    const url = new URL(endpoint); url.searchParams.set('action', action);
    const options = { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
    if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify({ ...body, csrf: session.csrf }); }
    const response = await fetch(url, options);
    if (!(response.headers.get('Content-Type') || '').includes('application/json')) throw new Error('Artwork studio is waiting for server setup. Your design stays available on this device.');
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'The artwork studio could not complete that request.');
    return data;
  }
  async function refreshSession() {
    try { session = await api('session'); } catch { session = { configured: false, authenticated: false, capabilities: {} }; }
    $('aiAvailability').textContent = !session.configured ? 'AI artwork is waiting for the private website connection. You can still use the library or upload an image.' : !session.authenticated ? 'Sign in to the Customer Portal to use the AI artwork studio. Your build stays on this device.' : !session.capabilities.builderAi ? 'Your account’s AI artwork studio is waiting for activation. You can still use the library or upload an image.' : 'Your AI artwork studio is ready. Describe your idea to begin.';
    // The guide remains useful when AI is unavailable; the action explains its availability.
    $('generateArt').disabled = aiBusy;
  }
  const image = async src => { const img = new Image(); img.src = src; await img.decode(); return img; };
  async function maskImage(src, polarity = 'light') {
    const img = await image(src);
    if (img.naturalWidth * img.naturalHeight > 24000000) throw new Error('Choose an image with fewer than 24 million pixels.');
    const scale = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(img.naturalWidth * scale)); canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext('2d', { willReadFrequently: true }); ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let minX = canvas.width, minY = canvas.height, maxX = -1, maxY = -1, count = 0;
    for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
      const p = (y * canvas.width + x) * 4, l = data.data[p] * .2126 + data.data[p + 1] * .7152 + data.data[p + 2] * .0722;
      const ink = data.data[p + 3] > 80 && (polarity === 'dark' ? l < 170 : l > 85);
      data.data[p] = data.data[p + 1] = data.data[p + 2] = 255; data.data[p + 3] = ink ? 255 : 0;
      if (ink) { count++; minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); }
    }
    if (count < 20) throw new Error('No engraving areas were found. Try the other light / dark setting or a clearer image.');
    ctx.putImageData(data, 0, 0);
    const crop = document.createElement('canvas'); crop.width = maxX - minX + 1; crop.height = maxY - minY + 1;
    crop.getContext('2d').drawImage(canvas, minX, minY, crop.width, crop.height, 0, 0, crop.width, crop.height);
    if(crop.width / crop.height > 10 || crop.width / crop.height < .1)throw new Error('Choose artwork with an aspect ratio between 1:10 and 10:1.');
    return { dataUrl: crop.toDataURL('image/png'), blob: await new Promise(resolve => crop.toBlob(resolve, 'image/png')), aspect: crop.width / crop.height };
  }
  async function chooseCandidate(info, src, blob = null, polarity = 'light') {
    const seq = ++artSequence;
    message('artMessage', 'Preparing a frosted engraving preview…');
    try {
      const mask = await maskImage(src, polarity);
      if (seq !== artSequence) return;
      candidate = { ...info, mask, originalBlob: blob };
      $('artCandidate').src = mask.dataUrl; $('artCandidateName').textContent = info.name;
      $('artReview').hidden = false; $('approveArt').disabled = false;
      message('artMessage', 'Review this engraving concept, then approve it to add it to your mirror.');
    } catch (error) { if (seq === artSequence) message('artMessage', error.message, true); }
  }
  function showTab(name, focus = false) {
    for (const tab of document.querySelectorAll('[data-art-tab]')) {
      const active = tab.dataset.artTab === name;
      tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1;
      $('panel-' + tab.dataset.artTab).hidden = !active;
      if (active && focus) tab.focus();
    }
  }
  function fitController() {
    const available = E.controllers(state, catalog).filter(c => c.available);
    if (!available.some(c => c.id === state.controllerId)) state.controllerId = available[0].id;
  }
  function drawPreview() {
    const svg = $('mirrorPreview'), w = state.size[0], h = state.size[1], scale = Math.min(450 / w, 430 / h);
    const x = (600 - w * scale) / 2, y = (525 - h * scale) / 2 + 10;
    const room = E.interior(state, catalog), art = E.artBox(state, catalog), color = state.rim.color;
    const frame = { 'Matte black': '#263348', 'Natural birch': '#b6956a', White: '#e2e8f0' }[state.finish];
    let parts = [`<title>${esc(w)} by ${esc(h)} inch infinity mirror, ${state.rim.enabled ? state.rim.rows : 0} rim rows, ${state.artwork?.approved ? esc(state.artwork.name) : 'artwork not yet selected'}</title>`, `<defs><linearGradient id="glass" x2="1" y2="1"><stop stop-color="#0c2630"/><stop offset=".5" stop-color="#03111e"/><stop offset="1" stop-color="#18213a"/></linearGradient><filter id="glow"><feGaussianBlur stdDeviation="2.3"/></filter><filter id="tint"><feFlood flood-color="${color}"/><feComposite in2="SourceAlpha" operator="in"/></filter><clipPath id="mirrorClip"><rect x="${x + room.x * scale}" y="${y + room.y * scale}" width="${room.width * scale}" height="${room.height * scale}" rx="3"/></clipPath></defs>`];
    parts.push(`<rect x="${x-5}" y="${y+8}" width="${w*scale+10}" height="${h*scale}" rx="11" fill="#000" opacity=".5"/><rect x="${x}" y="${y}" width="${w*scale}" height="${h*scale}" rx="9" fill="${frame}" stroke="#ffffff25"/><rect x="${x+7}" y="${y+7}" width="${w*scale-14}" height="${h*scale-14}" rx="5" fill="url(#glass)" stroke="#ffffff12"/>`);
    if (state.rim.enabled) {
      for (let row = 0; row < state.rim.rows; row++) {
        const inset = (catalog.rules.frameLipIn + row * catalog.rules.rowGapIn) * scale;
        for (let tunnel = 5; tunnel >= 0; tunnel--) {
          const shift = tunnel * 4, opacity = (1 - tunnel * .15) * (rearView ? .25 : 1);
          const rw = w * scale - 2 * inset - shift * 2, rh = h * scale - 2 * inset - shift * 2;
          if (rw <= 0 || rh <= 0) continue;
          parts.push(`<rect x="${x+inset+shift}" y="${y+inset+shift}" width="${rw}" height="${rh}" rx="2" fill="none" stroke="${color}" stroke-width="${tunnel===0?2.2:1.2}" opacity="${opacity}"/>`);
        }
        const rw = w * scale - 2 * inset, rh = h * scale - 2 * inset, perimeter = 2 * (rw + rh);
        for (let i = 0; i < Math.min(state.rim.countPerRow, 300); i++) {
          const t = i * perimeter / Math.min(state.rim.countPerRow, 300);
          let px, py;
          if (t < rw) { px=t; py=0; } else if (t<rw+rh) { px=rw; py=t-rw; } else if (t<rw*2+rh) { px=rw-(t-rw-rh);py=rh; } else { px=0;py=rh-(t-rw*2-rh); }
          parts.push(`<circle cx="${x+inset+px}" cy="${y+inset+py}" r="1.2" fill="${color}" opacity="${rearView?.3:.9}"/>`);
        }
      }
    }
    if (rearView && result.layout) {
      parts.push(`<g clip-path="url(#mirrorClip)">`);
      result.layout.cells.forEach((cell,i) => parts.push(`<rect data-panel="${i}" x="${x+cell.x*scale}" y="${y+cell.y*scale}" width="${cell.width*scale}" height="${cell.height*scale}" fill="#17323e" stroke="#5eead4" stroke-width="1.4"/><text x="${x+(cell.x+cell.width/2)*scale}" y="${y+(cell.y+cell.height/2)*scale}" text-anchor="middle" fill="#a6d3cd" font-size="11">${i+1}</text>`));
      parts.push('</g>');
    }
    if (state.artwork?.approved && approvedMask) {
      const attrs=`x="${x+art.x*scale}" y="${y+art.y*scale}" width="${art.width*scale}" height="${art.height*scale}" href="${approvedMask.dataUrl}" preserveAspectRatio="xMidYMid meet"`;
      parts.push(`<g clip-path="url(#mirrorClip)" opacity="${rearView?.65:1}"><image ${attrs} filter="url(#glow)" opacity=".65"/><image ${attrs} filter="url(#tint)"/><image ${attrs} opacity=".6"/></g>`);
      if (rearView) parts.push(`<rect x="${x+art.x*scale}" y="${y+art.y*scale}" width="${art.width*scale}" height="${art.height*scale}" fill="none" stroke="#fcd34d" stroke-dasharray="5 4" stroke-width="1.2"/>`);
    } else parts.push(`<text x="300" y="270" text-anchor="middle" fill="#85a8b4" font-size="13">Your engraving goes here</text>`);
    if (rearView && !result.layout) parts.push(`<text x="300" y="310" text-anchor="middle" fill="#85a8b4" font-size="11">${state.rear==='none'?'Rim lighting only':'Approve artwork to see panel coverage'}</text>`);
    const dy=y+h*scale+22;
    parts.push(`<path d="M${x} ${dy}h${w*scale}M${x} ${dy-4}v8M${x+w*scale} ${dy-4}v8" stroke="#667c94" stroke-width="1"/><text x="300" y="${dy+21}" text-anchor="middle" fill="#a3b3c6" font-size="13">${w} inches</text><text x="${x-20}" y="${y+h*scale/2}" text-anchor="middle" fill="#a3b3c6" font-size="12" transform="rotate(-90 ${x-20} ${y+h*scale/2})">${h} inches</text>`);
    svg.innerHTML=parts.join('');
  }
  const money = cents => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(cents/100);
  const moneyRange = (min,max) => min===max?money(min):`${money(min)}–${money(max)}`;
  function renderPricing() {
    price=E.pricing(state,catalog,result);
    const subtotal=moneyRange(price.subtotalMinCents,price.subtotalMaxCents);
    $('priceSubtotal').textContent=subtotal;$('previewPrice').textContent=subtotal;
    $('priceStatus').textContent=price.pendingCount?`+ ${price.pendingCount} items awaiting a quote${price.rangeCount?' · LED variant range included':''}`:'Supplier estimates · final quote follows';
    $('priceGrandTotal').textContent=price.grandTotalCents===null?'Quote pending':money(price.grandTotalCents)+' estimate';
    $('previewPriceStatus').textContent=price.grandTotalCents===null?'Grand total: quote pending':'Grand total estimate: '+money(price.grandTotalCents);
    $('priceLines').innerHTML=price.lines.map(l=>`<li data-price-item="${esc(l.id)}" class="${l.minCents===null?'price-pending':''}"><div class="price-line-top"><strong>${esc(l.label)}</strong><span>${l.minCents===null?'Quote needed':esc(moneyRange(l.minCents,l.maxCents))}</span></div><small>${esc(l.supplier)} · × ${esc(l.purchaseQuantity)}${l.minCents===null?'':l.status==='range'?' · variant range':' · estimate'}</small>${l.id==='frame'&&l.unitCents!==null?`<small>${esc(money(l.unitCents))} supplier unit cost + ${esc(money(l.markupCents))} markup (${price.frameMarkupPercent}%)</small>`:''}<details><summary>Price basis${l.url?' & source':''}</summary><p>${esc(l.detail)}</p><p>${esc(l.availability)}</p>${l.url?`<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">View supplier listing ↗</a>`:''}</details></li>`).join('');
    $('priceNotice').textContent=`Frame supplier cost includes your ${price.frameMarkupPercent}% markup. The grand total follows after every quote item, shipping and tax is priced. No payment starts here.`;
    $('supplierPolicy').textContent=state.fulfillment==='rush'?'Rush addressable strips and flexible panels use Amazon. HUB75 stays with Alibaba / AliExpress. Digi controllers use Dr. Zzs; MatrixPortal uses Adafruit.':'Standard addressable strips and panels use Alibaba / AliExpress. Digi controllers use Dr. Zzs; MatrixPortal uses Adafruit. Amazon is reserved for rush addressable LEDs.';
    $('frameOffers').innerHTML=price.frameAlternatives.length?price.frameAlternatives.map(f=>`<li>${f.priceCents!==null?`${esc(money(f.priceCents))} / ${f.packQuantity} frames · ${esc(money(Math.round(f.priceCents/f.packQuantity)))} per frame before ${price.frameMarkupPercent}% markup`:'Matching nominal frame candidate · supplier quote needed'} · <a href="${esc(f.url)}" target="_blank" rel="noopener noreferrer">Michaels listing ↗</a></li>`).join(''):`<li>Exact size / finish needs a Michaels quote; supplier cost + ${price.frameMarkupPercent}%.</li>`;
    $('supplierDate').textContent=catalog.pricing.notice;
  }
  function render() {
    fitController(); result=E.plan(state,catalog);
    $('previewSize').textContent=`${state.size[0]} × ${state.size[1]} in`;
    $('previewLabel').textContent=state.rim.enabled?`${state.rim.rows} rim row${state.rim.rows>1?'s':''} · ${result.rimPixels} LEDs`:'Rim strips off';
    $('statRim').textContent=result.rimPixels; $('statPanels').textContent=result.layout?.count??'—'; $('statController').textContent=result.controller.name.replace('QuinLED ','').replace('Adafruit ','');
    $('densityNote').textContent=`${state.rim.countPerRow} LEDs per row · ${result.rimPixels} rim LEDs total`;
    $('rimOptions').hidden=!state.rim.enabled;
    $('approvedArt').hidden=!state.artwork?.approved; $('artScaleField').hidden=!state.artwork?.approved;
    $('approvedArtName').textContent=state.artwork?.name||'';
    const art=E.artBox(state,catalog); $('artScaleLabel').textContent=`${E.round(art.width)} × ${E.round(art.height)} in · ${state.artScale}% of safe area`;
    $('panelSelectField').hidden=!result.layouts.length;
    $('panelSelect').innerHTML='<option value="auto">Auto · least unused coverage</option>'+result.layouts.map(p=>`<option value="${p.key}">${esc(p.name)} · ${p.count} panels${p.rotated?' · rotated':''} · ${p.utilization}% used</option>`).join('');
    if(state.layoutKey!=='auto'&&!result.layouts.some(x=>x.key===state.layoutKey)) state.layoutKey='auto';
    $('panelSelect').value=state.layoutKey;
    $('panelResult').innerHTML=state.rear==='none'?'<p>Rim lighting only. No rear panels included.</p>':!state.artwork?.approved?'<p>Approve artwork to find the best-fitting panels.</p>':!result.layout?'<p>No complete panel layout fits. Reduce the artwork size or choose a larger mirror.</p>':`<strong>${esc(result.layout.name)} · ${result.layout.count} panels</strong><small>${result.layout.cols} across × ${result.layout.rows} high${result.layout.rotated?' · rotated':''} · ${E.round(result.layout.width)} × ${E.round(result.layout.height)} in coverage</small><small>${result.layout.utilization}% of this layout covers the artwork bounding box</small><div class="coverage-meter"><span style="width:${result.layout.utilization}%"></span></div>`;
    $('controllerOptions').innerHTML=E.controllers(state,catalog).map(c=>`<label class="controller-choice"><input type="radio" name="controller" value="${c.id}" ${c.id===state.controllerId?'checked':''} ${!c.available?'disabled':''}><span><strong>${esc(c.name)}</strong><small>${esc(c.reason || (c.family==='hub75'?'HUB75 / HUB75E matrix output':c.outputs+' addressable LED outputs · layout reviewed by the team'))}</small></span></label>`).join('');
    $('rimControllerField').hidden=state.rear!=='hub75'||!state.rim.enabled;
    $('controllerNote').textContent=state.rear==='hub75'?'HUB75 uses MatrixPortal S3, currently out of stock at Adafruit; studio stock and lead time need confirmation. Rim strips use a separate Digi-Uno or Digi-Quad. The Beast is Coming Soon.':'Flexible panels and rim LEDs use Digi-Uno or Digi-Quad. Output grouping and LED load are verified in the final proof.';
    $('hardwareList').innerHTML=result.hardware.map(h=>`<li><span>${esc(h.label)}</span><small>${h.id==='rim'?h.quantity+' LEDs':'× '+h.quantity}</small></li>`).join('');
    $('powerNote').textContent=`Addressable LEDs: ${result.addressableEstimateAmps} A at 5V for planning, using a conservative 60 mA / pixel assumption.${result.hub75PowerPending?' HUB75 power is additional and awaits the actual panel specification.':''} The team selects the power supply, wire gauges and fuses.`;
    $('reviewNotes').innerHTML=result.warnings.map(w=>`<li>${esc(w)}</li>`).join('');
    const done=[true,true,!!state.artwork?.approved,state.rear==='none'||!!result.layout,true,true];
    ['frame','rim','art','rear','controller','hardware'].forEach((k,i)=>{const tick=$('tick-'+k);tick.textContent=done[i]?'✓':'○';tick.classList.toggle('pending',!done[i]);});
    [...$('progressList').children].forEach((node,i)=>node.classList.toggle('done',done[i]));
    $('addBuild').disabled=!result.ready || (state.rim.enabled && !$('ledCount').validity.valid);
    $('emailQuote').hidden=$('addBuild').disabled;
    $('emailQuote').removeAttribute('href');
    if(!$('emailQuote').hidden){
      const body=['Hello Mirroried LED,','','Please quote this custom infinity mirror:','Size: '+state.size.join(' × ')+' inches','Frame: '+state.finish+' · '+state.depthIn+' inches deep','Artwork: '+state.artwork.name,'Rim: '+state.rim.rows+' rows · '+result.rimPixels+' LEDs','Rear lighting: '+state.rear+' · '+(result.layout?result.layout.name+' × '+result.layout.count:'Rim only'),'Controller: '+result.controller.name,'Audio reactive: '+(state.audioReactive?'Yes':'No'),'Order speed: '+state.fulfillment,'','Final pricing and design proof required. I will attach my artwork and downloaded build configuration.','','Name:','Phone:','Best contact time:'].join('\n');
      $('emailQuote').href='mailto:quotes@mirroriedled.com?subject='+encodeURIComponent('Mirroried LED infinity mirror quote')+'&body='+encodeURIComponent(body);
    }
    if(!result.ready)message('buildMessage',!state.artwork?.approved?'Choose and approve artwork to complete your build.':!state.rim.enabled&&state.rear==='none'?'Include rim strips or rear panels to light your mirror.':'Adjust the artwork size or frame until a complete panel layout fits.',true);else message('buildMessage','Your design is ready for a quote review.');
    renderPricing();drawPreview(); clearTimeout(saveTimer); saveTimer=setTimeout(()=>saveLocal(false),600);
  }
  function applyControls() {
    document.querySelector(`input[name=size][value="${state.size.join('x')}"]`).checked=true;
    $('frameFinish').value=state.finish;$('frameDepth').value=state.depthIn;$('rimEnabled').checked=state.rim.enabled;
    document.querySelector(`input[name=rows][value="${state.rim.rows}"]`).checked=true;
    $('ledCount').value=state.rim.countPerRow;$('ledColor').value=state.rim.color;$('audioReactive').checked=state.audioReactive;
    $('addressableEffects').checked=state.rim.addressable;
    $('artScale').value=state.artScale;document.querySelector(`input[name=rear][value="${state.rear}"]`).checked=true;
    $('rimController').value=state.rimControllerId;$('wallMount').checked=state.extras.wallMount;$('remote').checked=state.extras.remote;
    document.querySelector(`input[name=fulfillment][value="${state.fulfillment||'standard'}"]`).checked=true;
  }
  function validSaved(s) {
    return s?.version===1&&catalog.sizes.some(a=>a.join('x')===s.size?.join('x'))&&['Matte black','Natural birch','White'].includes(s.finish)&&s.depthIn===3&&[1,2,3].includes(s.rim?.rows)&&Number.isInteger(s.rim.countPerRow)&&s.rim.countPerRow>=24&&s.rim.countPerRow<=2000&&/^#[a-f0-9]{6}$/i.test(s.rim.color)&&s.artScale>=20&&s.artScale<=100&&['flex','hub75','none'].includes(s.rear)&&s.extras&&(!s.artwork||typeof s.artwork.name==='string'&&s.artwork.name.length<=200&&s.artwork.aspect>0&&s.artwork.aspect<=10);
  }
  async function saveLocal(explicit) {
    if(drafting)return;
    try { await MirrorDraftStore.put({id:'active',catalogVersion:catalog.version,state,maskBlob:approvedMask?.blob||null,originalBlob,aiDraft:{subject:$('aiSubject').value,type:$('aiType').value,questions:aiQuestions,answers:answers()}}); if(explicit)message('draftStatus','Design saved on this device.'); }
    catch { if(explicit)message('draftStatus','This browser could not save your artwork. Download the build or keep this page open.',true); }
  }
  function specification() {
    const clean=JSON.parse(JSON.stringify(state));
    return {catalogVersion:catalog.version,state:clean,artworkBox:E.artBox(state,catalog),panelPlan:result.layout,hardware:result.hardware,pricing:price,productionStatus:'Quote and operator proof required',rules:catalog.rules.finish};
  }
  async function addBuild() {
    if(!result.ready || (state.rim.enabled && !$('ledCount').reportValidity()))return;
    $('addBuild').disabled=true;drafting=true;
    try {
      const id=uid();
      await MirrorDraftStore.put({id,state,maskBlob:approvedMask.blob,originalBlob:originalBlob||approvedMask.blob});
      const cart=JSON.parse(localStorage.getItem('mirroriedled_storefront_cart_vnext')||'[]');
      if(!Array.isArray(cart)||cart.length>=20)throw new Error('Your build list is full. Review it in the Customer Portal first.');
      const description=state.artwork.source==='ai'?'AI engraving concept':state.artwork.source==='library'?'Studio library engraving':'Uploaded engraving';
      const item={id,product:'Custom Infinity Mirror',size:state.size.join('×'),quantity:1,artwork:`${state.artwork.name} · ${description} · customer approved`,artworkSource:'upload',lighting:`${result.rimPixels} rim LEDs · ${state.rear}${state.audioReactive?' · audio reactive':''}`,finish:state.finish,notes:`${state.depthIn} in depth. ${result.layout?result.layout.name+' × '+result.layout.count:'Rim only'}. ${result.controller.name}. ${catalog.rules.finish}`,builder:specification(),builderDraftId:id};
      cart.push(item);localStorage.setItem('mirroriedled_storefront_cart_vnext',JSON.stringify(cart));
      sessionStorage.setItem('mirroriedled_quote_draft_v1',JSON.stringify(cart));
      location.href='../customer-portal/#builds';
    } catch(error){message('buildMessage',error.message||'The build could not be saved. Try downloading your build.',true);drafting=false;$('addBuild').disabled=false;}
  }
  function fallbackQuestions(type) {
    const first={music:['instrument','Which instrument, music style or motion should lead the image?'],nature:['subject','Which animal, landscape or natural elements should be included?'],portrait:['person','Who is being honored, and what pose or symbolic details matter?'],logo:['wording','What exact name, lettering or logo elements should appear?'],sports:['sport','Which sport, venue or original sports scene should be shown?'],geometric:['shape','Which shapes, symmetry or visual rhythm do you like?'],other:['subject','What is the main subject, and which details matter most?']}[type];
    return [{id:first[0],question:first[1]},{id:'style',question:'Should it be a bold silhouette, flowing line art, or layered detail?'},{id:'text',question:'What exact names, dates or words should appear? Write “none” if no text is needed.'},{id:'composition',question:'What should be central, and what should be left out?'}];
  }
  function answers(){return aiQuestions.map(q=>({question:q.question,answer:$('question-'+q.id)?.value||''}));}
  function questionInputs(list) {
    aiQuestions=list.slice(0,6).map((q,i)=>({id:'q'+i,question:String(q.question).slice(0,250)}));
    $('aiQuestions').replaceChildren();
    aiQuestions.forEach(q=>{const l=document.createElement('label');l.textContent=q.question;const input=document.createElement('input');input.id='question-'+q.id;input.maxLength=800;input.required=true;l.append(input);$('aiQuestions').append(l);});
  }
  async function guideDesign() {
    if(!$('aiSubject').reportValidity())return;
    const fingerprint=$('aiSubject').value.trim()+'|'+$('aiType').value;
    guideBrief='';guideFingerprint=fingerprint;questionInputs(fallbackQuestions($('aiType').value));
    if(!session.capabilities.builderAi||!session.authenticated){message('artMessage','Answer these design questions. AI artwork will be available once your account’s studio is activated.');return;}
    $('askAI').disabled=true;message('artMessage','The artwork guide is choosing questions for your idea…');
    try {const data=await api('builder-guide',{subject:$('aiSubject').value,type:$('aiType').value});if(fingerprint!==$('aiSubject').value.trim()+'|'+$('aiType').value)return;guideBrief=data.designBrief;questionInputs(data.questions);message('artMessage','Answer these questions, then generate your engraving concept.');}
    catch(error){message('artMessage',error.message+' Your design questions remain available.',true);}finally{$('askAI').disabled=false;}
  }
  async function generate(event) {
    event.preventDefault();if(aiBusy)return;
    if(!session.capabilities.builderAi||!session.authenticated){await saveLocal(false);message('artMessage',session.authenticated?'AI artwork is waiting for account activation. Your design answers are saved on this device.':'Sign in through the Customer Portal to use AI artwork. Your design answers are saved on this device.',true);return;}
    if(guideFingerprint!==$('aiSubject').value.trim()+'|'+$('aiType').value||!aiQuestions.length){await guideDesign();return;}
    if(!$('aiForm').reportValidity())return;
    if(!$('aiConsent').checked){message('artMessage','Select “Create this artwork using AI” to continue.',true);return;}
    const body={subject:$('aiSubject').value,type:$('aiType').value,answers:answers(),consent:true};
    const fingerprint=JSON.stringify(body);
    if(fingerprint!==generationFingerprint){generationKey=uid();generationFingerprint=fingerprint;}
    aiBusy=true;$('generateArt').disabled=true;$('askAI').disabled=true;message('artMessage','Creating your engraving concept. This may take a few minutes…');
    try {const data=await api('builder-generate',{...body,requestKey:generationKey});const blob=await (await fetch(data.artwork.url,{credentials:'same-origin'})).blob();const url=URL.createObjectURL(blob);try{await chooseCandidate({id:data.artwork.id,serverId:data.artwork.id,name:data.artwork.name,source:'ai'},url,blob,'light');}finally{URL.revokeObjectURL(url);}generationKey=null;generationFingerprint='';}
    catch(error){message('artMessage',error.message,true);}finally{aiBusy=false;$('generateArt').disabled=false;$('askAI').disabled=false;}
  }
  async function init(){
    try {
      const response=await fetch('catalog.json',{cache:'no-cache'});if(!response.ok)throw new Error('Builder catalog could not be loaded.');catalog=await response.json();state=E.initial(catalog);
      $('sizeOptions').innerHTML=catalog.sizes.map(s=>`<label><input type="radio" name="size" value="${s.join('x')}"><span>${s.join(' × ')}</span></label>`).join('');
      $('artGallery').innerHTML=catalog.gallery.map(g=>`<button type="button" class="gallery-item" data-gallery="${g.id}" aria-label="Review ${esc(g.name)}"><img src="${esc(g.url)}" alt="${esc(g.name)} engraving design" loading="lazy"><span>${esc(g.name)}<small>${esc(g.source)}</small></span></button>`).join('');
      try {const saved=await MirrorDraftStore.get('active');if(saved?.catalogVersion===catalog.version&&validSaved(saved.state)){
        state=saved.state;state.fulfillment=state.fulfillment==='rush'?'rush':'standard';originalBlob=saved.originalBlob;
        if(saved.maskBlob){const url=URL.createObjectURL(saved.maskBlob);try{approvedMask=await maskImage(url,'light');}finally{URL.revokeObjectURL(url);}}else state.artwork=null;
        if(saved.aiDraft){$('aiSubject').value=saved.aiDraft.subject||'';$('aiType').value=saved.aiDraft.type||'other';questionInputs(saved.aiDraft.questions||[]);(saved.aiDraft.answers||[]).forEach((a,i)=>{const el=$('question-q'+i);if(el)el.value=a.answer;});guideFingerprint=$('aiSubject').value.trim()+'|'+$('aiType').value;}
        message('draftStatus','Your saved design has been restored on this device.');
      }}catch{}
      applyControls();render();
      $('sizeOptions').addEventListener('change',event=>{state.size=event.target.value.split('x').map(Number);state.layoutKey='auto';state.rim.countPerRow=Math.round(2*(state.size[0]+state.size[1])*25.4/1000*60/4)*4;$('ledCount').value=state.rim.countPerRow;render();});
      $('frameFinish').addEventListener('change',event=>{state.finish=event.target.value;render();});
      $('rimEnabled').addEventListener('change',event=>{state.rim.enabled=event.target.checked;render();});
      $('rowOptions').addEventListener('change',event=>{state.rim.rows=Number(event.target.value);render();});
      $('ledCount').addEventListener('input',event=>{const n=Number(event.target.value);if(!Number.isInteger(n)||n<24||n>2000){event.target.setCustomValidity('Choose a whole number from 24 to 2000.');$('addBuild').disabled=true;$('emailQuote').hidden=true;$('emailQuote').removeAttribute('href');message('buildMessage','Set a valid LEDs-per-row count.',true);return;}event.target.setCustomValidity('');state.rim.countPerRow=n;render();});
      $('ledColor').addEventListener('input',event=>{state.rim.color=event.target.value;render();});
      $('audioReactive').addEventListener('change',event=>{state.audioReactive=event.target.checked;render();});
      $('addressableEffects').addEventListener('change',event=>{state.rim.addressable=event.target.checked;render();});
      document.querySelectorAll('[data-art-tab]').forEach(tab=>{tab.addEventListener('click',()=>showTab(tab.dataset.artTab));tab.addEventListener('keydown',event=>{const tabs=[...document.querySelectorAll('[data-art-tab]')],index=tabs.indexOf(tab);if(['ArrowRight','ArrowLeft','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;showTab(tabs[next].dataset.artTab,true);}});});
      $('artGallery').addEventListener('click',event=>{const button=event.target.closest('[data-gallery]');if(!button)return;const g=catalog.gallery.find(g=>g.id===button.dataset.gallery);chooseCandidate({id:g.id,name:g.name,source:'library'},g.url);});
      async function uploadCandidate(){const file=$('artUpload').files[0];if(!file)return;if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10485760){message('artMessage','Choose a PNG, JPEG or WebP image of 10 MB or less.',true);return;}const url=URL.createObjectURL(file);try{await chooseCandidate({id:uid(),name:file.name.slice(0,150),source:'upload'},url,file,$('uploadPolarity').value);}finally{URL.revokeObjectURL(url);}}
      $('artUpload').addEventListener('change',uploadCandidate);$('uploadPolarity').addEventListener('change',uploadCandidate);
      $('approveArt').addEventListener('click',async()=>{if(!candidate)return;const current=candidate;$('approveArt').disabled=true;try{if(current.serverId)await api('builder-approve',{id:current.serverId,approve:true});if(current!==candidate)return;state.artwork={id:current.id,name:current.name,source:current.source,serverId:current.serverId||null,approved:true,aspect:current.mask.aspect};approvedMask=current.mask;originalBlob=current.originalBlob;state.layoutKey='auto';candidate=null;$('artReview').hidden=true;message('artMessage','Artwork approved and added to your design.');render();}catch(error){message('artMessage',error.message,true);$('approveArt').disabled=false;}});
      $('discardArt').addEventListener('click',()=>{artSequence++;candidate=null;$('artReview').hidden=true;message('artMessage','Choose another image or generate a revised concept.');});
      $('changeArt').addEventListener('click',()=>{state.artwork=null;approvedMask=null;originalBlob=null;render();message('artMessage','Choose artwork and approve it again.');});
      $('artScale').addEventListener('input',event=>{state.artScale=Number(event.target.value);state.layoutKey='auto';render();});
      document.querySelectorAll('input[name=rear]').forEach(input=>input.addEventListener('change',()=>{state.rear=input.value;state.layoutKey='auto';render();}));
      $('panelSelect').addEventListener('change',event=>{state.layoutKey=event.target.value;render();});
      $('controllerOptions').addEventListener('change',event=>{state.controllerId=event.target.value;render();});
      $('rimController').addEventListener('change',event=>{state.rimControllerId=event.target.value;render();});
      ['wallMount','remote'].forEach(id=>$(id).addEventListener('change',event=>{state.extras[id]=event.target.checked;render();}));
      document.querySelectorAll('input[name=fulfillment]').forEach(input=>input.addEventListener('change',()=>{state.fulfillment=input.value;render();}));
      function view(rear){rearView=rear;$('frontView').classList.toggle('active',!rear);$('rearView').classList.toggle('active',rear);$('frontView').setAttribute('aria-pressed',String(!rear));$('rearView').setAttribute('aria-pressed',String(rear));drawPreview();}
      $('frontView').addEventListener('click',()=>view(false));$('rearView').addEventListener('click',()=>view(true));
      $('saveDraft').addEventListener('click',()=>saveLocal(true));
      $('downloadSpec').addEventListener('click',()=>{const data=specification();data.complete=result.ready;const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='MirroriedLED_Infinity_Mirror_Build.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
      $('addBuild').addEventListener('click',addBuild);$('askAI').addEventListener('click',guideDesign);$('aiForm').addEventListener('submit',generate);
      $('aiType').addEventListener('change',()=>{questionInputs(fallbackQuestions($('aiType').value));guideFingerprint='';});
      $('aiSubject').addEventListener('input',()=>{clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveLocal(false),600);});
      $('aiQuestions').addEventListener('input',()=>{clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveLocal(false),600);});
      await refreshSession();
    }catch(error){$('loadError').hidden=false;message('loadError',error.message+' Return to the storefront to start a build request.',true);}
  }
  init();
})();
