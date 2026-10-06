(()=>{
  'use strict';
  const catalog=window.MLED_STADIUMS,core=window.MLED_STADIUM_CORE;
  const $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[s]));
  const money=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:catalog.currency}).format(v);
  const KEY='mledStadiumTestSelectionV1';
  let active=null,imageIndex=0,selections=[];
  try{const saved=JSON.parse(localStorage.getItem(KEY)||'[]');if(Array.isArray(saved))selections=saved.slice(0,100).map(s=>{try{return core.selection(catalog,s.stadiumId,s.size)}catch{return null}}).filter(Boolean);}catch{}
  function placeholder(){return '<div class="stadium-placeholder"><span aria-hidden="true">🏟</span><small>Model preview coming soon</small></div>';}
  function renderTeams(){
    const f=core.normalize(catalog.products,{sport:$('sportFilter').value,team:$('teamFilter').value});
    $('teamFilter').innerHTML='<option value="all">All teams</option>'+catalog.products.filter(p=>f.sport==='all'||p.sport===f.sport).sort((a,b)=>a.team.localeCompare(b.team)).map(p=>`<option value="${esc(p.id)}">${esc(p.team)}</option>`).join('');
    $('teamFilter').value=f.team;
  }
  function render(){
    const products=core.filter(catalog.products,{sport:$('sportFilter').value,team:$('teamFilter').value});
    $('catalogCount').textContent=`${products.length} ${products.length===1?'team':'teams'} · ${products.filter(p=>p.images.length).length} with saved previews`;
    $('stadiumGrid').innerHTML=products.map(p=>`<article class="stadium-card">${p.images.length?`<img class="stadium-card-image" src="${esc(p.images[0].thumb)}" alt="${esc(p.team+' — '+p.images[0].caption)}" loading="lazy" width="600" height="400">`:placeholder()}<div class="stadium-card-copy"><div class="eyebrow">${esc(p.sport)} · ${esc(p.league)}</div><h2>${esc(p.venue||p.team)}</h2><p>${esc(p.venue?p.team:'Custom arena / stadium build')}</p><small>${p.previewType==='model-concept'?'MODEL CONCEPT':p.previewType==='layout-preview'?'STYLIZED LAYOUT PREVIEW':'ARTWORK TO BE ADDED'}</small><button data-id="${esc(p.id)}" type="button" aria-label="View ${esc(p.team)} build">VIEW BUILD →</button></div></article>`).join('');
    $('stadiumGrid').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>open(b.dataset.id)));
  }
  function renderImage(){
    const img=active.images[imageIndex];
    $('detailImage').innerHTML=img?`<img src="${esc(img.src)}" alt="${esc(active.team+' — '+img.caption)}">`:placeholder();
    $('imageCaption').textContent=img?`${imageIndex+1} / ${active.images.length} · ${img.caption}`:'A custom design will be prepared for approval.';
    $('previousImage').disabled=$('nextImage').disabled=active.images.length<2;
  }
  function price(){
    const s=core.selection(catalog,active.id,$('buildSize').value);
    $('buildPrice').textContent=money(s.testUnitPrice);
  }
  function open(id){
    active=catalog.products.find(p=>p.id===id);if(!active)return;
    imageIndex=0;$('detailLeague').textContent=active.league+' · '+active.sport;
    $('detailTitle').textContent=active.venue||active.team;
    $('detailTeam').textContent=active.team;
    $('detailStatus').textContent=active.previewType==='layout-preview'?'This is a stylized layout concept. Your final stadium design is confirmed before production.':active.images.length?'Concept previews shown. Your finished build follows the approved design proof.':'Artwork for this team is being added. You can still request a custom build.';
    $('selectionStatus').textContent='';$('buildSize').value='medium';renderImage();price();$('stadiumDetail').showModal();
    $('closeDetail').focus();
  }
  function renderSelection(){
    $('testSelection').hidden=!selections.length;
    $('testLines').innerHTML=selections.map((s,i)=>`<div class="stadium-test-line"><span>${esc(s.team)} · ${esc(s.sizeLabel)}</span><span><b>${money(s.testUnitPrice)}</b><button data-index="${i}" type="button" aria-label="Remove ${esc(s.team)} ${esc(s.sizeLabel)}">REMOVE</button></span></div>`).join('');
    $('testTotal').textContent=money(selections.reduce((total,s)=>total+s.testUnitPrice,0));
    $('testLines').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{selections.splice(Number(b.dataset.index),1);saveSelection();}));
  }
  function saveSelection(){try{localStorage.setItem(KEY,JSON.stringify(selections));}catch{}renderSelection();}
  $('sportFilter').addEventListener('change',()=>{renderTeams();render();});
  $('teamFilter').addEventListener('change',render);
  $('resetFilters').addEventListener('click',()=>{$('sportFilter').value='all';$('teamFilter').value='all';renderTeams();render();});
  $('buildSize').innerHTML=catalog.sizes.map(s=>`<option value="${esc(s.id)}">${esc(s.label)}</option>`).join('');
  $('buildSize').addEventListener('change',price);
  $('previousImage').addEventListener('click',()=>{imageIndex=(imageIndex+active.images.length-1)%active.images.length;renderImage();});
  $('nextImage').addEventListener('click',()=>{imageIndex=(imageIndex+1)%active.images.length;renderImage();});
  $('closeDetail').addEventListener('click',()=>$('stadiumDetail').close());
  $('addTest').addEventListener('click',()=>{if(selections.length>=100){$('selectionStatus').textContent='Clear some sample selections to add another.';return;}selections.push(core.selection(catalog,active.id,$('buildSize').value));saveSelection();$('selectionStatus').textContent='Added to your sample selection. No order placed.';});
  $('requestQuote').addEventListener('click',()=>{
    const cartKey='mirroriedled_storefront_cart_vnext',draftKey='mirroriedled_quote_draft_v1';
    let previous=null,saved=false;
    try{
      previous=localStorage.getItem(cartKey);
      const cart=JSON.parse(previous||'[]');
      if(!Array.isArray(cart))throw new Error('Your saved build list could not be read. Review it on the homepage first.');
      if(cart.length>=20)throw new Error('Your build list is full. Review it in the Customer Portal first.');
      const item={id:crypto.randomUUID(),...core.quoteItem(catalog,active.id,$('buildSize').value)};
      cart.push(item);
      localStorage.setItem(cartKey,JSON.stringify(cart));saved=true;
      sessionStorage.setItem(draftKey,JSON.stringify(cart));
      location.href='../customer-portal/#builds';
    }catch(error){
      if(saved)try{if(previous===null)localStorage.removeItem(cartKey);else localStorage.setItem(cartKey,previous);}catch{}
      $('selectionStatus').textContent=error.message||'Your browser could not save this build. Use the website contact form for a quote.';
    }
  });
  $('clearTest').addEventListener('click',()=>{selections=[];saveSelection();});
  renderTeams();render();renderSelection();
})();
