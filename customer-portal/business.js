(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const money = cents => cents === null ? 'Quote pending' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
  const when = seconds => seconds ? new Date(Number(seconds) * 1000).toLocaleString() : 'To be scheduled';
  const qty = value => (Number(value) / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
  const labels = { REQUESTED: 'Quote review', QUOTED: 'Your approval needed', APPROVED: 'Production review', READY: 'Scheduled', BUILDING: 'In production', QC_HOLD: 'Quality hold', QC_PASSED: 'Quality passed', FULFILLING: 'Shipping / pickup', COMPLETED: 'Completed', CANCELLED: 'Cancelled' };
  const endpoint = new URL('backend/api.php', window.location.href);
  const teamPage = document.body.dataset.operations === 'true';
  const draftKey = 'mirroriedled_quote_draft_v1';
  let session = { authenticated: false, capabilities: {}, user: null, csrf: null };
  let orders = [], stock = [], selectedOrder = null, imported = null, refreshing = 0;
  const pending = new Map();

  function message(id, text, error = false) {
    const element = $(id); if (!element) return;
    element.textContent = text; element.classList.toggle('error', error);
  }
  function hasRole(...roles) { return (session.user?.roles || []).some(role => role === 'admin' || roles.includes(role)); }
  function ready() { return session.authenticated && session.capabilities.business; }
  function requestKey(action, body) {
    const fingerprint = action + JSON.stringify(body instanceof FormData ? [...body.entries()].filter(([k])=>!['csrf','requestKey'].includes(k)).map(([k,v]) => [k, v instanceof File ? [v.name,v.size,v.lastModified] : v]) : body);
    if (!pending.has(fingerprint)) pending.set(fingerprint, crypto.randomUUID());
    return { key: pending.get(fingerprint), fingerprint };
  }
  async function api(action, body, query = {}) {
    const url = new URL(endpoint); url.searchParams.set('action', action);
    for (const [key,value] of Object.entries(query)) url.searchParams.set(key,value);
    const options = { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } };
    let request;
    if (body) {
      request = requestKey(action,body); options.method = 'POST';
      if (body instanceof FormData) { body.set('csrf',session.csrf || ''); body.set('requestKey',request.key); options.body = body; }
      else { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify({...body,csrf:session.csrf,requestKey:request.key}); }
    }
    const response = await fetch(url,options);
    if (!(response.headers.get('Content-Type') || '').includes('application/json')) throw new Error('The build service is waiting for server setup. Use the website contact form for a quote.');
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (response.status === 401 || response.status === 419) await refreshSession();
      throw new Error(data.error || 'This action could not be completed.');
    }
    if (request) pending.delete(request.fingerprint);
    return data;
  }
  async function refreshSession() {
    try { session = await api('session'); } catch { session = { authenticated:false,capabilities:{},user:null }; }
    updateAccess();
  }
  function updateAccess() {
    const enabled = ready();
    const text = !session.configured ? 'Server setup is required for private accounts and build requests.'
      : !session.capabilities.business ? 'Build requests and team operations are waiting for server setup.'
        : !session.authenticated ? 'Sign in above to save artwork, request a quote and follow your builds.' : 'Your private build and support records are ready.';
    message('businessAvailability',text);
    for (const id of ['saveBuildRequest','saveSupportRequest','refreshBuilds']) if ($(id)) $(id).disabled = !enabled;
    if ($('operationsLink')) $('operationsLink').hidden = !enabled || !(session.user?.roles || []).length;
    if (teamPage) {
      const team = enabled && (session.user?.roles || []).length > 0;
      $('teamWorkspace').hidden = !team; $('teamLogin').hidden = team;
      if (!team) message('businessAvailability',enabled ? 'This account does not have team access. Ask the owner to assign the approved role.' : text);
    } else if (!enabled) {
      $('customerBuilds').innerHTML = '<p class="empty-business">Sign in to view your private build requests.</p>';
      $('customerTickets').innerHTML = '<p class="empty-business">Sign in to view your conversations.</p>';
      $('customerUpdates').innerHTML = '<li>Private updates appear after sign-in.</li>';
    }
    if (!enabled) { orders=[]; stock=[]; selectedOrder=null; if(teamPage){$('teamOrderDetails').replaceChildren();$('teamTickets').replaceChildren();$('teamAudit').replaceChildren();} }
  }
  document.addEventListener('mled-session', event => { session=event.detail; updateAccess(); refresh().catch(error=>message('businessAvailability',error.message,true)); });

  function filesHtml(files) { return files.map(file=>`<a href="${esc(file.url)}" download>${esc(file.name)} · ${esc(file.purpose)}</a>`).join('<br>'); }
  function builderDetails(builder) {
    if(!builder?.state)return '';
    const s=builder.state,p=builder.panelPlan;
    const price=builder.pricing;
    const estimate=price?`<p><strong>Supplier estimate:</strong> ${esc(money(price.subtotalMinCents))}${price.subtotalMaxCents!==price.subtotalMinCents?'–'+esc(money(price.subtotalMaxCents)):''}${price.pendingCount?' + '+esc(price.pendingCount)+' quote items':''}. Grand total: ${price.grandTotalCents===null?'quote pending':esc(money(price.grandTotalCents))+' estimate'}. Frame markup: ${esc(price.frameMarkupPercent)}%. ${s.fulfillment==='rush'?'Rush request':'Standard order'}. Final staff quote follows.</p><ul>${price.lines.map(l=>`<li>${esc(l.label)} · × ${esc(l.purchaseQuantity)} · ${esc(l.supplier)} · ${l.minCents===null?'Quote needed':esc(money(l.minCents))+(l.maxCents!==l.minCents?'–'+esc(money(l.maxCents)):'')}</li>`).join('')}</ul>`:'';
    return `<details><summary>Infinity mirror configuration</summary><p>${esc(s.depthIn)} in depth · ${esc(s.finish)}<br>${s.rim.enabled?`${esc(s.rim.rows)} rim rows × ${esc(s.rim.countPerRow)} LEDs`:'No rim strips'} · ${s.rim.addressable?'addressable effects':'steady glow'}${s.audioReactive?' · audio reactive':''}<br>${p?`${esc(p.name)} × ${esc(p.count)} · ${esc(p.cols)} across × ${esc(p.rows)} high`:'Rim only'}<br>Controller: ${esc(s.controllerId)}${s.rear==='hub75'&&s.rim.enabled?` · rim: ${esc(s.rimControllerId)}`:''}<br>${esc(builder.rules)}</p>${estimate}</details>`;
  }
  function itemsHtml(items) { return `<ul>${items.map(item=>`<li><strong>${esc(item.product)}</strong> · ${esc(item.size)} · ${esc(item.quantity || 1)}<br>${esc(item.artwork)}<br>${item.artworkSource==='upload'?'Uploaded artwork':'Mirroried LED team design'}${item.notes ? `<br>${esc(item.notes)}`:''}${builderDetails(item.builder)}</li>`).join('')}</ul>`; }
  function cardHtml(order) {
    return `<article class="build-card" data-order="${esc(order.id)}"><div class="build-meta"><span>${esc(labels[order.status] || order.status)}</span><span>${esc(money(order.quoteCents))}</span></div><h3>${esc(order.id)}</h3>${itemsHtml(order.items)}
      ${order.proof?`<div><h4>Proof ${esc(order.proof.version)} · ${esc(money(Number(order.proof.quote_cents)))}</h4><p class="proof-summary">${esc(order.proof.summary)}</p></div>`:''}
      ${order.files.length?`<p>${filesHtml(order.files)}</p>`:''}
      ${order.status==='QUOTED'?`<form class="approve-proof"><label class="check-row"><input type="checkbox" required>I reviewed proof ${esc(order.proof?.version)} and accept the quoted ${esc(money(order.quoteCents))} total.</label><button type="submit" class="button primary">Approve this proof & quote</button></form>`:''}
      ${order.status==='REQUESTED'?'<form class="attach-artwork"><label>Add private artwork<input type="file" name="file" accept=".png,.jpg,.jpeg,.pdf,.svg" required></label><button type="submit" class="button secondary">Upload artwork</button></form>':''}
      ${order.carrier?`<p><strong>${esc(order.carrier)}</strong> · ${esc(order.tracking)}</p>`:''}
      <details><summary>Build timeline</summary><ul>${order.timeline.map(event=>`<li>${esc(when(event.created_at))} · ${esc(event.customer_message)}</li>`).join('')}</ul></details><p class="business-message card-message" role="status"></p></article>`;
  }
  function renderOrders() {
    $('customerBuilds').innerHTML = orders.length ? orders.map(cardHtml).join('') : '<p class="empty-business">Your first build starts with a quote request.</p>';
    $('supportOrder').innerHTML = '<option value="">General question</option>' + orders.map(o=>`<option value="${esc(o.id)}">${esc(o.id)} · ${esc(labels[o.status])}</option>`).join('');
    for (const card of $('customerBuilds').querySelectorAll('[data-order]')) {
      const order=orders.find(o=>o.id===card.dataset.order);
      card.querySelector('.approve-proof')?.addEventListener('submit',async event=>{
        event.preventDefault(); await cardAction(card,event.submitter,async()=>api('business-approve',{orderId:order.id,revision:order.revision,proofId:order.proof.id,acceptQuote:true}),'Proof and quote approved.');
      });
      card.querySelector('.attach-artwork')?.addEventListener('submit',async event=>{
        event.preventDefault(); const file=event.target.querySelector('input[type=file]').files[0];
        await cardAction(card,event.submitter,()=>uploadFile(order.id,'artwork',file),'Private artwork saved.');
      });
    }
  }
  async function cardAction(card,button,action,success) {
    const status=card.querySelector('.card-message'); button.disabled=true; status.textContent='Saving…';
    try { await action(); await refresh(); message('businessAvailability',success); }
    catch(error) { status.textContent=error.message;status.classList.add('error');button.disabled=false; }
  }
  async function uploadFile(orderId,purpose,file) {
    if(!file || file.size<1 || file.size>10485760) throw new Error('Choose an artwork file between 1 byte and 10 MB.');
    const data=new FormData();data.set('orderId',orderId);data.set('purpose',purpose);data.set('file',file);
    return api('business-upload',data);
  }
  function renderTickets(target,tickets,team=false) {
    $(target).innerHTML=tickets.length?tickets.map(ticket=>`<article class="build-card" data-ticket="${esc(ticket.id)}"><div class="build-meta"><span>${esc(ticket.kind)}</span><span>${esc(ticket.state)}</span></div><h3>${esc(ticket.subject)}</h3><p>${esc(ticket.order_id || 'General support')}</p>${ticket.messages.map(m=>`<div class="ticket-thread"><small>${esc(m.sender)} · ${esc(when(m.created_at))}</small>${esc(m.body)}</div>`).join('')}<form class="reply-ticket"><label>Reply<textarea maxlength="4000" rows="3" required></textarea></label>${team?'<label class="check-row"><input type="checkbox">Close this request after the reply.</label>':''}<button class="button secondary" type="submit">Save reply</button></form><p class="card-message business-message" role="status"></p></article>`).join(''):'<p class="empty-business">No support conversations yet.</p>';
    for(const card of $(target).querySelectorAll('[data-ticket]'))card.querySelector('form').addEventListener('submit',async event=>{
      event.preventDefault();await cardAction(card,event.submitter,()=>api('business-reply',{ticketId:card.dataset.ticket,body:event.target.querySelector('textarea').value,close:!!event.target.querySelector('input[type=checkbox]')?.checked}),'Reply saved.');
    });
  }
  async function refresh() {
    if(!ready())return;
    const generation=++refreshing;
    if(teamPage){
      if(!(session.user?.roles || []).length)return;
      const data=await api('business-dashboard');if(generation!==refreshing || !ready())return;
      orders=data.orders;stock=data.stock;renderTeam(data);
    }else{
      const [builds,tickets,updates]=await Promise.all([api('business-orders'),api('business-tickets'),api('business-updates')]);
      if(generation!==refreshing || !ready())return;
      orders=builds.orders;renderOrders();renderTickets('customerTickets',tickets.tickets);
      $('customerUpdates').innerHTML=updates.updates.length?updates.updates.map(u=>`<li>${esc(when(u.created_at))} · ${esc(u.order_id)}<br>${esc(u.customer_message)}</li>`).join(''):'<li>Your first build update will appear here.</li>';
    }
  }

  function useDraft() {
    if(teamPage)return;
    try { const data=JSON.parse(sessionStorage.getItem(draftKey)||'null'); imported=Array.isArray(data)&&data.length>0&&data.length<=20?data:null; }catch{ imported=null; }
    $('singleBuildFields').hidden=!!imported;
    for(const field of $('singleBuildFields').querySelectorAll('input,select,textarea'))field.disabled=!!imported;
    $('importedBuilds').hidden=!imported;$('clearImportedBuilds').hidden=!imported;
    if(imported)$('importedBuilds').textContent=imported.map((item,i)=>`${i+1}. ${item.product} · ${item.size}\n${item.artwork}\n${item.artworkSource==='upload'?'Your uploaded artwork':'Mirroried LED team design'}`).join('\n\n');
  }
  if(!teamPage){
    useDraft();
    $('clearImportedBuilds').addEventListener('click',()=>{try{sessionStorage.removeItem(draftKey);}catch{}useDraft();});
    $('buildProduct').addEventListener('change',()=>{$('buildSize').placeholder=$('buildProduct').value==='Layered Stadium Model'?'Mini, Medium or Collector':'24×24, or custom dimensions';});
    $('refreshBuilds').addEventListener('click',()=>refresh().catch(error=>message('businessAvailability',error.message,true)));
    $('buildRequestForm').addEventListener('submit',async event=>{
      event.preventDefault();if(!ready())return;
      const button=$('saveBuildRequest');button.disabled=true;message('buildRequestMessage','Saving your build request…');
      let saved;
      try{
        const items=imported||[{product:$('buildProduct').value,size:$('buildSize').value,quantity:Number($('buildQuantity').value),artwork:$('buildArtwork').value,artworkSource:$('buildArtworkSource').value,lighting:$('buildLighting').value,finish:$('buildFinish').value,notes:$('buildNotes').value}];
        const file=$('buildArtworkFile').files[0];
        const builderFiles=[];
        for(const item of items.filter(item=>item.builderDraftId)){
          const draft=await window.MirrorDraftStore?.get(item.builderDraftId);
          if(!draft?.maskBlob)throw new Error('This browser no longer has your engraving image. Return to the Infinity Mirror builder to restore it, or attach the artwork manually.');
          builderFiles.push(new File([draft.maskBlob],`Infinity-${item.id}-engraving.png`,{type:'image/png'}));
          if(draft.originalBlob&&draft.state?.artwork?.source==='upload'){
            const ext={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[draft.originalBlob.type];
            if(ext)builderFiles.push(new File([draft.originalBlob],`Infinity-${item.id}-source.${ext}`,{type:draft.originalBlob.type}));
          }
        }
        if(items.some(item=>item.artworkSource==='upload'&&!item.builderDraftId)&&!file)throw new Error('Choose the artwork file, or select a Mirroried LED team design.');
        if(file&&file.size>10485760)throw new Error('Artwork files must be 10 MB or smaller.');
        if(builderFiles.length+(file?1:0)>20||builderFiles.reduce((sum,f)=>sum+f.size,0)+(file?.size||0)>52428800)throw new Error('Split this build list into smaller quote requests so its artwork stays within the 20-file / 50 MB limit.');
        saved=await api('business-request',{items:items.map(item=>({...item,size:item.product==='Layered Stadium Model'&&item.size==='Mid'?'Medium':item.size}))});
        try{
          if(imported){
            const ids=new Set(imported.map(item=>item.id).filter(Boolean));
            const current=JSON.parse(localStorage.getItem('mirroriedled_storefront_cart_vnext')||'[]');
            if(Array.isArray(current)&&ids.size)localStorage.setItem('mirroriedled_storefront_cart_vnext',JSON.stringify(current.filter(item=>!ids.has(item.id))));
          }
          sessionStorage.removeItem(draftKey);
        }catch{}useDraft();$('buildRequestForm').reset();
        if(file)await uploadFile(saved.order.id,'artwork',file);
        for(const artFile of builderFiles)await uploadFile(saved.order.id,'artwork',artFile);
        for(const item of items.filter(item=>item.builderDraftId))await window.MirrorDraftStore.remove(item.builderDraftId).catch(()=>{});
        await refresh();message('buildRequestMessage',`Saved ${saved.order.id}. The team will review your quote request.`);
      }catch(error){if(saved){await refresh().catch(()=>{});message('buildRequestMessage',`${saved.order.id} was saved. ${error.message} Attach the file to that request below.`,true);}else message('buildRequestMessage',error.message,true);}
      finally{button.disabled=!ready();}
    });
    $('supportRequestForm').addEventListener('submit',async event=>{
      event.preventDefault();await formAction('supportRequestForm','supportRequestMessage',async()=>{
        await api('business-ticket',{kind:$('supportKind').value,orderId:$('supportOrder').value||null,subject:$('supportSubject').value,body:$('supportBody').value});$('supportRequestForm').reset();
      },'Support request saved.');
    });
  }

  async function formAction(formId,messageId,action,success) {
    if(!ready())return;const button=$(formId).querySelector('button[type=submit]');button.disabled=true;message(messageId,'Saving…');
    try{await action();await refresh();message(messageId,success);}catch(error){message(messageId,error.message,true);}finally{button.disabled=!ready();}
  }
  function orderPayload(extra={}) { if(!selectedOrder)throw new Error('Choose a build first.');return {orderId:selectedOrder.id,revision:selectedOrder.revision,...extra}; }
  function options(id,items,filter=()=>true) { $(id).innerHTML='<option value="">Choose a file</option>'+items.filter(filter).map(file=>`<option value="${esc(file.id)}">${esc(file.name)}</option>`).join(''); }
  function renderSelected() {
    selectedOrder=orders.find(o=>o.id===$('teamOrder').value)||null;
    const order=selectedOrder;const state=order?.status;
    $('teamOrderDetails').innerHTML=order?`<div class="build-card"><div class="build-meta"><span>${esc(labels[state])}</span><span>Revision ${esc(order.revision)}</span><span>${esc(money(order.quoteCents))}</span></div><h3>${esc(order.customer.name)}</h3><p>${esc(order.customer.email)}</p>${itemsHtml(order.items)}<p>${filesHtml(order.files)}</p>${order.proof?`<p class="proof-summary">Proof ${esc(order.proof.version)}: ${esc(order.proof.summary)}</p>`:''}<p><strong>Materials reserved</strong></p><ul>${order.reservations.map(r=>`<li>${esc(r.name)} · ${esc(r.lot)} · ${esc(qty(r.quantity))} ${esc(r.unit)}</li>`).join('')||'<li>No materials reserved.</li>'}</ul>${order.machine?`<p>${esc(order.machine)} · ${esc(when(order.scheduledAt))}</p>`:''}<div class="business-actions"><button type="button" id="downloadManifest" class="button secondary">Download shop handoff</button></div></div>`:'<p class="empty-business">New customer build requests will appear here.</p>';
    const mutable=['REQUESTED','QUOTED','APPROVED'].includes(state);
    $('teamFileForm').hidden=!mutable||!hasRole('sales','production');
    $('teamQuoteForm').hidden=!mutable||!hasRole('sales');
    $('teamReserveForm').hidden=!mutable||!hasRole('inventory','production');
    $('teamReleaseForm').hidden=state!=='APPROVED'||!hasRole('production');
    $('teamBuildPanel').hidden=state!=='READY'||!hasRole('production');
    $('teamQcForm').hidden=!['BUILDING','QC_HOLD'].includes(state)||!hasRole('qc');
    $('teamFulfillForm').hidden=!['QC_PASSED','FULFILLING'].includes(state)||!hasRole('fulfillment');
    $('teamCancelForm').hidden=!['REQUESTED','QUOTED','APPROVED','READY'].includes(state)||!hasRole('sales','production');
    $('teamFulfillButton').textContent=state==='FULFILLING'?'Record completed delivery / pickup':'Record shipment / pickup';
    options('teamProofFile',order?.files||[],f=>f.purpose==='proof');options('teamProductionFile',order?.files||[],f=>f.purpose==='production');
    $('teamStock').innerHTML='<option value="">Choose an inspected lot</option>'+stock.filter(s=>s.quality==='PASSED').map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${esc(s.lot)} · ${esc(qty(s.quantity-s.reserved))} ${esc(s.unit)} available</option>`).join('');
    if($('downloadManifest')){ $('downloadManifest').hidden=!hasRole('production');$('downloadManifest').addEventListener('click',async()=>{
      try{const data=await api('business-manifest',null,{orderId:order.id});const url=URL.createObjectURL(new Blob([JSON.stringify(data.manifest,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=order.id+'-shop-handoff.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
      catch(error){message('teamActionMessage',error.message,true);}
    });}
    if(order){$('teamCarrier').value=order.carrier||'';$('teamTracking').value=order.tracking||'';}
  }
  function renderTeam(data) {
    const previous=$('teamOrder').value;
    $('teamOrder').innerHTML=orders.map(o=>`<option value="${esc(o.id)}">${esc(o.customer.name)} · ${esc(o.id.slice(-8))} · ${esc(labels[o.status])}</option>`).join('');
    if(orders.some(o=>o.id===previous))$('teamOrder').value=previous;renderSelected();
    const open=orders.filter(o=>['REQUESTED','QUOTED'].includes(o.status)).length;
    const builds=orders.filter(o=>['READY','BUILDING'].includes(o.status)).length;
    const holds=orders.filter(o=>o.status==='QC_HOLD').length;
    const low=stock.filter(s=>s.quality==='PASSED'&&s.quantity-s.reserved<=s.threshold).length;
    $('operationsKpis').innerHTML=[['Quote reviews',open],['Queued / building',builds],['Quality holds',holds],['Low stock lots',low]].map(([title,value])=>`<div class="kpi"><strong>${esc(value)}</strong>${esc(title)}</div>`).join('');
    $('teamStockRows').innerHTML=stock.map(s=>`<tr><td>${esc(s.name)}<br><small>${esc(s.sku)} · ${esc(s.lot)} · ${esc(s.location)}</small></td><td>${esc(qty(s.quantity-s.reserved))} ${esc(s.unit)}</td><td>${esc(qty(s.reserved))}</td><td>${esc(s.quality)}</td></tr>`).join('')||'<tr><td colspan="4">No received stock lots yet.</td></tr>';
    $('teamReceiveForm').hidden=!hasRole('inventory');
    $('teamTasks').innerHTML=data.tasks.filter(t=>t.state==='OPEN').map(t=>`<article class="build-card" data-task="${esc(t.id)}"><h3>${esc(t.title)}</h3><p>${esc(t.reference)}</p><form><label>Completion evidence<input maxlength="1000" required></label><button type="submit" class="button secondary compact">Record task done</button></form><p class="card-message business-message" role="status"></p></article>`).join('')||'<p class="empty-business">No open tasks.</p>';
    for(const card of $('teamTasks').querySelectorAll('[data-task]'))card.querySelector('form').addEventListener('submit',async event=>{event.preventDefault();await cardAction(card,event.submitter,()=>api('business-task',{taskId:Number(card.dataset.task),note:event.target.querySelector('input').value}),'Task completion recorded.');});
    $('teamIntegrations').innerHTML=Object.entries(data.integrations).map(([name,status])=>`<li><strong>${esc({payments:'Payments',emailSms:'Email / SMS',shipping:'Shipping',laser:'LightBurn / laser',wled:'LED controllers'}[name])}</strong>${esc(status)}</li>`).join('');
    renderTickets('teamTickets',data.tickets,hasRole('support'));
    if(!hasRole('support'))for(const form of $('teamTickets').querySelectorAll('form'))form.hidden=true;
    $('teamAudit').innerHTML=data.audit.map(e=>`<li>${esc(when(e.created_at))} · ${esc(e.kind)} · ${esc(e.order_id||'Operations')} · Actor ${esc(e.actor_id)}</li>`).join('');
  }
  if(teamPage){
    $('teamOrder').addEventListener('change',()=>{renderSelected();message('teamActionMessage','');});
    $('refreshTeam').addEventListener('click',()=>refresh().catch(error=>message('businessAvailability',error.message,true)));
    const bind=(id,action,body,success)=>$(id).addEventListener('submit',event=>{event.preventDefault();formAction(id,'teamActionMessage',()=>api(action,body()),success);});
    $('teamFileForm').addEventListener('submit',event=>{event.preventDefault();formAction('teamFileForm','teamActionMessage',async()=>{const result=await uploadFile(selectedOrder?.id,$('teamFilePurpose').value,$('teamFile').files[0]);$('teamFileForm').reset();return result;},'Private file saved.');});
    bind('teamQuoteForm','business-proof',()=>orderPayload({fileId:$('teamProofFile').value,quoteCents:Math.round(Number($('teamQuoteAmount').value)*100),summary:$('teamProofSummary').value}),'Quote and proof ready for customer review.');
    bind('teamReserveForm','business-reserve',()=>orderPayload({stockId:Number($('teamStock').value),quantity:$('teamReserveQty').value}),'Materials reserved.');
    bind('teamReleaseForm','business-release',()=>orderPayload({fileId:$('teamProductionFile').value,financeReference:$('teamFinanceRef').value,machine:$('teamMachine').value,scheduledAt:Math.floor(new Date($('teamScheduledAt').value).getTime()/1000),minutes:Number($('teamMinutes').value),materialsComplete:$('teamMaterialsComplete').checked,assetReviewed:$('teamAssetReviewed').checked}),'Build released to the local shop queue.');
    $('teamBuildButton').addEventListener('click',async()=>{const button=$('teamBuildButton');button.disabled=true;try{await api('business-build',orderPayload());await refresh();message('teamActionMessage','Build start recorded and reserved materials consumed.');}catch(error){message('teamActionMessage',error.message,true);}finally{button.disabled=false;}});
    bind('teamQcForm','business-qc',()=>orderPayload({passed:$('teamQcResult').value==='pass',note:$('teamQcNote').value,checks:{dimensions:$('qcDimensions').checked,finish:$('qcFinish').checked,electrical:$('qcElectrical').checked,function:$('qcFunction').checked}}),'Quality result recorded.');
    bind('teamFulfillForm','business-fulfill',()=>orderPayload({complete:selectedOrder.status==='FULFILLING',carrier:$('teamCarrier').value,tracking:$('teamTracking').value,note:$('teamFulfillNote').value}),'Delivery / pickup record saved.');
    bind('teamCancelForm','business-cancel',()=>orderPayload({note:$('teamCancelNote').value}),'Request cancelled and reservations released.');
    $('teamReceiveForm').addEventListener('submit',event=>{event.preventDefault();formAction('teamReceiveForm','receiveMessage',()=>api('business-receive',{sku:$('receiveSku').value,name:$('receiveName').value,lot:$('receiveLot').value,location:$('receiveLocation').value,unit:$('receiveUnit').value,quantity:$('receiveQty').value,threshold:$('receiveThreshold').value,costCents:Math.round(Number($('receiveCost').value)*100),quality:$('receiveQuality').value}),'Material receipt recorded.');});
  }
  refreshSession().then(refresh).catch(error=>message('businessAvailability',error.message,true));
})();
