const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../stadiums/core.js');

const catalog = {
  currency: 'USD',
  sizes: [{id:'mini',label:'Mini',testPrice:99.99},{id:'medium',label:'Medium',testPrice:199.99}],
  products: [
    {id:'dodgers',sport:'baseball',league:'MLB',team:'Los Angeles Dodgers',venue:'Dodger Stadium',previewType:'model-concept',images:[{src:'concept.webp'}]},
    {id:'rams',sport:'football',league:'NFL',team:'Los Angeles Rams',venue:'SoFi Stadium',previewType:'model-concept',images:[{src:'concept.webp'}]},
    {id:'celtics',sport:'basketball',league:'NBA',team:'Boston Celtics',venue:'',previewType:'pending',images:[]}
  ]
};

test('changing sports clears an incompatible team filter', () => {
  assert.deepEqual(core.normalize(catalog.products,{sport:'football',team:'dodgers'}),{sport:'football',team:'all'});
  assert.deepEqual(core.filter(catalog.products,{sport:'football',team:'dodgers'}).map(p=>p.id),['rams']);
});

test('a selected team narrows the sport catalog', () => {
  assert.deepEqual(core.filter(catalog.products,{sport:'baseball',team:'dodgers'}).map(p=>p.team),['Los Angeles Dodgers']);
  assert.equal(core.filter(catalog.products,{sport:'all',team:'all'}).length,3);
});

test('placeholder selections recalculate from the catalog and reject unknown sizes', () => {
  assert.equal(core.selection(catalog,'dodgers','mini').testUnitPrice,99.99);
  assert.equal(core.selection(catalog,'dodgers','medium').testUnitPrice,199.99);
  assert.throws(()=>core.selection(catalog,'dodgers','huge'),/Choose a stadium/);
});

test('the Customer Portal quote handoff excludes placeholder money', () => {
  assert.equal(typeof core.quoteItem,'function','Stadiums need a handoff to the current Customer Portal');
  const item=core.quoteItem(catalog,'dodgers','medium');
  assert.equal(item.product,'Layered Stadium Model');
  assert.equal(item.size,'Medium');
  assert.equal(item.quantity,1);
  assert.equal(item.artworkSource,'team-design');
  assert.match(item.artwork,/Los Angeles Dodgers.*Dodger Stadium/);
  for(const field of ['testUnitPrice','price','unitPrice','total','quoteCents','priceMode'])assert.equal(Object.hasOwn(item,field),false);
  assert.doesNotMatch(item.notes,/199\.99|99\.99/);
  assert.match(item.notes,/final quote/i);
});

test('missing stadium artwork still creates an honest custom design request', () => {
  assert.equal(typeof core.quoteItem,'function','Stadium quote handoff is required');
  const item=core.quoteItem(catalog,'celtics','mini');
  assert.match(item.artwork,/Boston Celtics/);
  assert.match(item.notes,/design proof/i);
  assert.throws(()=>core.quoteItem(catalog,'unknown','mini'),/Choose a stadium/);
});
