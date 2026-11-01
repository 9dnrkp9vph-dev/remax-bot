// tests/social/test_ui.js — כפתור "פרסם ברשתות" בכרטיס הנכס + כרטיס בכלי המפתח (על הקוד האמיתי ב-effie_v2.py)
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };
function block(name, q) {
  const a = src.indexOf('\n' + name + ' = r' + q); if (a < 0) throw new Error('missing ' + name);
  const s = src.indexOf(q, a) + 3, e = src.indexOf(q, s); return src.slice(s, e);
}
function scripts(html) {
  const out = []; let i = 0;
  for (;;) { const a = html.indexOf('<script>', i); if (a < 0) break; const b = html.indexOf('</script>', a); out.push(html.slice(a + 8, b)); i = b + 9; }
  return out;
}
function fn(js, name) {                      // גוף פונקציה לפי ספירת סוגריים
  const a = js.indexOf('function ' + name + '('); if (a < 0) throw new Error('missing fn ' + name);
  let i = js.indexOf('{', a), d = 0;
  for (; i < js.length; i++) { if (js[i] === '{') d++; else if (js[i] === '}' && --d === 0) break; }
  return js.slice(a, i + 1);
}
const PROPS = block('V2_PROPS_HTML', "'''"), DEV = block('V2_DEV_HTML', "'''");
const pjs = scripts(PROPS).join('\n'), djs = scripts(DEV).join('\n');
[...scripts(PROPS), ...scripts(DEV)].forEach((js, i) => { new vm.Script(js); ck(true, 'syntax ' + i); });

const ctx = {String, Math, JSON, Date, encodeURIComponent, console, DEAL: '', MODE: 'mine',
  esc: s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]))};
vm.createContext(ctx);
ck(pjs.includes('var SOC_RETRY_DAYS = 3;'), 'retry days = 3');
vm.runInContext('var SOC_RETRY_DAYS = 3; var SOC = {dev:false, mode:"preview", items:{}};\n' + fn(pjs, 'socWhen') + '\n' + fn(pjs, 'socRow'), ctx);
const P = {id: 'tok1'};
ck(ctx.socRow(P) === '', 'non-dev → empty');
vm.runInContext('SOC.dev = true; SOC.mode = "publish";', ctx);
ck(ctx.socRow(P) === '', 'no status loaded yet → empty');
vm.runInContext('SOC.items = {tok1: {last: null, can: {fb: {ok: true, reason: ""}, ig: {ok: true, reason: ""}}}}', ctx);
let h = ctx.socRow(P);
ck(h.includes('פרסם ברשתות') && h.includes("socPublish('tok1')") && /min-height:44px/.test(h) && h.includes('#C29435'), h);
vm.runInContext('SOC.items.tok1.can = {fb: {ok:false, reason:"פורסם 20/10 · אפשר שוב מ-03/11"}, ig: {ok:false, reason:"פורסם 20/10 · אפשר שוב מ-03/11"}}', ctx);
h = ctx.socRow(P);
ck(h.includes('disabled') && h.includes('אפשר שוב מ-03/11'), h);
const recent = new Date(Date.now() - 3600e3).toISOString(), old = new Date(Date.now() - 5 * 86400e3).toISOString();
ctx.SOC.items.tok1 = {last: {created_at: recent, fb_status: 'ok', ig_status: 'ok', fb_permalink: 'https://fb/p', ig_permalink: 'https://ig/m'},
                      can: {fb: {ok: false, reason: 'x'}, ig: {ok: false, reason: 'x'}}};
h = ctx.socRow(P);
ck(/פורסם \d\d\/\d\d · פייסבוק ✓ · אינסטגרם ✓/.test(h.replace(/<[^>]+>/g, '')) && h.includes('href="https://fb/p"') && h.includes('target="_blank"'), h);
ctx.SOC.items.tok1 = {last: {created_at: recent, fb_status: 'ok', ig_status: 'failed'}, can: {fb: {ok: false, reason: 'x'}, ig: {ok: true, reason: ''}}};
h = ctx.socRow(P);
ck(h.includes('נסה שוב לאינסטגרם') && h.includes("socPublish('tok1',['ig'])"), h);
ctx.SOC.items.tok1.last.created_at = old;
ck(!ctx.socRow(P).includes('נסה שוב לאינסטגרם'), 'no retry after RETRY_DAYS');
ctx.DEAL = 'commercial'; ck(ctx.socRow(P) === '', 'commercial hidden'); ctx.DEAL = '';
ctx.MODE = 'shtaf'; ck(ctx.socRow(P) === '', 'shtaf hidden'); ctx.MODE = 'office';
ck(ctx.socRow(P) !== '', 'shown in office for dev');
vm.runInContext('SOC.mode = "preview"', ctx);
ctx.SOC.items.tok1 = {last: null, can: {fb: {ok: true, reason: ''}, ig: {ok: true, reason: ''}}};
ck(ctx.socRow(P).includes('מצב בדיקה'), 'preview label');
ck(!/[\u{1F300}-\u{1FAFF}]/u.test(fn(pjs, 'socRow')), 'no emoji in UI');
// [ביקורת סופית C1a] הכפתור ננעל אחרי לחיצה — לא שולחים פעמיים
ctx.POSTS = []; ctx.POST = (u, d) => { ctx.POSTS.push([u, d]); return {then: () => ({catch: () => {}})}; };
ctx.toast = () => {}; ctx.render = () => {}; ctx.setTimeout = () => {};
vm.runInContext(fn(pjs, 'socPublish'), ctx);
ctx.SOC.items.tok1 = {last: null, can: {fb: {ok: true, reason: ''}, ig: {ok: true, reason: ''}}};
ctx.socPublish('tok1'); ctx.socPublish('tok1');
ck(ctx.POSTS.length === 1, 'second click ignored');
h = ctx.socRow(P);
ck(h.includes('disabled') && h.includes('נשלח'), h);

ck(/acts \+ (?:shareRow\(p, i\) \+ )?hotRow \+ fhRow \+ siteRow \+ socRow\(p\)/.test(PROPS), 'row in card');
ck(/SOC\.dev = j\.drole === 'developer'/.test(PROPS), 'dev flag from whoami');
ck(PROPS.includes("/v2/api/social/status?keys="), 'status fetch');

// כלי המפתח
ck(DEV.includes('<h2>פרסום ברשתות</h2>') && /loadSoc\(\)/.test(DEV) && DEV.includes('/v2/api/social/health') && DEV.includes('/v2/api/social/preview?key='), 'dev card');
console.log('social_ui OK', n);
