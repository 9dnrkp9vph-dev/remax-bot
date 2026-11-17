// tests/social_video/test_ui.js — כפתור "צור סרטון" בכרטיס הנכס + אזור "סרטונים" בכלי המפתח (על הקוד האמיתי ב-effie_v2.py)
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
function fn(js, name) {
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
const vst = pjs.slice(pjs.indexOf('var VID_ST = '), pjs.indexOf('};', pjs.indexOf('var VID_ST = ')) + 2);
vm.runInContext('var SOC = {dev:false, user:false, mode:"preview", items:{}, asked:{}, busy:{}}; var VID = {items:{}, busy:{}, asked:{}};\n' + vst + '\n' +
  fn(pjs, 'socWhen') + '\n' + fn(pjs, 'socOn') + '\n' + fn(pjs, 'vidRow') + '\n' + fn(pjs, 'socRow'), ctx);
const P = {id: 'tok1'};
ck(ctx.vidRow(P) === '', 'not logged in yet → empty');
// [18/11 אייל] הכפתורים נפתחו לסוכנים ולמתאמות — רק בטאב "שלי"; למפתח — כמו קודם, בכל הטאבים
{
  const full = {id: 'v1', status: 'approved', publish_at: '2026-11-07T06:00:00+00:00', created_at: '2026-11-06T10:00:00+00:00'};
  ctx.VID.items.tok1 = {last: null, can: {ok: true, reason: ''}};
  ctx.SOC.items.tok1 = {last: null, can: {fb: {ok: true}, ig: {ok: true}}};
  vm.runInContext('SOC.user = true; SOC.mode = "publish";', ctx);
  ck(ctx.socOn() && ctx.vidRow(P).includes("vidCreate('tok1')") && ctx.socRow(P).includes("socPublish('tok1')"), 'agent sees both buttons in "mine"');
  ctx.MODE = 'office'; ck(!ctx.socOn() && ctx.vidRow(P) === '' && ctx.socRow(P) === '', 'agent: nothing in the office tab');
  ctx.MODE = 'mine';
  ctx.VID.items.tok1 = {last: full, can: {ok: false, reason: 'x'}};
  ck(!ctx.vidRow(P).includes('vidNow('), 'agent: no "publish now" (developer only)');
  ctx.VID.items.tok1 = {last: Object.assign({}, full, {status: 'partial', publish_at: null}), can: {ok: false, reason: 'x'}};
  ck(!ctx.vidRow(P).includes('vidRetry('), 'agent: no retry (developer only)');
  ctx.VID.items.tok1 = {last: Object.assign({}, full, {status: 'pending', publish_at: null}), can: {ok: false, reason: 'x'}};
  ck(ctx.vidRow(P).includes('vidResend('), 'agent can resend the approval message');
  ctx.VID.items.tok1 = {last: null, can: {ok: false, reason: 'הגעת למגבלה היומית — 2 פרסומים ידניים ביום'}};
  ck(ctx.vidRow(P).includes('הגעת למגבלה היומית') && ctx.vidRow(P).includes('disabled'), 'cap reason shown');
  vm.runInContext('SOC.dev = true;', ctx);
  ctx.MODE = 'office'; ck(ctx.socOn(), 'developer: every tab'); ctx.MODE = 'mine';
  ctx.VID.items.tok1 = {last: full, can: {ok: false, reason: 'x'}};
  ck(ctx.vidRow(P).includes('vidNow('), 'developer keeps "publish now"');
  vm.runInContext('SOC.dev = false; SOC.user = false; SOC.mode = "preview"; VID.items = {}; SOC.items = {};', ctx);
}
ck(/SOC\.user = true/.test(PROPS) && /function socLoad\(list\)\{\s*if \(!socOn\(\)\) return;/.test(PROPS)
   && /function vidLoad\(list\)\{\s*if \(!socOn\(\)\) return;/.test(PROPS), 'whoami + loaders use socOn');
vm.runInContext('SOC.dev = true; SOC.mode = "publish";', ctx);
ck(ctx.vidRow(P) === '', 'nothing loaded → empty');
ctx.VID.items.tok1 = {last: null, can: {ok: true, reason: ''}};
let h = ctx.vidRow(P);
ck(h.includes('צור סרטון') && h.includes("vidCreate('tok1')") && /min-height:44px/.test(h) && h.includes('#C29435'), h);
ctx.VID.items.tok1 = {last: {id: 'v1', status: 'pending', created_at: new Date().toISOString(), video_token: 'Tk1'}, can: {ok: false, reason: 'כבר נוצר סרטון ב-02/11'}};
h = ctx.vidRow(P);
ck(h.includes('ממתין לאישור') && h.includes('/v2/social/vid/Tk1.mp4') && h.includes('disabled'), h);
// [02/11] ממתין — כפתור "שלח שוב לאישור", והסיבה כשלא נשלח
ck(h.includes("vidResend('v1')") && h.includes('שלח שוב לאישור'), h);
ctx.VID.items.tok1.last.error = 'לא נשלח לאישור בוואטסאפ (0505709865)';
h = ctx.vidRow(P);
ck(h.includes('לא נשלח לאישור בוואטסאפ') && h.includes('#C24040') === false, h);
delete ctx.VID.items.tok1.last.error;
ctx.VID.items.tok1.last = {id: 'v1', status: 'published', created_at: new Date().toISOString(), ig_story_status: 'ok', ig_reel_status: 'ok', fb_story_status: 'ok', fb_reel_status: 'ok', ig_reel_permalink: 'https://ig/r'};
h = ctx.vidRow(P);
ck(h.replace(/<[^>]+>/g, '').includes('פורסם') && h.includes('4/4') && h.includes('href="https://ig/r"'), h);
ctx.VID.items.tok1.last = {id: 'v1', status: 'partial', created_at: new Date().toISOString(), ig_story_status: 'ok', ig_reel_status: 'failed', fb_story_status: 'ok', fb_reel_status: 'ok'};
h = ctx.vidRow(P);
ck(h.includes('3/4') && h.includes("vidRetry('v1')"), h);
// [02/11] ערוץ כבוי (סטורי פייסבוק) לא נספר במכנה
ctx.VID.items.tok1.last = {id: 'v1', status: 'published', created_at: new Date().toISOString(), ig_story_status: 'ok', ig_reel_status: 'ok', fb_story_status: 'off', fb_reel_status: 'ok'};
h = ctx.vidRow(P); ck(h.includes('3/3') && !h.includes('/4'), h);
// [06/11] אושר ונדחה (שבת/לילה) → "פרסם עכשיו" + מתי יעלה
ctx.VID.items.tok1.last = {id: 'v1', status: 'approved', publish_at: '2026-11-07T06:00:00+00:00', created_at: new Date().toISOString()};
h = ctx.vidRow(P);
ck(h.includes("vidNow('v1')") && h.includes('פרסם עכשיו') && h.includes('אושר — ממתין') && h.includes('#2E6BD6'), h);
ctx.VID.items.tok1.last = {id: 'v1', status: 'approved', created_at: new Date().toISOString()};
ck(!ctx.vidRow(P).includes('vidNow'), 'approved without delay → no button');
ctx.VID.busy.tok1 = 1; ck(ctx.vidRow(P).includes('disabled') && ctx.vidRow(P).includes('בהכנה'), 'busy'); delete ctx.VID.busy.tok1;
ctx.MODE = 'shtaf'; ck(ctx.vidRow(P) === '', 'shtaf hidden'); ctx.MODE = 'mine';
ctx.DEAL = 'commercial'; ck(ctx.vidRow(P) === '', 'commercial hidden'); ctx.DEAL = '';
vm.runInContext('SOC.mode = "preview"', ctx);
ctx.VID.items.tok1 = {last: null, can: {ok: true, reason: ''}};
ck(ctx.vidRow(P).includes('מצב בדיקה'), 'preview label');
ck(!/[\u{1F300}-\u{1FAFF}✅❌]/u.test(fn(pjs, 'vidRow')), 'no emoji in UI');
ctx.POSTS = []; ctx.POST = (u, d) => { ctx.POSTS.push([u, d]); return {then: () => ({catch: () => {}})}; };
ctx.toast = () => {}; ctx.render = () => {}; ctx.setTimeout = () => {};
vm.runInContext(fn(pjs, 'vidCreate'), ctx);
ctx.vidCreate('tok1'); ctx.vidCreate('tok1');
ck(ctx.POSTS.length === 1 && ctx.POSTS[0][0] === '/v2/api/social/video', ctx.POSTS);
vm.runInContext(fn(pjs, 'vidNow'), ctx);
ctx.vidNow('v1'); ctx.vidNow('v1');
ck(ctx.POSTS.filter(x => x[0] === '/v2/api/social/video/now').length === 1 && ctx.POSTS[ctx.POSTS.length - 1][1].id === 'v1', ctx.POSTS);
ck(/socRow\(p\) \+ vidRow\(p\)/.test(PROPS) && /vidLoad\(src\)/.test(PROPS) && PROPS.includes('/v2/api/social/videos?keys='), 'wired in card');
ck(DEV.includes('<h2>סרטונים לרשתות</h2>') && /loadVid\(\)/.test(DEV) && DEV.includes('/v2/api/social/video/health') && DEV.includes('<video'), 'dev card');
console.log('video_ui OK', n);
