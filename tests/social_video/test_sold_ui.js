// tests/social_video/test_sold_ui.js — כפתורי סטורי SOLD: "הנכסים שלי" (מוכר / מוכר+קונה) ותהליכים ועסקאות (קונה)
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
function between(js, a, b) { const i = js.indexOf(a); return js.slice(i, js.indexOf(b, i) + b.length); }
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

// ── הנכסים שלי ──
const pjs = scripts(block('V2_PROPS_HTML', "'''")).join('\n');
ck(pjs.indexOf('soldRow(p)') > 0 && pjs.indexOf('soldLoad(src)') > 0, 'wired into card + render');
const P = {String, esc, DEAL: '', MODE: 'mine', SOC: {dev: false, mode: 'publish'}};
vm.createContext(P);
vm.runInContext(between(pjs, 'var SOLD = {items', '};') + '\n' + between(pjs, 'var SOLD_ST = ', '};') + '\n' + fn(pjs, 'soldRow'), P);
const p = {id: 'tok1'};
ck(P.soldRow(p) === '', 'non-dev → nothing');
P.SOC.dev = true;
let h = P.soldRow(p);
ck(h.includes('סטורי SOLD — נמכר') && h.includes("soldToggle('tok1')"), h);
P.MODE = 'office'; ck(P.soldRow(p) !== '', 'office tab → shown (admin has no mine)');
P.MODE = 'shtaf'; ck(P.soldRow(p) === '', 'shtaf → nothing'); P.MODE = 'mine';
P.DEAL = 'rent'; ck(P.soldRow(p) === '', 'rentals → nothing'); P.DEAL = '';
P.SOLD.open.tok1 = true; h = P.soldRow(p);
ck(h.includes("soldCreate('tok1','seller')") && h.includes("soldBoth('tok1')") && h.includes('ביטול'), h);
// [05/11 אייל] המוכר וגם הקונה → בוחרים מי הביא את הקונה → סרטון משולב
vm.runInContext(fn(pjs, 'soldToggle') + '\n' + fn(pjs, 'soldBoth') + '\n' + fn(pjs, 'soldBA') + '\n' + fn(pjs, 'soldPr') + '\n' + fn(pjs, 'soldCreate') +
  '\nvar RENDERS = 0; function render(){ RENDERS++; } var GETS = [], POSTS = [];' +
  'function GET(u){ GETS.push(u); return {then: function(f){ f({ok: true, agents: [{name: "אלי שמול"}, {name: "יהודית שמול"}]}); return {catch: function(){}}; }}; }' +
  'function POST(u, b){ POSTS.push([u, b]); return {then: function(){ return {catch: function(){}}; }}; } function toast(){}', P);
ck(h.includes("soldBoth('tok1')") && !h.includes("soldCreate('tok1','both')"), 'both opens picker first');
P.soldBoth('tok1'); h = P.soldRow(p);
ck(h.includes('מי הביא את הקונה') && h.includes('<option value="אלי שמול">') && h.includes("soldBA('tok1',1,this.value)") && h.includes("soldCreate('tok1','both')"), h);
ck(P.GETS.length === 1, 'agents loaded once'); P.soldBoth('tok1'); ck(P.GETS.length === 1, 'cached');
P.soldBA('tok1', 0, ' אלי שמול '); P.soldBA('tok1', 1, '');
P.soldCreate('tok1', 'both');
ck(JSON.stringify(P.POSTS[0][1]) === JSON.stringify({key: 'tok1', side: 'both', details: {buyer_agents: ['אלי שמול'], price: ''}}), JSON.stringify(P.POSTS[0]));
// [09/11 אייל] מחיר הסגירה — שדה בטופס (ריק = המחיר מהמודעה), עם פסיקים
delete P.SOLD.busy.tok1; P.SOLD.open.tok1 = true; h = P.soldRow(p);
ck(h.includes('מחיר הסגירה') && h.includes("soldPr('tok1',this)") && h.includes('inputmode="numeric"'), h);
P.soldBoth('tok1'); h = P.soldRow(p); ck(h.includes('מחיר הסגירה'), 'price also in both form');
const el = {value: '1090000'}; P.soldPr('tok1', el);
ck(el.value === (1090000).toLocaleString() && P.SOLD.pr.tok1 === el.value, el.value);
delete P.SOLD.busy.tok1; P.soldCreate('tok1', 'seller');
ck(JSON.stringify(P.POSTS[1][1]) === JSON.stringify({key: 'tok1', side: 'seller', details: {price: (1090000).toLocaleString()}}), JSON.stringify(P.POSTS[1]));
delete P.SOLD.busy.tok1;
P.SOLD.open.tok1 = false;
P.SOLD.items['p:tok1'] = {id: 's1', status: 'rendering', token: 'T1'};
h = P.soldRow(p); ck(h.includes('מכין סטורי') && h.includes('disabled') && !h.includes('צפייה'), h);
P.SOLD.items['p:tok1'] = {id: 's1', status: 'ready', token: 'T1'};
h = P.soldRow(p);
ck(h.includes("soldPublish('s1','tok1')") && h.includes('פרסם לסטורי באינסטגרם ובפייסבוק') && h.includes('/v2/social/vid/T1.mp4'), h);
ck(!h.includes('מצב בדיקה') && h.includes('צור סטורי SOLD מחדש'), h);
P.SOC.mode = 'preview'; ck(P.soldRow(p).includes('(מצב בדיקה)'), 'preview label'); P.SOC.mode = 'publish';
P.SOLD.items['p:tok1'] = {id: 's1', status: 'partial', token: 'T1', ig: 'failed', fb: 'ok', error: 'ig_story: bad'};
h = P.soldRow(p); ck(h.includes('אינסטגרם נכשל') && h.includes('פייסבוק ✓') && h.includes('נסה שוב את מה שנכשל') && h.includes('ig_story: bad'), h);
P.SOLD.items['p:tok1'] = {id: 's1', status: 'published', token: 'T1', ig: 'ok', fb: 'ok'};
h = P.soldRow(p); ck(h.includes('פורסם בסטורי') && !h.includes('soldPublish'), h);

// ── תהליכים ועסקאות ──
const djs = scripts(block('V2_DEALS_HTML', "'''")).join('\n');
ck(djs.indexOf('soldRow(it)') > 0 && djs.indexOf('soldLoad(src.slice(0, 60))') > 0 && djs.indexOf("SOLD.dev = j.drole === 'developer'") > 0, 'deals wired');
const D = {String, esc};
vm.createContext(D);
vm.runInContext(between(djs, 'var SOLD = {dev', '};') + '\n' + between(djs, 'var SOLD_ST = ', '};') + '\n' +
  fn(djs, 'soldOk') + '\n' + fn(djs, 'soldRow'), D);
const it = {id: 'd1', deal: true, side1: 'קונה', side2: 'מוכר', agents: ['רויטל', 'צדוק']};
ck(D.soldRow(it) === '', 'deals non-dev → nothing');
D.SOLD.dev = true;
h = D.soldRow(it); ck(h.includes("soldOpen('d1')") && h.includes('סטורי SOLD — עסקת קונה'), h);
// [05/11] טופס: כתובת ונתונים בהקלדה + בחירת סוכנים (צוות)
vm.runInContext(fn(djs, 'soldBuyers') + '\n' + fn(djs, 'soldOpen') + '\n' + fn(djs, 'soldF') + '\n' + fn(djs, 'soldAg') + '\n' +
  fn(djs, 'soldForm') + '\n' + fn(djs, 'soldSellers') + '\n' + fn(djs, 'soldS') +
  '\nvar ITEMS = []; var AGENTS = []; var RENDERS = 0; function render(){ RENDERS++; }', D);
D.ITEMS.push(Object.assign({}, it, {notes: 'ציזלינג 36', sale_price: '1250000', agents: ["רפי דה פיצ'וטו", 'צדוק']}));
D.soldOpen('d1');
const F = D.SOLD.f.d1;
ck(F.addr === 'ציזלינג 36' && F.price === (1250000).toLocaleString() && JSON.stringify(F.agents) === JSON.stringify(["רפי דה פיצ'וטו"]), JSON.stringify(F));
h = D.soldRow(D.ITEMS[0]);
ck(h.includes('כתובת מלאה') && h.includes('value="ציזלינג 36"') && h.includes('מאפיינים') && h.includes("soldCreate('d1')") && !h.includes("soldOpen('d1')"), h);
ck(h.includes("soldAg('d1',0,false)") && h.includes("soldAg('d1',1,true)") && !h.includes("פיצ'וטו',"), 'agent buttons by index');
D.soldAg('d1', 1, true); ck(JSON.stringify(D.SOLD.f.d1.agents) === JSON.stringify(["רפי דה פיצ'וטו", 'צדוק']), 'team');
D.soldAg('d1', 0, false); ck(JSON.stringify(D.SOLD.f.d1.agents) === JSON.stringify(['צדוק']), 'remove');
D.soldF('d1', 'rooms', '4'); ck(D.SOLD.f.d1.rooms === '4', 'typed');
// [05/11 אייל] גם צד המוכר שלנו → סרטון משולב
vm.runInContext(fn(djs, 'soldCreate') +
  "\nAGENTS = ['בן כהן', \"רפי דה פיצ'וטו\"]; var POSTS = []; function POST(u, b){ POSTS.push([u, b]); return {then: function(){ return {catch: function(){}}; }}; } function toast(){}", D);
h = D.soldRow(D.ITEMS[0]);
ck(h.includes('מי הביא את המוכר') && h.includes('<option value="בן כהן">') && h.includes('&#39;') && h.includes("soldS('d1',1,this.value)"), h);
D.soldS('d1', 0, 'בן כהן'); D.soldS('d1', 1, ' בנימין לוי ');
D.soldCreate('d1');
const B = D.POSTS[0][1].details;
ck(JSON.stringify(B.seller_agents) === JSON.stringify(['בן כהן', 'בנימין לוי']) && B.addr === 'ציזלינג 36' && D.POSTS[0][1].deal === 'd1', JSON.stringify(D.POSTS[0]));
delete D.SOLD.busy.d1;
D.SOLD.form.d1 = false;
ck(D.soldRow(Object.assign({}, it, {deal: false})) === '', 'open process → nothing');
ck(D.soldRow(Object.assign({}, it, {side1: 'מוכר', side2: ''})) === '', 'seller-only deal → nothing');
ck(D.soldRow(Object.assign({}, it, {side1: '', side2: ''})) !== '', 'no sides → shown');
D.SOLD.mode = 'publish';
D.SOLD.items['d:d1'] = {id: 's9', status: 'ready', token: 'T9'};
h = D.soldRow(it); ck(h.includes("soldPublish('s9','d1')") && h.includes('/v2/social/vid/T9.mp4') && !h.includes('מצב בדיקה'), h);
console.log('sold ui OK', n);
