// tests/signpage/test_signform_fields.js — אייל 10/11: כתובת לקוח + מייל בטופס ההחתמה → שורות בכותרת ההסכם
// מריץ את submitSign האמיתי מ-V2_SIGN_HTML עם DOM מדומה ובודק את הכותרת שנשלחת לשרת.
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const page = src.slice(src.indexOf("V2_SIGN_HTML = r'''"), src.indexOf("'''", src.indexOf("V2_SIGN_HTML = r'''") + 20));
const scripts = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL ' + m); n++; };
function run(vals){
  const els = {}, posts = [];
  const mk = id => els[id] || (els[id] = {id, value: vals[id] || '', textContent: '', style: {}, dataset: {signed: '1'}, disabled: false,
    classList: {add(){}, remove(){}, toggle(){}}, appendChild(){}, set innerHTML(v){}, get innerHTML(){return '';},
    getBoundingClientRect: () => ({width: 300, left: 0, top: 0}), getContext: () => new Proxy({}, {get: () => () => {}}),
    toDataURL: () => 'data:x', parentNode: {style: {}}, querySelectorAll: () => [], addEventListener(){}});
  const store = {};
  const ctx = {console, setTimeout: () => 0, clearTimeout(){}, encodeURIComponent, JSON, Promise, Object, String, Math, Date, Array,
    localStorage: {getItem: k => store[k] || null, setItem: (k, v) => store[k] = v, removeItem: k => delete store[k]},
    location: {href: '', replace(){}, search: ''},
    document: {getElementById: mk, querySelector: () => mk('main'), querySelectorAll: () => [], createElement: () => mk('x'),
      addEventListener(){}, body: mk('body')},
    fetch: (u, o) => { if (o && o.method === 'POST') posts.push({u, b: JSON.parse(o.body)});
      return Promise.resolve({ok: true, json: () => Promise.resolve(u.indexOf('/api/sign/contract') >= 0 ? {ok: true, title: 'T', body: 'B SALE_FEE'} : {ok: true, name: 'רועי לוי'})}); },
    navigator: {}, addEventListener(){}, alert(){}};
  ctx.window = ctx; vm.createContext(ctx);
  try { vm.runInContext(scripts, ctx); } catch (e) { if (process.env.DBG) console.error("init", e.message); }
  ctx.toast = m => { if (process.env.DBG) console.error("toast", m); };
  vm.runInContext("MODE='remote';PROPS=[{addr:'הנביאים 54 קרית אתא',price:'2,100,000'}];" +
    "DEALS_DEF.forEach(function(d){d.on=(d.k==='buy'||d.k==='sale');if(d.on){d.val='1';d.un='%';}});BUSY=false;", ctx);
  vm.runInContext('submitSign()', ctx);
  return new Promise(r => setTimeout.call ? setImmediate(() => setImmediate(() => setImmediate(() => r(posts)))) : r(posts));
}
(async () => {
  let posts = await run({cName: 'שחר קרובי', cPhone: '0587816168', cId: '', cAddr: '  הנביאים 54\nקרית אתא ', cMail: ' karubis1509@gmail.com '});
  const p = posts.find(x => x.u === '/api/sign/send_remote');
  ck(p, 'נשלח send_remote ' + JSON.stringify(posts.map(x => x.u)));
  const lines = p.b.header.split('\n');
  ck(lines.includes('כתובת הלקוח: הנביאים 54 קרית אתא'), p.b.header);
  ck(lines.includes('מייל הלקוח: karubis1509@gmail.com'), p.b.header);
  ck(lines[0].startsWith('תאריך:') && lines[1].startsWith('לקוח: שחר קרובי') && lines[2].startsWith('נכס: הנביאים 54'), p.b.header);
  posts = await run({cName: 'שחר', cPhone: '0587816168', cAddr: '', cMail: ''});
  const p2 = posts.find(x => x.u === '/api/sign/send_remote');
  ck(p2 && p2.b.header.split('\n').length === 3, 'בלי השדות — הכותרת כמו קודם: ' + (p2 && p2.b.header));
  console.log('OK', n);
})().catch(e => { console.error(e.message); process.exit(1); });
