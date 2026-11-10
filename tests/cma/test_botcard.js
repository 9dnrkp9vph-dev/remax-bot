// CMA — כרטיס "בקש עסקאות עדכניות" במסך ניתוח שוק: בקשה, המתנה לתשובה וחישוב מחדש. הרצה: node tests/cma/test_botcard.js
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'cma.py'), 'utf8');
const html = src.slice(src.indexOf("V2_CMA_HTML = r'''"));
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
let fails = 0; const ck = (c, m) => { console.log((c ? 'ok  ' : 'FAIL') + '  ' + m); if (!c) fails++; };
const els = {st: {value: 'דולב'}, hs: {value: '3'}, ct: {value: 'קרית ים'}, rm: {value: '5'}, sq: {value: ''}, pt: {value: 'דירה'},
             res: {innerHTML: ''}, botMsg: {textContent: ''}, botBtn: {disabled: false}};
const calls = []; let timers = [];
const replies = {};
const env = {
  localStorage: {getItem: () => 't'}, location: {replace() {}},
  document: {getElementById: id => els[id]},
  setTimeout: (f) => { timers.push(f); return timers.length; }, clearTimeout() {},
  fetch: (url, opt) => { calls.push({url, body: opt && opt.body}); const k = Object.keys(replies).find(p => url.indexOf(p) === 0);
    const v = typeof replies[k] === 'function' ? replies[k]() : replies[k];
    return Promise.resolve({status: 200, json: () => Promise.resolve(v)}); },
};
const f = new Function(...Object.keys(env), js + '; return {botAsk, botPoll, BOT, run};')(...Object.values(env));
const tick = () => new Promise(r => setImmediate(r));
(async () => {
  replies['/v2/api/cma/bot_request'] = {ok: true, request_id: 'cma-1'};
  let polls = 0;
  replies['/v2/api/cma/bot_status'] = () => (++polls < 2 ? {ok: true, done: false} : {ok: true, done: true, saved: true, n: 20});
  replies['/v2/api/cma/view'] = {ok: true, cma: null, reason: 'few'};
  f.botAsk(); for (let i = 0; i < 6; i++) await tick();
  ck(JSON.parse(calls[0].body).address === 'דולב 3, קרית ים', 'sends "street house, city"');
  ck(els.botMsg.textContent.indexOf('6 דקות') >= 0 && els.botBtn.disabled, 'shows waiting message, button disabled');
  ck(timers.length === 1, 'not answered → polls again later');
  timers.shift()(); for (let i = 0; i < 8; i++) await tick();
  ck(calls.some(c => c.url.indexOf('/v2/api/cma/view') === 0), 'answer arrived → recalculates');
  ck(f.BOT.msg.indexOf('הגיעו 20 עסקאות') >= 0 && !f.BOT.busy, 'tells how many deals arrived');
  replies['/v2/api/cma/bot_request'] = {ok: false, reason: 'daily_cap'};
  f.botAsk(); for (let i = 0; i < 6; i++) await tick();
  ck(els.botMsg.textContent.indexOf('תקרת') >= 0 && !f.BOT.busy, 'daily cap → clear message');
  console.log('\n' + fails + ' failures'); process.exit(fails ? 1 : 0);
})();
