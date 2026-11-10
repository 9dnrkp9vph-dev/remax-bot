// CMA — פונקציות התצוגה במסך "ניתוח שוק" (/v2/cma). הרצה: node tests/cma/test_client.js
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'cma.py'), 'utf8');
const a = src.indexOf('// CMA-FN-START'), b = src.indexOf('// CMA-FN-END');
if (a < 0 || b < 0) { console.log('FAIL  markers not found'); process.exit(1); }
const code = src.slice(a, b);
const fns = new Function(code + '; return {cmaFmt, cmaRow, cmaResult};')();
let fails = 0;
function ck(c, m) { console.log((c ? 'ok  ' : 'FAIL') + '  ' + m); if (!c) fails++; }

ck(fns.cmaFmt(1620000) === '1,620,000', 'cmaFmt 1,620,000');
ck(fns.cmaFmt(null) === '', 'cmaFmt null → empty');
const ours = fns.cmaRow({street: 'מנחם בגין', house: 6, date: '2026-10-01', rooms: 3, sqm: 67, floor: '2',
  price: 1270000, ppm: 18955, ours: true, used: true, reason: ''});
ck(ours.indexOf('עסקה שלנו') >= 0 && ours.indexOf('מנחם בגין 6') >= 0, 'cmaRow ours chip + address');
const out = fns.cmaRow({street: 'מנחם בגין', house: 28, date: '2026-06-30', rooms: 5, sqm: 93, floor: '0',
  price: 2270000, ppm: 24409, ours: false, used: false, reason: 'חריג'});
ck(out.indexOf('חריג') >= 0 && out.indexOf('class="cr out"') >= 0, 'cmaRow dropped → reason + strike class');
const xss = fns.cmaRow({street: '<img src=x>', house: 1, date: '2026-01-01', rooms: 3, sqm: 60, floor: '',
  price: 1, ppm: 1, ours: false, used: true, reason: ''});
ck(xss.indexOf('<img') < 0, 'cmaRow escapes text');
const ex = fns.cmaRow({street: 'מנחם בגין', house: 36, date: '2026-08-31', rooms: 5, sqm: 123, floor: '3',
  price: 2070000, ppm: 16829, ours: false, used: false, reason: '', extra: true});
ck(ex.indexOf('class="cr ex"') >= 0 && ex.indexOf(' out') < 0, 'cmaRow extra → muted, not struck');
const few = fns.cmaResult({ok: true, cma: null, reason: 'few'});
ck(few.indexOf('אין מספיק עסקאות דומות') >= 0, 'cmaResult few → empty state');
const full = fns.cmaResult({ok: true, cma: {title: 'x', level: 'street', street_count: 13, since_year: 2023,
  ppm_median: 16800, competing: 2, range: [1620000, 1910000], ppm_range: [15151, 17892], basis: 'sqm', n_used: 7,
  subject: {street: 'מנחם בגין', rooms: 5}, comps: [], listings: [], data_as_of: '2026-11-06'}});
ck(full.indexOf('1,620,000') >= 0 && full.indexOf('1,910,000') >= 0, 'cmaResult shows range');
ck(full.indexOf('13') >= 0 && full.indexOf('16,800') >= 0, 'cmaResult shows teaser numbers');
ck(full.indexOf('06/11/2026') >= 0, 'cmaResult data date');
console.log('\n' + fails + ' failures');
process.exit(fails ? 1 : 0);
