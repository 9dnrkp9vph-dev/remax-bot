// [HOME-BUNDLE 06/11] loadData האמיתי של הבית: בקשה מאוחדת, השלמת חלקים חסרים, ונפילה לישן
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const a = src.indexOf('function loadData(){\n  var ldFailed');
const b = src.indexOf("document.addEventListener('visibilitychange'", a);
const code = src.slice(a, b);
let fails = 0;
function ok(c, m){ if (!c){ fails++; console.log('FAIL', m); } else console.log('ok', m); }

const FULL = {
  '/api/newborn/meetings': {ok: true, results: [{date: '2026-11-06T10:00'}]},
  '/api/report?period=week': {ok: true, label: 'השבוע', listings: 9, summary: {calls: {total: 5}, sigs: {total: 2}, sigsList: [{a: 1}], exclusives: [{}, {}]}},
  '/api/my/buyers': {ok: true, results: [{date: '01/01/2020', agent: ''}, {date: '01/01/2020', agent: 'x'}]},
  '/api/my/properties': {ok: true, count: 4},
  '/api/signatures': {ok: true, signatures: [{type: 'בלעדיות', ts: Math.floor(Date.now() / 1000), address: 'a', client: 'c'}]},
  '/v2/api/sign/drafts': {ok: true, drafts: [{client: 'd'}]},
  '/api/deals': {ok: true, items: [{deal: false}, {deal: true}, {deal: false}]},
  '/api/newborn?limit=120': {ok: true, total: 2600, results: [{ageDays: 0, address: 'h', city: 'c'}]},
  '/v2/api/dialer/access': {ok: true, allowed: true},
};
const KEY = {meets: '/api/newborn/meetings', report: '/api/report?period=week', buyers: '/api/my/buyers',
  props: '/api/my/properties', sigs: '/api/signatures', drafts: '/v2/api/sign/drafts', deals: '/api/deals',
  nb: '/api/newborn?limit=120', dialer: '/v2/api/dialer/access'};

async function run(bundle){
  const urls = [], els = {};
  const ctx = {
    M: {meets: [], meetToday: 0, meetLate: 0}, STORY: {open: false}, CO: 1, LD_TRY: 0, LD_TS: 0,
    el: id => (els[id] = els[id] || {style: {}, textContent: '', innerHTML: ''}),
    parseDMY: () => new Date(2020, 0, 1), dayDiff: () => -100,
    renderDash(){ ctx.paints++; }, homeSnapSave(){}, renderCard(){}, _homeMeetCounts(){}, _homeNbBadge(){},
    setTimeout(){ ctx.retry = true; }, paints: 0, retry: false,
    GET(u){
      urls.push(u);
      if (u === '/v2/api/home/bundle') return bundle === 'reject' ? Promise.reject(new Error('x')) : Promise.resolve(bundle);
      return Promise.resolve(FULL[u]);
    },
  };
  const f = new Function(...Object.keys(ctx), code + '; return loadData;');
  await f(...Object.values(ctx))();
  return {ctx, urls, els};
}

(async () => {
  const parts = {};
  for (const k in KEY) parts[k] = FULL[KEY[k]];
  let r = await run({ok: true, parts});
  ok(r.urls.length === 1, 'full bundle → one request only');
  ok(r.ctx.M.calls === 5 && r.ctx.M.props === 4 && r.ctx.M.buyersTot === 2 && r.ctx.M.buyersUn === 1, 'numbers applied');
  ok(r.ctx.M.exclWeek.length === 1 && r.ctx.M.drafts.length === 1 && r.ctx.M.meets.length === 1, 'sigs/drafts/meets');
  ok(r.ctx.M.nb === 2600 && r.ctx.M.nbNew.length === 1, 'newborn counter');
  ok(r.els.dealsBadge.textContent === 2 && r.els.dealsBadge.style.display === 'flex', 'deals badge');
  ok(r.els.menuDialer.style.display === 'flex', 'dialer menu');
  ok(!r.ctx.retry && r.ctx.M.ready, 'no retry, ready');

  const p2 = Object.assign({}, parts); delete p2.sigs; delete p2.nb;
  r = await run({ok: true, parts: p2, miss: ['sigs', 'nb']});
  ok(r.urls.length === 3 && r.urls.includes('/api/signatures') && r.urls.includes('/api/newborn?limit=120'), 'missing parts fetched alone');
  ok(r.ctx.M.exclWeek.length === 1 && r.ctx.M.nb === 2600, 'missing parts applied');

  r = await run('reject');
  ok(r.urls.length === 10, 'bundle failed → all 9 old requests');
  ok(r.ctx.M.calls === 5 && r.els.menuDialer.style.display === 'flex', 'old path still works');

  r = await run({ok: false});
  ok(r.urls.length === 10, 'old server (404 json) → old requests');

  const p3 = Object.assign({}, parts, {report: {ok: false}});
  r = await run({ok: true, parts: p3});
  ok(r.ctx.retry === true, 'hard part error → retry scheduled');
  const p4 = Object.assign({}, parts, {deals: {ok: false}});
  r = await run({ok: true, parts: p4});
  ok(r.ctx.retry === false, 'soft part error → no retry');

  console.log(fails ? fails + ' FAILED' : 'ALL OK'); process.exit(fails ? 1 : 0);
})();
