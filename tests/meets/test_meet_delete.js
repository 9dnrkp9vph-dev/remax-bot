// tests/meets/test_meet_delete.js — כפתור מחיקה בכרטיס היומן /v2/meets (על הקוד האמיתי)
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const start = src.indexOf('V2_MEETS_HTML = ');
const a = src.indexOf('<script>', start) + 8, b = src.indexOf('</script>', a);
const js = src.slice(a, b);
function fn(name){   // חילוץ פונקציה לפי שם, עם התאמת סוגריים
  const i = js.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let j = js.indexOf('{', i), d = 0;
  for (; j < js.length; j++){ if (js[j] === '{') d++; else if (js[j] === '}' && --d === 0) break; }
  return js.slice(i, j + 1);
}
function vr(name){ const m = js.match(new RegExp('var ' + name + ' = [^\\n]*')); if (!m) throw new Error('missing var ' + name); return m[0]; }
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };
const calls = [];
let confirmAns = true;
const env = {
  MEETS: [{skey: 'אייל::manual:1', status: 'meeting', addr: 'נעמי שמר 18', date: '2026-10-23T10:00', agent: 'אייל'}],
  MULTI: false,
  POST: (u, d) => { calls.push([u, d]); return Promise.resolve({ok: true}); },
  toast: (m) => calls.push(['toast', m]),
  load: () => calls.push(['load']),
  confirm: (m) => { calls.push(['confirm', m]); return confirmAns; },
};
const code = [vr('CAL_SVG'), vr('FU_SVG'), vr('LATE_SVG'), fn('esc'), fn('parseWhen'), fn('dayDiff'), fn('whoLine'), fn('itemRow'), fn('delMeet')].join('\n');
const T = new Function(...Object.keys(env), code + ';return {itemRow, delMeet};')(...Object.values(env));
const h = T.itemRow(env.MEETS[0], 0);
ck(h.includes('onclick="delMeet(0)"'), 'trash button in card');
ck(h.includes('#FBEDED') && h.includes('aria-label="מחיקה"'), 'trash style + label');
// ביטול באישור — לא נמחק
confirmAns = false; T.delMeet(0);
ck(!calls.some(c => c[0] === '/api/newborn/status/delete'), 'no delete when cancelled');
// אישור — מוחק לפי skey ומרענן
confirmAns = true; calls.length = 0; T.delMeet(0);
const conf = calls.find(c => c[0] === 'confirm');
ck(conf && conf[1].includes('נעמי שמר 18') && conf[1].includes('Google'), 'confirm mentions address + calendar');
const p = calls.find(c => c[0] === '/api/newborn/status/delete');
ck(p && p[1].skey === 'אייל::manual:1', 'POST delete by skey');
setTimeout(() => {
  ck(calls.some(c => c[0] === 'load') && calls.some(c => c[0] === 'toast'), 'reload + toast after delete');
  console.log('ok', n);
}, 10);
