// [CARD 26/11] כרטיס "שלי": תמונה, פעולות גלויות, "שיווק" ו"עוד פעולות" מתקפלים — על הקוד האמיתי של הדף
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const page = src.match(/V2_PROPS_HTML = r'''([\s\S]*?)'''/)[1];
const js = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
function cut(name){ const i = js.indexOf('function ' + name + '('); assert(i >= 0, name); let d = 0, j = js.indexOf('{', i);
  for (let k = j; k < js.length; k++){ if (js[k] === '{') d++; else if (js[k] === '}'){ d--; if (!d) return js.slice(i, k + 1); } } }
const code = ['propCard', 'mineCard', 'cardHint', 'cardTog', 'propDate', 'featChips', 'bpaBtn', 'shareRow', 'socWhen'].map(cut).join('\n');
const ctx = {MODE: 'mine', DEAL: '', MINE_MULTI: false, HOT: {}, HOT_BY: {}, SITE: {hidden: {}, fh: {}, can: true, on: true}, SHARE: {},
  VID: {items: {}}, VID_ST: {published: 'פורסם'}, bpAdd: function(){}, Date, String, Math,
  esc: s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'),
  fmtPrice: p => '₪' + p, socRow: () => '', vidRow: () => '<div>VIDROW</div>', soldRow: () => ''};
vm.createContext(ctx); vm.runInContext('var CARD_OPEN={};' + code, ctx);
const P = {id: 'abc', pkey: 'abc', own: true, address: 'רחוב הדוגמה 3', city: 'קרית אתא', type: 'קוטג', rooms: '7', price: '4,900,000',
  image: 'https://img.example.test/x.jpg', link: 'https://example.test/item/abc', feats: ['ממ"ד'], excl: false};
let h = ctx.propCard(P, 0);
['matchBuyers(0)', 'shareProp(0', 'bpAddProp(0)', 'reqPrice(0)', 'toggleHot(0)', 'toggleFH(0)', 'toggleSite(0)', 'propDetails(0)', 'reqRemove(0)',
 'VIDROW', 'img.example.test/x.jpg', 'example.test/item/abc', 'שיווק', 'עוד פעולות'].forEach(x => assert(h.includes(x), 'חסר: ' + x));
// עדכן מחיר גלוי (לפני החלקים המתקפלים); הורדת הנכס והפרטים בתוך "עוד פעולות"
assert(h.indexOf('reqPrice(0)') < h.indexOf('<details'), 'עדכן מחיר צריך להיות גלוי');
assert(h.indexOf('reqRemove(0)') > h.indexOf('class="px"'), 'הורדת הנכס בתוך עוד פעולות');
assert(h.indexOf('toggleHot(0)') > h.indexOf('class="pg"') && h.indexOf('toggleHot(0)') < h.indexOf('class="px"'), 'נכס חם בתוך שיווק');
assert(!/<details[^>]* open/.test(h), 'סגור כברירת מחדל');
// מצב פתוח נשמר בין ציורים
ctx.cardTog('abc:m', {open: true}); assert(/class="pg" open/.test(ctx.propCard(P, 0)));
// בלי תמונה — אין img; בטיפול אצל המזכירה — בלי עדכן מחיר ובלי הורדה
h = ctx.propCard(Object.assign({}, P, {image: '', pending: true}), 0);
assert(!h.includes('<img') && h.includes('doneListing(0)') && !h.includes('reqPrice(0)') && !h.includes('reqRemove(0)'));
// רמז השיווק
ctx.VID.items.abc = {last: {status: 'published', created_at: '2026-11-05T10:00:00Z'}}; ctx.HOT.abc = 1;
h = ctx.propCard(P, 0); assert(h.includes('נכס חם · סרטון: פורסם 05/11'));
// המשרד ושת"פ — בלי שינוי (אין הכרטיס החדש)
// המשרד שלנו — אותו עיצוב, 'פרטי הנכס' ו'למודעה' גלויים, בלי פעולות של הסוכן; ירידת מחיר מוצגת
ctx.MODE = 'office'; ctx.HOT = {};
h = ctx.propCard(Object.assign({}, P, {priceDropped: true, priceOld: '5,100,000'}), 0);
assert(h.includes('class="pth"') && !h.includes('prop mine'));
assert(h.indexOf('propDetails(0)') < h.indexOf('<details') && h.includes('example.test/item/abc'));
assert(h.indexOf('propDetails(0)') < h.indexOf('shareProp(0'), 'פרטי הנכס בשורה הראשונה');
['reqPrice(0)', 'reqRemove(0)', 'toggleHot(0)', 'toggleFH(0)'].forEach(z => assert(!h.includes(z), 'לא במשרד: ' + z));
assert(h.includes('toggleSite(0)') && h.includes('₪5,100,000') && h.includes('line-through') && h.includes('ירידת מחיר'));
ctx.SITE.can = false; ctx.vidRow = () => ''; h = ctx.propCard(P, 0); assert(!h.includes('<details'), 'סוכן רגיל במשרד — בלי חלקים מתקפלים');
ctx.SITE.can = true; ctx.vidRow = () => '<div>VIDROW</div>';
// שת"פ — בלי שינוי
ctx.MODE = 'shtaf'; h = ctx.propCard({street: 'רחוב', city: 'עיר', price: '1', office: 'משרד'}, 0); assert(!h.includes('class="pth"') && h.includes('class="top"'));
// הדגמה לצילום
if (process.argv[2]){ ctx.MODE = 'mine'; const css = page.match(/<style>([\s\S]*?)<\/style>/)[1];
  ctx.vidRow = () => '<div style="font-size:12px;color:#5B6472;font-weight:700;margin-top:8px">סרטון: פורסם 05/11 · 3/3</div><div style="margin-top:8px"><button style="width:100%;min-height:44px;border-radius:12px;font-size:13px;font-weight:800;font-family:inherit;background:#C29435;color:#231700;border:none">צור סרטון סטורי + ריל</button></div>';
  ctx.MODE = 'office'; const a = ctx.propCard(Object.assign({}, P, {agent: 'סוכן לדוגמה', priceDropped: true, priceOld: '5,100,000'}), 0); ctx.SITE.can = false;
  const b = ctx.propCard(Object.assign({}, P, {image: '', agent: 'סוכן לדוגמה'}), 0);
  fs.writeFileSync(process.argv[2], '<!doctype html><html dir="rtl" lang="he"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>' + css + '</style><body><div style="max-width:390px;margin:auto;padding:12px">' + a + b + '</div></body></html>'); }
console.log('ok mine card');
