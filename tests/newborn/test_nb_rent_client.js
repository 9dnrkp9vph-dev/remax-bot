// tests/newborn/test_nb_rent_client.js — מתג מכירה/השכרה במסך נכס נולד + תווית בכרטיס (על הקוד האמיתי)
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
function block(constName){
  const st = src.indexOf(constName + ' = ');
  const end = src.indexOf("</html>'''", st);
  const page = src.slice(st, end > 0 ? end : undefined);
  const a = page.indexOf('<script>') + 8, b = page.indexOf('</script>', a);
  return page.slice(a, b);
}
const js = block('V2_NB_HTML');
const kit = (function(){ const st = src.indexOf('V2_NB_KIT = '); const a = src.indexOf('<script>', st) + 8;
  return src.slice(a, src.indexOf('</script>', a)); })();
function fn(code, name){
  const i = code.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let j = code.indexOf('{', i), d = 0;
  for (; j < code.length; j++){ if (code[j] === '{') d++; else if (code[j] === '}' && --d === 0) break; }
  return code.slice(i, j + 1);
}
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };

// ── דף נכס נולד ────────────────────────────────────────────────────────────
const store = {};
const localStorage = {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }};
function mkEl(id){
  const kids = id === 'dealSeg' ? [{attr: '', cls: new Set()}, {attr: 'rent', cls: new Set()}].map(o => ({
    getAttribute: () => o.attr, classList: {toggle: (c, on) => on ? o.cls.add(c) : o.cls.delete(c), contains: c => o.cls.has(c)}})) : [];
  return {id, style: {}, textContent: '', innerHTML: '', value: '', children: kids};
}
const els = {};
const el = id => (els[id] = els[id] || mkEl(id));
const urls = [];
let reply = () => ({});
const GET = u => { urls.push(u); return Promise.resolve(reply(u)); };
const env = {localStorage, el, GET, esc: s => String(s == null ? '' : s), nbCard: (r) => '<card ' + r.key + '>'};
const code = ['var ROWS = [], BUCKETS = [], TOTAL = 0, AGE = -1, MEETS = [];',
  js.match(/var BUCKET_RANGES = [^\n]*/)[0], "var NB_ETAG = '';", 'var NB_FULL = false;', 'var NB_SHOWN = 40;',
  js.match(/var DEAL = [^\n]*/)[0], js.match(/try\{ RENT_OK = [^\n]*/)[0],
  fn(js, '_dealQs'), fn(js, '_setRentOk'), fn(js, 'setNbDeal'), fn(js, '_nbApply'), fn(js, '_nbFull'), fn(js, 'load'), fn(js, 'render'),
  'return {setNbDeal, load, render, st: () => ({DEAL, RENT_OK, ROWS, NB_FULL})};'].join('\n');
const T = new Function(...Object.keys(env), code)(...Object.values(env));
const tick = () => new Promise(r => setTimeout(r, 5));

(async () => {
  // סוכן בלי הרשאה: אין מתג, אין deal בבקשות
  reply = u => u.indexOf('meetings') >= 0 ? {} : {ok: true, results: [{key: 's1'}], bucketCounts: [1], total: 1, rentAllowed: false, deal: ''};
  await T.load(); await tick();
  ck(urls.every(u => u.indexOf('deal=') < 0), 'no deal param by default');
  ck(els.dealSeg.style.display === 'none', 'switch hidden when not allowed');
  ck(store['v2c:nbrent'] === '0', 'remembers not allowed');
  ck(JSON.parse(store['v2c:nb']).r[0].key === 's1', 'sale cache saved');

  // סוכן עם הרשאה: המתג מופיע
  urls.length = 0;
  reply = u => u.indexOf('meetings') >= 0 ? {} : (u.indexOf('deal=rent') >= 0
    ? {ok: true, results: [{key: 'r1', rent: true}], bucketCounts: [1], total: 1, rentAllowed: true, deal: 'rent', partial: u.indexOf('limit=') >= 0}
    : {ok: true, results: [{key: 's1'}], bucketCounts: [1], total: 1, rentAllowed: true, deal: ''});
  await T.load(); await tick();
  ck(els.dealSeg.style.display === 'flex', 'switch shown when allowed');
  ck(els.dealSeg.children[0].classList.contains('on'), 'sale tab on');

  // מעבר להשכרה
  urls.length = 0;
  el('nbBadge').textContent = 'SALE';
  T.setNbDeal('rent'); await tick(); await tick();
  ck(urls.some(u => u.indexOf('/api/newborn?limit=80&deal=rent') === 0), 'first page asks for rent: ' + urls.join(' | '));
  ck(urls.some(u => u === '/api/newborn?deal=rent'), 'full list asks for rent');
  ck(T.st().ROWS[0].key === 'r1' && els.list.innerHTML.indexOf('<card r1>') >= 0, 'rent rows rendered');
  ck(els.dealSeg.children[1].classList.contains('on'), 'rent tab on');
  ck(JSON.parse(store['v2c:nb']).r[0].key === 's1', 'sale cache untouched by rent');
  ck(els.nbBadge.textContent === 'SALE', 'nav badge not set from rent');

  // תשובת מכירה מאוחרת לא דורסת את ההשכרות
  urls.length = 0;
  reply = u => ({ok: true, results: [{key: 's9'}], bucketCounts: [1], total: 1, rentAllowed: true, deal: ''});
  await T.load(); await tick();
  ck(T.st().ROWS[0].key === 'r1', 'stale sale reply ignored on rent tab');

  // חזרה למכירה — מיד מהעותק השמור
  reply = u => ({ok: true, results: [{key: 's1'}], bucketCounts: [1], total: 1, rentAllowed: true, deal: ''});
  T.setNbDeal('');
  ck(T.st().ROWS[0].key === 's1', 'back to sale from cache instantly');
  await tick(); await tick();

  // ההרשאה בוטלה בזמן שעומד על השכרה → חוזר למכירה
  T.setNbDeal('rent'); await tick(); await tick();
  reply = u => ({ok: true, results: [], bucketCounts: [], total: 0, rentAllowed: false, deal: 'rent'});
  await T.load(); await tick(); await tick();
  ck(T.st().DEAL === '' && T.st().RENT_OK === false, 'revoked → back to sale');

  // ── הכרטיס המשותף ──────────────────────────────────────────────────────────
  const kenv = {esc: s => String(s == null ? '' : s), MGR: false, ST_LABEL: {}};
  const kcode = [fn(kit, 'nbFmtPrice'), fn(kit, 'nbCard'), 'return nbCard;'].join('\n');
  const nbCard = new Function(...Object.keys(kenv), kcode)(...Object.values(kenv));
  const hr = nbCard({key: 'r1', rent: true, price: '4,500', address: 'בגין 12', city: 'קרית מוצקין', ageDays: 0}, 0);
  ck(hr.indexOf('>להשכרה<') >= 0 && hr.indexOf('לחודש') >= 0, 'rent card: tag + per month');
  const hs = nbCard({key: 's1', price: '1,900,000', address: 'הרצל 5', city: 'קרית ביאליק', ageDays: 0}, 0);
  ck(hs.indexOf('להשכרה') < 0 && hs.indexOf('לחודש') < 0, 'sale card unchanged');
  console.log('ok', n);
})().catch(e => { console.error(e); process.exit(1); });

// ── ניהול: מתג 'השכרות בנכס נולד' בכרטיס החבר ─────────────────────────────────
(function(){
  const st = src.indexOf('V2_ADMIN_HTML = ');
  const page = src.slice(st, src.indexOf("</html>'''", st));
  const a = page.indexOf('<script>') + 8, js2 = page.slice(a, page.indexOf('</script>', a));
  const posts = []; let sheet = '';
  const tg = {cls: new Set(), classList: {contains: c => tg.cls.has(c)}};
  const P0 = {name: 'יוסי לוי', role: 'agent', phone: '522222222', vphone: '', nbRent: false};
  const env2 = {
    el: id => id === 'teamList' ? {_list: [P0]} : id === 'tgRent' ? tg : id === 'tgSusp' ? {classList: {contains: () => false}} : null,
    esc: s => String(s == null ? '' : s), seg: () => '', coordAgentsOf: () => [], PEOPLE: [P0], COORDS: [],
    openSheet: h => { sheet = h; }, POST: (u, d) => { posts.push([u, d]); return Promise.resolve({ok: true}); },
    closeSheet: () => {}, toast: () => {}, boot: () => {}, _pickedNames: () => [],
  };
  const code2 = ['var SEL_ROLE = "agent";', fn(js2, 'openMember'), fn(js2, 'saveMember'), 'return {openMember, saveMember};'].join('\n');
  const A2 = new Function(...Object.keys(env2), code2)(...Object.values(env2));
  A2.openMember(0);
  ck(sheet.indexOf('השכרות בנכס נולד') >= 0 && sheet.indexOf('id="tgRent"') >= 0, 'toggle in member sheet');
  ck(sheet.indexOf('ממתי רואה מודעות') < 0, 'old delay setting gone');
  A2.saveMember(0);
  ck(!posts.some(p => p[0] === '/api/dev/agent_update'), 'no update when unchanged');
  tg.cls.add('on'); A2.saveMember(0);
  const up = posts.find(p => p[0] === '/api/dev/agent_update');
  ck(up && up[1].newbornRent === true && up[1].name === 'יוסי לוי', 'saves newbornRent=true');
  console.log('admin ok', n);
})();
