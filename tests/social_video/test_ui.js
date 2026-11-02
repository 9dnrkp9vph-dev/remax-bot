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
vm.runInContext('var SOC = {dev:false, mode:"preview", items:{}}; var VID = {items:{}, busy:{}, asked:{}};\n' + vst + '\n' + fn(pjs, 'socWhen') + '\n' + fn(pjs, 'vidRow'), ctx);
const P = {id: 'tok1'};
ck(ctx.vidRow(P) === '', 'non-dev → empty');
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
ck(/socRow\(p\) \+ vidRow\(p\)/.test(PROPS) && /vidLoad\(src\)/.test(PROPS) && PROPS.includes('/v2/api/social/videos?keys='), 'wired in card');
ck(DEV.includes('<h2>סרטונים לרשתות</h2>') && /loadVid\(\)/.test(DEV) && DEV.includes('/v2/api/social/video/health') && DEV.includes('<video'), 'dev card');
console.log('video_ui OK', n);
