// tests/kit/test_client.js — תיק פרזנטציה, צד הלקוח (Task 5): על הקוד האמיתי מתוך effie_v2.py
const fs = require('fs'), path = require('path'), cp = require('child_process'), os = require('os');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');

function page(constName, endMark){
  const st = src.indexOf(constName + ' = ');
  if (st < 0) throw new Error('missing ' + constName);
  const end = src.indexOf(endMark, st);
  return src.slice(st, end > 0 ? end + endMark.length : undefined);
}
function scripts(html){   // כל ה-<script> בלי src
  const out = []; let i = 0;
  for (;;){
    const a = html.indexOf('<script>', i); if (a < 0) break;
    const b = html.indexOf('</script>', a);
    out.push(html.slice(a + 8, b)); i = b + 9;
  }
  return out;
}
function fn(code, name){
  const i = code.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let j = code.indexOf('{', i), d = 0;
  for (; j < code.length; j++){ if (code[j] === '{') d++; else if (code[j] === '}' && --d === 0) break; }
  return code.slice(i, j + 1);
}
function syntax(label, code){
  const f = path.join(os.tmpdir(), 'kitck_' + label + '_' + process.pid + '.js');
  fs.writeFileSync(f, code);
  try { cp.execFileSync('node', ['--check', f], {stdio: 'pipe'}); }
  catch (e){ throw new Error('syntax ' + label + ': ' + e.stderr); }
  finally { fs.unlinkSync(f); }
}
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };

const KITS = page('V2_KITS_HTML', '</html>"""');
const MEETS = page('V2_MEETS_HTML', '</html>"""');
const HOME = page('V2_HOME_HTML', "</html>'''");
const ADMIN = page('V2_ADMIN_HTML', "</html>'''");
const NBKIT = page('V2_NB_KIT', '</script>');
const kjs = scripts(KITS).join('\n');
[['kits', KITS], ['meets', MEETS], ['home', HOME], ['admin', ADMIN], ['nbkit', NBKIT]].forEach(([l, h]) =>
  scripts(h).forEach((s, k) => syntax(l + k, s)));
n++;

// ── פונקציות טהורות במסך התיקים ─────────────────────────────────────────────
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const T = new Function('esc', [fn(kjs, 'kitPad'), fn(kjs, 'kitStatusChip'), fn(kjs, 'kitViews'), fn(kjs, 'kitSendBtn'),
  fn(kjs, 'kitManualErr'), fn(kjs, 'kitTakenMsg'), 'return {kitStatusChip, kitViews, kitSendBtn, kitManualErr, kitTakenMsg};'].join('\n'))(esc);

const chip = st => T.kitStatusChip(st);
ck(chip({status: 'pending'}).includes('בהכנה'), 'pending → בהכנה');
ck(chip({status: 'pending'}).includes('#7A5E1C'), 'pending gold text');
const rj = chip({status: 'rejected', reject_reason: 'מחיר לא נכון'});
ck(rj.includes('נדחה') && rj.includes('מחיר לא נכון'), 'rejected + reason: ' + rj);
ck(!rj.includes('#C24040'), 'rejected not red');
ck(chip({status: 'rejected'}).includes('נדחה') && !chip({status: 'rejected'}).includes(' · '), 'rejected no reason');
ck(chip({status: 'rejected', reject_reason: '<b>'}).includes('&lt;b&gt;'), 'reason escaped');
ck(chip({status: 'approved'}).includes('מוכן לשליחה') && chip({status: 'approved'}).includes('#2E6BD6'), 'approved blue');
ck(chip({status: 'sent'}).includes('נשלח') && chip({status: 'sent'}).includes('#157A43'), 'sent green');
ck(chip({status: 'expired'}).includes('פג תוקף') && chip({status: 'expired'}).includes('#6B7280'), 'expired grey');
const tk = chip({status: 'taken', taken_by: 'דנה <כהן>'});
ck(tk.includes('נשלח ע״י דנה &lt;כהן&gt;') && tk.includes('#6B7280'), 'taken chip grey: ' + tk);
ck(T.kitSendBtn({status: 'taken', wa: '9725', text: 't'}, 0) === '', 'no send on taken');
ck(T.kitTakenMsg('דנה כהן') === 'לבעל הנכס הזה כבר נשלח תיק ע״י דנה כהן', 'taken msg');

const ts = new Date(2026, 10, 9, 14, 5).getTime() / 1000;
const v = T.kitViews({opens: 2, secs: 150, last: ts});
ck(v === "נפתח 2 פעמים · 3 דק' · לאחרונה 09/11 14:05", 'views line: ' + v);
ck(T.kitViews({}) === 'עוד לא נפתח', 'views empty');
ck(T.kitViews(null) === 'עוד לא נפתח', 'views null');
ck(T.kitViews({opens: 1, secs: 20, last: ts}).startsWith('נפתח פעם אחת · 1 דק'), 'views one');

const k = {status: 'approved', wa: '972544448065', text: 'שלום', id: 'x'};
ck(T.kitSendBtn(k, 0).includes('שלח לבעל הנכס'), 'send on approved');
ck(T.kitSendBtn(k, 0).includes('#157A43'), 'send green');
ck(T.kitSendBtn(Object.assign({}, k, {status: 'sent'}), 0).includes('שלח לבעל הנכס'), 'send on sent');
['pending', 'rejected', 'expired'].forEach(s => ck(T.kitSendBtn({status: s, wa: '1', text: 't'}, 0) === '', 'no send on ' + s));
ck(T.kitSendBtn({status: 'approved'}, 0) === '', 'no send without wa');

ck(T.kitManualErr('price') === 'kmPrice', 'price → kmPrice');
ck(T.kitManualErr('owner') === 'kmOwner', 'owner');
ck(T.kitManualErr('phone') === 'kmPhone', 'phone');
ck(T.kitManualErr('addr') === 'kmStreet', 'addr → street');
ck(T.kitManualErr('rooms') === 'kmRooms', 'rooms');
ck(T.kitManualErr('agent') === 'kmAgent' && T.kitManualErr('forbidden') === 'kmAgent', 'agent/forbidden → picker');
ck(T.kitManualErr('db') === '', 'db → no field');

// ── שליחה: wa.me ואז /sent ────────────────────────────────────────────────
(async () => {
  const opened = [], posts = [], toasts = [];
  const env = {
    esc, KITS_: null,
    window: {open: (u, t) => opened.push([u, t])},
    POST: (u, d) => { posts.push([u, d]); return Promise.resolve({ok: true}); },
    toast: m => toasts.push(m), load: () => {},
  };
  const send = new Function(...Object.keys(env), 'var KITS = [{id:"k1",status:"approved",wa:"972544448065",text:"שלום רב"}];\n' +
    fn(kjs, 'kitSend') + '\nreturn kitSend;')(...Object.values(env));
  send(0); await new Promise(r => setTimeout(r, 5));
  ck(opened[0][0] === 'https://wa.me/972544448065?text=' + encodeURIComponent('שלום רב') && opened[0][1] === '_blank', 'wa.me ' + opened[0]);
  ck(posts[0][0] === '/v2/api/kit/sent' && posts[0][1].id === 'k1', 'POST sent');
  // לחיצה כפולה: וואטסאפ אחד ו-/sent אחד
  async function sendRun(reply, taps){
    const O = [], Pp = [], Ts = [], L = [];
    const f = new Function('esc', 'window', 'POST', 'toast', 'load', 'kitTakenMsg',
      'var KITS = [{id:"k2",status:"approved",wa:"9725",text:"t"}];\n' + fn(kjs, 'kitSend') + '\nreturn kitSend;')(
      esc, {open: u => O.push(u)}, (u, d) => { Pp.push(u); return reply(); }, m => Ts.push(m), () => L.push(1), T.kitTakenMsg);
    for (let t = 0; t < taps; t++) f(0);
    await new Promise(r => setTimeout(r, 5));
    return {O, Pp, Ts, L};
  }
  let sr = await sendRun(() => Promise.resolve({ok: true}), 2);
  ck(sr.O.length === 1 && sr.Pp.length === 1, 'double tap guarded ' + sr.O.length + '/' + sr.Pp.length);
  sr = await sendRun(() => Promise.resolve({ok: false, reason: 'status'}), 1);
  ck(sr.Ts[0] === 'לא נשמר שהתיק נשלח — נסה שוב' && sr.L.length === 1, 'sent ok:false → toast + reload');
  sr = await sendRun(() => Promise.resolve({ok: false, reason: 'taken', by: 'רון לוי'}), 1);
  ck(sr.Ts[0] === 'לבעל הנכס הזה כבר נשלח תיק ע״י רון לוי' && sr.L.length === 1, 'sent taken → toast + reload');
  sr = await sendRun(() => Promise.reject(new Error('net')), 1);
  ck(sr.Ts[0] === 'לא נשמר שהתיק נשלח — נסה שוב' && sr.L.length === 1, 'sent network fail → toast + reload');
  ck(/created = 'הוכן ' \+/.test(kjs) && !/'נפתח ' \+ kitPad/.test(kjs), 'created prefix הוכן');
  ck(/#sheet\{[^}]*padding:12px 18px (9\d|1\d\d)px/.test(KITS), 'sheet bottom padding >= 90');

  // ── כרטיס נכס נולד: כפתור + kitFromNb ─────────────────────────────────────
  ck(/<button class="s[^"]*" onclick="kitFromNb\(' \+ i \+ '\)">תיק לפני פגישה<\/button>/.test(NBKIT), 'nb button');
  const nbjs = scripts(NBKIT).join('\n');
  async function nb(reply){
    const P = [], Ts = [];
    const f = new Function('POST', 'toast', 'nbKitRows', fn(nbjs, 'kitFromNb') + '\nreturn kitFromNb;')(
      (u, d) => { P.push([u, d]); return Promise.resolve(reply); }, m => Ts.push(m), () => [{key: 'nbk1'}]);
    f(0); await new Promise(r => setTimeout(r, 5));
    return {P, Ts};
  }
  let r = await nb({ok: true});
  ck(r.P[0][0] === '/v2/api/kit/create' && r.P[0][1].source === 'nb' && r.P[0][1].key === 'nbk1', 'nb POST');
  ck(r.Ts[0] === 'התיק בהכנה · ממתין לאישור', 'nb toast ok');
  r = await nb({ok: false, reason: 'owner'});
  ck(r.Ts[0] === 'חסרים שם או טלפון של בעל הנכס — פתח תיק ידני', 'nb owner');
  r = await nb({ok: false, reason: 'phone'});
  ck(r.Ts[0] === 'חסרים שם או טלפון של בעל הנכס — פתח תיק ידני', 'nb phone');
  r = await nb({ok: false, reason: 'not_found'});
  ck(r.Ts[0] === 'הנכס לא נמצא', 'nb not_found');
  r = await nb({ok: false, reason: 'taken', by: 'רון לוי'});
  ck(r.Ts[0] === 'לבעל הנכס הזה כבר נשלח תיק ע״י רון לוי', 'nb taken');
  r = await nb({ok: false, reason: 'forbidden'});
  ck(r.Ts[0] === 'אין הרשאה לנכס הזה', 'nb forbidden');
  // בזמן שהבקשה בדרך — לחיצה נוספת לא שולחת שוב; אחרי התשובה אפשר שוב
  {
    const P = []; let res;
    const f = new Function('POST', 'toast', 'nbKitRows', fn(nbjs, 'kitFromNb') + '\nreturn kitFromNb;')(
      (u, d) => { P.push(u); return new Promise(x => { res = x; }); }, () => {}, () => [{key: 'k'}]);
    f(0); f(0);
    ck(P.length === 1, 'nb in-flight guard');
    res({ok: true}); await new Promise(x => setTimeout(x, 5));
    f(0);
    ck(P.length === 2, 'nb guard released');
  }

  // ── יומן: כפתור רק לפגישה שאינה ידנית, לפני המחיקה ───────────────────────
  const mjs = scripts(MEETS).join('\n');
  const row = new Function('esc', 'parseWhen', 'dayDiff', 'whoLine', 'LATE_SVG', 'CAL_SVG', 'FU_SVG',
    fn(mjs, 'itemRow') + '\nreturn itemRow;')(esc, () => ({d: null, time: ''}), () => 99, () => '', '', '', '');
  const a = row({status: 'meeting', skey: 'nb:1', addr: 'x'}, 3);
  ck(a.includes('kitFromMeet(3)'), 'meet kit button');
  ck(a.indexOf('kitFromMeet(3)') < a.indexOf('delMeet(3)'), 'kit before delete');
  ck(!row({status: 'meeting', skey: 'manual:1', addr: 'x'}, 3).includes('kitFromMeet'), 'no kit for manual');
  const mP = [];
  const fm = new Function('POST', 'toast', 'MEETS', fn(mjs, 'kitFromMeet') + '\nreturn kitFromMeet;')(
    (u, d) => { mP.push([u, d]); return Promise.resolve({ok: true}); }, () => {}, [{skey: 'nb:9'}]);
  fm(0); await new Promise(r2 => setTimeout(r2, 5));
  ck(mP[0][0] === '/v2/api/kit/create' && mP[0][1].source === 'meet' && mP[0][1].skey === 'nb:9', 'meet POST');
  async function meet(reply){
    const Ts = [];
    const f = new Function('POST', 'toast', 'MEETS', fn(mjs, 'kitFromMeet') + '\nreturn kitFromMeet;')(
      () => reply(), m => Ts.push(m), [{skey: 'nb:9'}]);
    f(0); f(0); await new Promise(x => setTimeout(x, 5));
    return Ts;
  }
  ck((await meet(() => Promise.resolve({ok: false, reason: 'not_found'})))[0] === 'הנכס לא נמצא', 'meet not_found');
  ck((await meet(() => Promise.resolve({ok: false, reason: 'taken', by: 'רון לוי'})))[0] === 'לבעל הנכס הזה כבר נשלח תיק ע״י רון לוי', 'meet taken');
  let mt = await meet(() => Promise.resolve({ok: false, reason: 'forbidden'}));
  ck(mt[0] === 'אין הרשאה לנכס הזה' && mt.length === 1, 'meet forbidden + guard');

  // ── תפריט, ניהול, ראוט ───────────────────────────────────────────────────
  ck(/<a id="menuKits" href="\/v2\/kits" style="display:flex/.test(HOME) && HOME.includes('תיקי פרזנטציה'), 'drawer item');
  ck(ADMIN.includes('id="kitCard"') && ADMIN.includes('תיק פרזנטציה — נתונים קבועים'), 'admin card');
  ck(/dlrLoad\(\);\s*kitLoad\(\);/.test(ADMIN) || /kitLoad\(\)/.test(fn(scripts(ADMIN).join('\n'), 'boot')), 'kitLoad in boot');
  ck(/function kitSave\(\)[\s\S]*?\/v2\/api\/kit\/settings[\s\S]*?toast\('נשמר'\)/.test(ADMIN), 'kitSave');
  ['kitCoop', 'kitRank', 'kitGRating', 'kitGCount', 'kitGUrl', 'kitIg', 'kitFb'].forEach(id => ck(ADMIN.includes('id="' + id + '"'), 'field ' + id));
  ck(ADMIN.includes("instagram: 'kitIg'") && ADMIN.includes("facebook: 'kitFb'") && /KIT_URL_ERR\[j\.reason\]/.test(ADMIN), 'ig/fb load+save+reason');
  ck(/@app\.route\("\/v2\/kits", methods=\["GET"\]\)\s*\n\s*def v2_kits\(\):\s*\n\s*return _page\(V2_KITS_HTML\)/.test(src), 'route');
  ck(KITS.includes('תיקי פרזנטציה') && KITS.includes('עוד אין תיקים') && KITS.includes('פתח תיק מכרטיס בנכס נולד או ידנית'), 'kits copy');
  ck(!/[\u{1F300}-\u{1FAFF}]/u.test(KITS), 'no emoji');
  ck(!/אפי/.test(KITS), 'white-label');
  {
    const Ts = [], L = [];
    const f = new Function('POST', 'toast', 'load', 'kitTakenMsg', 'var KITS = [{id:"k3"}];\n' + fn(kjs, 'kitResend') + '\nreturn kitResend;')(
      () => Promise.resolve({ok: false, reason: 'taken', by: 'רון לוי'}), m => Ts.push(m), () => L.push(1), T.kitTakenMsg);
    f(0); await new Promise(x => setTimeout(x, 5));
    ck(Ts[0] === 'לבעל הנכס הזה כבר נשלח תיק ע״י רון לוי', 'resend taken');
  }
  ck(/j\.reason === 'taken'[^\n]*kitTakenMsg\(j\.by\)/.test(fn(kjs, 'kitManualGo')), 'manual create taken');
  console.log('ok kit client · ' + n + ' checks');
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
