// tests/meets/test_refresh_ui.js — [PTR 28/10] פס 'מתעדכן', 'עודכן' ומשיכה לרענון (על הקוד האמיתי ב-V2_BOOST)
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
function block(tag){
  const a = src.indexOf('/* [' + tag + '] start */'), b = src.indexOf('/* [' + tag + '] end */');
  if (a < 0 || b < 0) throw new Error('missing block ' + tag);
  return src.slice(a, b);
}
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };

// ── סביבה מזויפת: טיימרים ידניים + DOM מינימלי ──
let now = 0, timers = [];
const setTimeout_ = (f, ms) => { const t = {f, at: now + (ms || 0), id: timers.length + 1}; timers.push(t); return t.id; };
const clearTimeout_ = id => { timers = timers.filter(t => t.id !== id); };
function tick(ms){   // שעון שמתקדם טיימר-טיימר (טיימר שנקבע תוך כדי נכנס לאותו חלון)
  const end = now + ms; let due;
  while ((due = timers.filter(t => t.at <= end).sort((a, b) => a.at - b.at)).length){
    const t = due[0]; timers = timers.filter(x => x !== t); now = Math.max(now, t.at); t.f();
  }
  now = end;
}
function mkEl(id){ const cls = new Set(); return {id, style: {}, attrs: {}, innerHTML: '', textContent: '', children: [],
  classList: {add: c => cls.add(c), remove: c => cls.delete(c), contains: c => cls.has(c), toggle: (c, v) => { (v === undefined ? !cls.has(c) : v) ? cls.add(c) : cls.delete(c); }},
  setAttribute(k, v){ this.attrs[k] = v; }, appendChild(c){ this.children.push(c); return c; }, closest(){ return null; }}; }
const created = {};
const body = mkEl('body'); body.style = {};
const docListeners = {};
const winListeners = {};
let hasNav = true, reloaded = 0, scrollY = 0;
const document = {
  body, documentElement: Object.assign(mkEl('html'), {scrollTop: 0}),
  createElement(){ const e = mkEl(''); return e; },
  getElementById(id){ return created[id] || null; },
  querySelector(s){ return s === 'nav' ? (hasNav ? {} : null) : null; },
  addEventListener(t, f){ (docListeners[t] = docListeners[t] || []).push(f); },
};
const origAppend = body.appendChild.bind(body);
body.appendChild = c => { origAppend(c); if (c.id) created[c.id] = c; return c; };
const sstore = {};
const window = {
  ontouchstart: null,
  get scrollY(){ return scrollY; },
  addEventListener(t, f){ (winListeners[t] = winListeners[t] || []).push(f); },
  location: {reload(){ reloaded++; }},
};
const sessionStorage = {getItem: k => (k in sstore ? sstore[k] : null), setItem: (k, v) => { sstore[k] = String(v); }, removeItem: k => { delete sstore[k]; }};

const code = block('BUSY') + '\n' + block('PTR');
new Function('window', 'document', 'setTimeout', 'clearTimeout', 'sessionStorage', 'location', code)(
  window, document, setTimeout_, clearTimeout_, sessionStorage, window.location);
const B = window.v2Busy;
ck(B && typeof B.wrap === 'function', 'v2Busy exposed');

// ── אילו בקשות נספרות ──
ck(B.tracked('/api/my/buyers', {}) === true, 'data GET tracked');
ck(B.tracked('/api/search/properties', {method: 'POST'}) === true, 'data POST tracked');
ck(B.tracked('/v2/api/ping', {method: 'POST', keepalive: true}) === false, 'heartbeat not tracked');
ck(B.tracked('/v2/api/story/view', {keepalive: true}) === false, 'keepalive not tracked');
ck(B.tracked('/api/auth/whoami', {}) === false, 'whoami not tracked');
ck(B.tracked('/v2/api/wa/click', {}) === false, 'wa click not tracked');
ck(B.tracked('/assets/logo', {}) === false, 'non-api not tracked');

// ── בקשה איטית: פס אחרי 400ms, 'עודכן' בסוף הסבב הראשון ──
function deferred(){ let r; const p = new Promise(res => { r = res; }); return {p, r}; }
const flush = () => new Promise(r => global.setImmediate(r));
(async () => {
  const d1 = deferred();
  B.wrap('/api/my/buyers', {}, d1.p);
  tick(300); const bar = created['v2busy'];
  ck(!bar || !bar.classList.contains('on'), 'no bar before 400ms (no flicker)');
  tick(200);
  ck(created['v2busy'] && created['v2busy'].classList.contains('on'), 'bar shown while loading');
  d1.r({ok: true}); await flush(); tick(200);
  ck(!created['v2busy'].classList.contains('on'), 'bar hidden when done');
  const chip = created['v2fresh'];
  ck(chip && chip.classList.contains('on') && /עודכן/.test(chip.innerHTML), 'fresh chip after first cycle');
  tick(2000);
  ck(!chip.classList.contains('on'), 'chip disappears');

  // ── רענון רקע (סבב שני): פס כן, 'עודכן' לא ──
  const d2 = deferred(); B.wrap('/api/history', {}, d2.p); tick(500);
  ck(created['v2busy'].classList.contains('on'), 'bar on background refresh');
  d2.r({}); await flush(); tick(200);
  ck(!chip.classList.contains('on'), 'no chip on background poll');

  // ── בקשה שלא חוזרת: הפס לא נתקע לנצח ──
  B.wrap('/api/never', {}, new Promise(() => {})); tick(31000);
  ck(!created['v2busy'].classList.contains('on'), 'stuck request released after 30s');

  // ── משיכה לרענון ──
  const ts = docListeners.touchstart[0], tm = docListeners.touchmove[0], te = docListeners.touchend[0];
  const tgt = {closest: () => null, parentElement: null, nodeType: 1, scrollTop: 0};
  const T = y => ({touches: [{clientY: y}], target: tgt});
  // משיכה קצרה — לא מרענן
  ts(T(100)); tm(T(150)); te({});
  ck(reloaded === 0, 'short pull does not refresh');
  // לא בראש המסך — לא מרענן
  scrollY = 200; ts(T(100)); tm(T(400)); te({}); scrollY = 0;
  ck(reloaded === 0, 'pull when scrolled down does nothing');
  // גיליון פתוח — לא מרענן
  body.style.overflow = 'hidden'; ts(T(100)); tm(T(400)); te({}); body.style.overflow = '';
  ck(reloaded === 0, 'pull with open sheet does nothing');
  // משיכה מלאה — מרענן ומסמן ל'עודכן' אחרי הטעינה
  ts(T(100)); tm(T(300));
  ck(created['v2ptr'] && created['v2ptr'].classList.contains('ready'), 'indicator ready past threshold');
  te({}); tick(50);
  ck(reloaded === 1, 'full pull reloads');
  ck(sstore['v2ptr'] === '1', 'reload flagged for fresh chip');
  // דף שמגדיר v2Refresh — בלי טעינה מחדש
  window.v2Refresh = () => Promise.resolve();
  const before = reloaded;
  ts(T(100)); tm(T(300)); te({}); tick(50); await flush(); tick(50);
  ck(reloaded === before, 'v2Refresh used instead of reload');
  console.log('ok', n);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
