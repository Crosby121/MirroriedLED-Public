(function(root,factory){
  if(typeof module==='object' && module.exports)module.exports=factory();
  else root.MLED_STADIUM_CORE=factory();
})(typeof window!=='undefined'?window:globalThis,function(){
  'use strict';
  function normalize(products,choice){
    const sport=['all','baseball','football','basketball'].includes(choice.sport)?choice.sport:'all';
    const team=products.some(p=>p.id===choice.team&&(sport==='all'||p.sport===sport))?choice.team:'all';
    return {sport,team};
  }
  function filter(products,choice){
    const f=normalize(products,choice);
    return products.filter(p=>(f.sport==='all'||p.sport===f.sport)&&(f.team==='all'||p.id===f.team))
      .sort((a,b)=>Number(b.previewType==='model-concept')-Number(a.previewType==='model-concept')||Number(b.images.length>0)-Number(a.images.length>0)||a.team.localeCompare(b.team));
  }
  function selection(catalog,id,size){
    const p=catalog.products.find(p=>p.id===id),s=catalog.sizes.find(s=>s.id===size);
    if(!p||!s)throw new Error('Choose a stadium and build size.');
    return {stadiumId:p.id,team:p.team,venue:p.venue,sport:p.sport,size:s.id,sizeLabel:s.label,currency:catalog.currency,testUnitPrice:s.testPrice,priceMode:'placeholder',quoteRequired:true};
  }
  function quoteItem(catalog,id,size){
    const selected=selection(catalog,id,size),product=catalog.products.find(p=>p.id===id);
    return {product:'Layered Stadium Model',size:selected.sizeLabel,quantity:1,
      artwork:product.team+' · '+(product.venue||'Custom venue')+' · '+product.league,
      artworkSource:'team-design',lighting:'To be confirmed',finish:'To be confirmed',
      notes:'Custom '+product.sport+' stadium build. Final dimensions, materials, lighting and price require a final quote and approved design proof.'};
  }
  return {normalize,filter,selection,quoteItem};
});
