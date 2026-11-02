// tests/props/test_remove_why.js — [REMOVE-WHY 02/11] מחיקת נכס שואלת למה; 'אני מכרתי' מסמן נמכר באתר
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const code = src.slice(src.indexOf('function reqRemove(i){'), src.indexOf('function doneListing(i){'));
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };
function run(DEAL, why, siteOk){
  const calls = [], toasts = []; let sheet = '', MINE = [{id: 'a1'}, {id: 'b2'}];
  const list = {_src: [{id: 'a1', address: 'אהוד מנור 11', city: 'קרית ביאליק'}]};
  const env = {el: id => id === 'list' ? list : {value: ''}, esc: x => String(x), openSheet: h => { sheet = h; },
    closeSheet(){}, render(){}, load(){}, toast: t => toasts.push(t),
    POST: (u, b) => { calls.push([u, b]); return Promise.resolve(u.includes('site') ? {ok: siteOk} : {ok: true}); }};
  const f = new Function(...Object.keys(env), 'DEAL', 'MINE', code + '; return {reqRemove, doRemove};');
  const api = f(...Object.values(env), DEAL, MINE);
  api.reqRemove(0);
  return {sheet, calls, toasts, go: () => { api.doRemove(0, why); return new Promise(r => setTimeout(r, 5)); }};
}
(async () => {
  let t = run('', 'sold', true);
  ck(/אני מכרתי/.test(t.sheet) && /נגמרה הבלעדיות/.test(t.sheet) && /ביטול/.test(t.sheet), 'sale sheet has both choices');
  await t.go();
  ck(t.calls[0][0] === '/v2/api/site/prop' && t.calls[0][1].sold === true && t.calls[0][1].key === 'a1', 'sold marks site first');
  ck(t.calls[1][0] === '/api/listing/request' && t.calls[1][1].reason === 'sold' && t.calls[1][1].kind === 'remove', 'then removal with reason');
  ck(/נכסים שמכרנו/.test(t.toasts[0]), 'toast tells site');
  t = run('', 'excl_end', true); await t.go();
  ck(t.calls.length === 1 && t.calls[0][1].reason === 'excl_end', 'exclusivity end — no site mark');
  t = run('', 'sold', false); await t.go();
  ck(t.calls.length === 2 && /לא הצלחנו/.test(t.toasts[0]), 'site fail still removes, says so');
  t = run('rent', 'closed', true);
  ck(!/אני מכרתי/.test(t.sheet) && /סגרתי עסקה/.test(t.sheet), 'rent: no "sold"');
  await t.go();
  ck(t.calls.length === 1 && t.calls[0][1].reason === 'closed', 'rent closed — no site mark');
  console.log('ok', n);
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
