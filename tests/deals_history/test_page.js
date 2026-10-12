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
// אייל 12/10: מכירה/קנייה מול שכירות — לכולם
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T4={kindBar,kQ,statsHtml,setK:function(v,e){KF=v;ED=e;}};');
T4.setK('rent', false);
const kb = T4.kindBar();
ck(kb.includes('מכירה וקנייה') && /class="bc on"[^>]*>שכירות/.test(kb) && T4.kQ() === 'deal=rent', kb);
const sh2 = T4.statsHtml({year: 2026, deal: 'rent', total: {n: 2, commission: 7000}, prev: {n: 0, commission: 0},
  bySide: {sale: {n: 3, commission: 44000}, rent: {n: 2, commission: 7000}}, byBranch: [], byAgent: [], byMonth: []});
ck(sh2.includes('שכירויות 2026') && sh2.includes('מכירה וקנייה · ₪44,000') && sh2.includes('שכירות · ₪7,000'), sh2);
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T5={agentsHtml};');
const ah = T5.agentsHtml({since: 2026, agents: [{name: 'חי חיים אלבז', n: 12, n_cur: 3, last: '01/09/2026', file_names: ['חי אלבז']}, {name: 'אלעד לוי', n: 0, n_cur: 0, last: '', file_names: []}],
  unlinked: [{name: 'רוני', n: 4, last: '01/01/2019', branches: ['motzkin']}]});
ck(ah.includes('חי חיים אלבז') && ah.includes('בקבצים: חי אלבז') && ah.includes('>אין<') && ah.includes('רוני') && ah.includes('מוצקין'), ah);
// אייל 12/10: וואטסאפ ללקוח עם הודעה מובנית — רק כשיש טלפון
eval(js.replace(/\(function\(\)\{\s*try\{ TOK[\s\S]*$/, '') + ';global.T6={waPhone,remindText,waBtn,agentCard,openCard,setOff:function(o){OFFICE=o;}};');
T6.setOff('רימקס פמילי');
ck(T6.waPhone('052-1234567') === '972521234567' && T6.waPhone('+972 52 123 4567') === '972521234567' && T6.waPhone('') === '' && T6.waPhone('123') === '', 'waPhone');
const msg = T6.remindText({client: 'דנה לוי', side: 'קונה', address: 'נעמי שמר 2, ביאליק', date: '01/02/2024'}, 'משה כהן');
ck(msg.startsWith('שלום דנה, כאן משה כהן מרימקס פמילי.') && msg.includes('בקניית הנכס בנעמי שמר 2, ביאליק ב-2024') && msg.includes('אשמח לעזור') && msg.trim().endsWith('משה כהן'), msg);
ck(T6.remindText({client: '', side: 'משכיר', address: 'הגפן 4', date: ''}, 'משה').startsWith('שלום, כאן משה מרימקס פמילי. ליוויתי אתכם בהשכרת הנכס בהגפן 4,'), T6.remindText({client: '', side: 'משכיר', address: 'הגפן 4', date: ''}, 'משה'));
ck(T6.waBtn({phone: ''}, 'משה') === '' && T6.waBtn({phone: '0521234567', client: 'דנה', side: 'מוכר', address: 'x', date: ''}, 'משה').includes('https://wa.me/972521234567?text='), 'btn only with phone');
const ac = T6.agentCard({date: '01/02/2024', address: 'נעמי שמר 2', side: 'קונה', client: 'דנה', price: 1, agent: 'משה כהן', phone: '0521234567'}, 'משה כהן');
ck(ac.includes('wa.me/972521234567') && ac.includes('תזכורת ללקוח'), ac);
const oc2 = T6.openCard({date: '10/05/2026', street: 'הגפן 9', city: 'ביאליק', side: 'שוכר', agent: 'דנה לוי + משה כהן', client_name: 'יוסי', client_phone: '0529999999', year: 2026});
ck(oc2.includes('wa.me/972529999999') && decodeURIComponent(oc2.match(/text=([^"]+)/)[1]).includes('כאן דנה לוי'), oc2);
console.log('OK', n, 'checks');
