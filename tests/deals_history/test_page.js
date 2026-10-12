// tests/deals_history/test_page.js — פונקציות הכרטיסים בדף /v2/history (על הקוד האמיתי)
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'deals_history.py'), 'utf8');
const a = src.indexOf('<script>', src.indexOf('V2_HISTORY_HTML = ')) + 8, b = src.indexOf('</script>', a);
const js = src.slice(a, b);
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };
global.document = {getElementById: () => null, querySelectorAll: () => []};
global.localStorage = {getItem: () => null, setItem: () => {}};
global.fetch = () => new Promise(() => {}); global.location = {href: ''};
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T={fmtP,agentCard,compCard,openCard,statsHtml,esc};');
ck(T.fmtP(1850000) === '₪1,850,000' && T.fmtP(null) === '' && T.fmtP(0) === '₪0', 'fmtP');
// היסטוריה (עד 2025): תאריך/כתובת/לקוח/סכום — בלי שולם/דווח/עמלה
const h = T.agentCard({date: '02/03/2025', address: 'הגפן 4, קרית מוצקין', side: 'מוכר', client: 'דנה', price: 1800000, agent: 'משה כהן'}, 'משה כהן');
ck(h.includes('דנה') && h.includes('₪1,800,000') && h.includes('02/03/2025') && !/שולם|דווח|עמלה/.test(h), h);
// 2026: עם עמלה/שולם/דווח
const d = T.agentCard({date: '01/06/2026', address: 'הרצל 1', side: 'מוכר', client: 'גל', price: 2000000,
  commission_net: 20000, paid: 20000, reported: '07/2026', agent: 'משה כהן'}, 'משה כהן');
ck(d.includes('עמלה ₪20,000') && d.includes('שולם ₪20,000') && d.includes('דווח 07/2026'), d);
const u = T.agentCard({date: '', address: 'x', side: '', client: '', price: null, commission_net: 5000, paid: null, reported: '', agent: 'משה כהן'}, 'משה כהן');
ck(u.includes('טרם שולם') && u.includes('לא דווח'), u);
// עסקה משותפת — מציג את השותף
ck(T.agentCard({date: '', address: 'x', client: '', price: 1, agent: 'משה כהן + דנה לוי'}, 'משה כהן').includes('משותפת'), 'joint label');
const cc = T.compCard({date: '01/02/2024', address: 'הגפן 4, קרית מוצקין', kind: 'מכירה', side: 'קונה', price: 1500000, agent: 'משה כהן'});
ck(cc.includes('₪1,500,000') && cc.includes('משה כהן') && !/עמלה|שולם/.test(cc), cc);
ck(T.esc('<b>') === '&lt;b&gt;', 'esc');
const oc = T.openCard({date: '10/05/2026', street: 'הגפן 9', city: 'קרית ביאליק', side: 'שוכר', agent: 'דנה לוי', client_name: 'יוסי',
  client_phone: '0529999999', commission_net: 5000, paid_amount: null, reported_date: null, collection_status: 'טרם שולם', invoice_no: '', receipt_no: '', year: 2026});
ck(oc.includes('0529999999') && oc.includes('טרם שולם') && !oc.includes('התחשבנות'), oc);
const oh = T.openCard({date: '10/05/2020', street: 'הגפן 9', city: 'קרית ביאליק', agent: 'דנה לוי', client_name: 'יוסי', client_phone: '', commission_net: 5000, paid_amount: null, reported_date: null, year: 2020});
ck(!/טרם שולם|לא דווח/.test(oh), 'history search card without payment chips');
const sh = T.statsHtml({year: 2025, total: {n: 2, commission: 23000}, prev: {n: 1, commission: 15000},
  byBranch: [{branch: 'motzkin', n: 1, commission: 18000}], byAgent: [{agent: 'משה כהן', n: 0.5, commission: 18000}], byMonth: [{month: '03', n: 1, commission: 18000}], years: [2025, 2024]});
ck(sh.includes('₪23,000') && sh.includes('מוצקין') && sh.includes('משה כהן') && sh.includes('2024') && sh.includes('0.5'), sh);
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T2={syncLine,reviewHtml};');
const sl = T2.syncLine({enabled: true, configured: true, alive: true, branches: {bialik: {ts: new Date(Date.now() - 120000).toISOString(), file: 'מעקב עסקאות 2026.xlsx', error: ''},
  motzkin: {ts: new Date().toISOString(), error: 'BadPassword: x'}}});
ck(sl.includes('ביאליק') && sl.includes('לפני 2 דק') && sl.includes('מוצקין') && sl.includes('#C24040'), sl);
ck(T2.syncLine({enabled: false}).includes('כבוי'), 'off');
const rv = T2.reviewHtml({missing: [{date: '01/02/2026', street: 'הרצל 2', city: 'קרית ים', agent: 'נדב רייזר', year: 2026}], unmapped: [{branch: 'bialik', name: 'חדש'}]});
ck(rv.includes('נעלמו מהאקסל') && rv.includes('הרצל 2') && rv.includes('ביאליק') && rv.includes('חדש'), rv);
ck(T2.reviewHtml({missing: [], unmapped: []}).includes('אין מה לבדוק'), 'empty');
// אייל 12/10: בורר סניף למנהלים; לסוכן — בלי
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T3={brBar,withQ,brQ,setED:function(v,b){ED=v;BRF=b;}};');
T3.setED(false, 'bialik');
ck(T3.brBar() === '' && T3.brQ() === '', 'agent: no branch bar, no param');
T3.setED(true, 'motzkin');
const bb = T3.brBar();
ck(bb.includes('כל הסניפים') && bb.includes('קרית ים') && /class="bc on"[^>]*>מוצקין/.test(bb), bb);
ck(T3.withQ('/a?kind=x', 'branch=motzkin') === '/a?kind=x&branch=motzkin' && T3.withQ('/a', '', 'q=1') === '/a?q=1' && T3.withQ('/a', '') === '/a', 'withQ');
ck(T3.brQ() === 'branch=motzkin', 'brQ');
console.log('OK', n, 'checks');
