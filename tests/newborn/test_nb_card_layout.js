// [CARD 26/11] כרטיס נכס נולד: חייג/וואטסאפ/למודעה, 4 כפתורי סטטוס גלויים, תיק + דף קונה ב"עוד פעולות"
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const i0 = src.indexOf('function nbCard(r, i){'); assert(i0 > 0);
let d = 0, end = -1; for (let k = src.indexOf('{', i0); k < src.length; k++){ if (src[k] === '{') d++; else if (src[k] === '}'){ d--; if (!d){ end = k + 1; break; } } }
const ctx = {MGR: true, ST_LABEL: {meeting: 'פגישה'}, bpAdd: function(){}, String, Math,
  esc: s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'), nbFmtPrice: p => '₪' + p};
vm.createContext(ctx); vm.runInContext(src.slice(i0, end), ctx);
const R = {key: 'id:abc', address: 'רחוב הדוגמה 5', city: 'קרית ביאליק', desc: 'דירה 4 חדרים', price: '2,050,000', priceDropped: true, priceOld: '2,150,000',
  owner: 'דוגמה', phone: '050-0000000', link: 'https://example.test/item/abc', ageDays: 0, date: '26/11/2026', contacted: ['סוכן א', 'סוכן ב'],
  stat: {status: 'meeting', date: '2026-11-27T10:30'}, unotes: [{name: 'סוכן', text: 'הערה'}], feats: ['מעלית']};
let h = ctx.nbCard(R, 3);
['nbDial(3)', 'waOwner(3)', 'example.test/item/abc', "stDate(3,'meeting')", "stDate(3,'followup')", 'stToggleNI(3)', 'noteSheet(3)',
 'kitFromNb(3)', 'bpAddNb(3)', 'כבר פנו', 'line-through', 'עוד פעולות', 'מעלית'].forEach(x => assert(h.includes(x), 'חסר: ' + x));
const det = h.indexOf('<details');
['stToggleNI(3)', 'noteSheet(3)', 'nbDial(3)', 'כבר פנו'].forEach(x => assert(h.indexOf(x) < det, 'צריך להיות גלוי: ' + x));
['kitFromNb(3)', 'bpAddNb(3)'].forEach(x => assert(h.indexOf(x) > det, 'בתוך עוד פעולות: ' + x));
assert(!/<details[^>]* open/.test(h));
vm.runInContext("nbCard._open['id:abc']=true", ctx); assert(/<details class="px" open/.test(ctx.nbCard(R, 3)), 'נשאר פתוח');
h = ctx.nbCard({address: 'א', city: 'ב', price: '1', ageDays: 40}, 0); assert(h.includes('kitFromNb(0)') && !h.includes('nbDial'));
if (process.argv[2]){ const kit = src.slice(src.lastIndexOf('<style>', i0), src.indexOf('</style>', src.lastIndexOf('<style>', i0)) + 8);
  fs.writeFileSync(process.argv[2], '<!doctype html><html dir="rtl" lang="he"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;600;700;800&display=swap" rel="stylesheet"><body style="margin:0;background:#F2EFE7;font-family:Heebo,sans-serif;color:#1E3A5F">' + kit + '<div class="nbk" style="max-width:390px;margin:auto;padding:12px;display:flex;flex-direction:column;gap:12px">' + ctx.nbCard(R, 3) + ctx.nbCard(Object.assign({}, R, {key: 'id:zz', priceDropped: false, contacted: [], stat: null, unotes: [], famexcl: true, famexclAgent: 'סוכן לדוגמה', ageDays: 40}), 1) + '</div></body></html>'); }
console.log('ok nb card');
