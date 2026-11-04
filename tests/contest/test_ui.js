// tests/contest/test_ui.js — הכרטיס המשותף ומסך התחרות (על הקוד האמיתי ב-contest.py וב-effie_v2.py)
const fs = require('fs'), path = require('path'), vm = require('vm'), cp = require('child_process');
const ROOT = path.join(__dirname, '..', '..');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };

const py = (expr) => cp.execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, ' + JSON.stringify(ROOT) +
  '); import contest; sys.stdout.write(' + expr + ')'], {encoding: 'utf8'});
const KIT = py('contest.V2_CONTEST_KIT'), PAGE = py('contest.V2_CONTEST_HTML');
function scripts(html) {
  const out = []; let i = 0;
  for (;;) {
    const a = html.indexOf('<script>', i); if (a < 0) break;
    const b = html.indexOf('</script>', a); out.push(html.slice(a + 8, b)); i = b + 9;
  }
  return out;
}
const kitJs = scripts(KIT).join('\n');
[...scripts(PAGE), kitJs].forEach((js, i) => { new vm.Script(js); ck(true, 'syntax ' + i); });
ck(KIT.includes('<style>') && kitJs.length > 100, 'kit has style + script');
ck(PAGE.includes('<!--CONTEST_KIT-->'), 'page kit placeholder');

const v2 = fs.readFileSync(path.join(ROOT, 'effie_v2.py'), 'utf8');
ck(/@app\.route\("\/v2\/contest", methods=\["GET"\]\)/.test(v2), '/v2/contest route in effie_v2');
ck(/V2_CONTEST_HTML\.replace\("<!--CONTEST_KIT-->", _contest\.V2_CONTEST_KIT, 1\)/.test(v2), 'kit injected');
ck(/href="\/v2\/contest"/.test(v2), 'home side menu link');
ck(!/route\("\/v2\/contest"/.test(fs.readFileSync(path.join(ROOT, 'contest.py'), 'utf8')), 'no page route in contest.py');

const ctx = {localStorage: {_s: {}, getItem(k) { return this._s[k] || null; }, setItem(k, v) { this._s[k] = String(v); }},
             location: {href: ''}, Intl, Date, Math, JSON, String, Number, isNaN, encodeURIComponent, console};
vm.createContext(ctx);
vm.runInContext(kitJs, ctx);
const K = ctx;

function J(over) {
  const j = {ok: true, mode: 'live', can_edit: false, adjustments: [],
    me: {group: 0, kind: 'row', label: 'נדב רייזר'},
    board: {id: '2026-11', name: 'תחרות נובמבר', start: '2026-11-01', end: '2026-11-30', days_left: 26,
      pts: {gius: 30, meeting: 5}, leader: 0,
      groups: [
        {name: "קבוצה א'", total: 395, rows: [
          {label: 'רויטל גל', members: ['רויטל גל'], meetings: 4, gius: 3, adj: 0, points: 110, pd: 2, rank: 1},
          {label: 'נדב רייזר', members: ['נדב רייזר'], meetings: 3, gius: 2, adj: 0, points: 75, pd: 1, rank: 2},
          {label: 'אירנה אוברוב', members: ['אירנה אוברוב'], meetings: 6, gius: 1, adj: 0, points: 60, pd: 3, rank: 3}],
         coords: [{name: 'נוי רבן', meetings: 7, adj: 0, points: 35}]},
        {name: "קבוצה ב'", total: 340, rows: [
          {label: 'אור צוקרמן', members: ['אור צוקרמן'], meetings: 2, gius: 3, adj: 5, points: 105, pd: 1, rank: 1},
          {label: 'אלעד לוי', members: ['אלעד לוי'], meetings: 0, gius: 0, adj: 0, points: 0, pd: 0, rank: 2}],
         coords: []}]}};
  return Object.assign(j, over || {});
}

// הכרטיס
let h = K.contestCardHtml(J(), {story: true});
ck(h.includes('הקבוצה שלך') && h.includes('מובילה'), 'mine + leading');
ck(h.includes('קבוצה א&#39; מובילה'), 'leader title (escaped)');
ck(h.includes('395') && h.includes('340'), 'both totals');
ck(h.includes('פער של') && h.includes('55 נקודות') && h.includes('2 גיוסים בערך'), 'gap line: ' + h.match(/פער[^<]*<b>[^<]*<\/b>[^<]*/));
ck(h.includes('הניקוד שלך') && h.includes('מקום 2'), 'me card');
ck(h.includes('/v2/contest'), 'story link to full table');
const tie = J(); tie.board.leader = null; tie.board.groups[1].total = 395;
h = K.contestCardHtml(tie, {});
ck(h.includes('תיקו') && !h.includes('פער של'), 'tie: title, no gap line');
ck(!K.contestCardHtml(J({me: null}), {}).includes('הניקוד שלך'), 'me=null → no me card');
ck(!K.contestCardHtml(J(), {tv: true}).includes('הניקוד שלך'), 'tv → no me card');
ck(K.contestGapGius(55, 30) === 2, 'gap gius 55/30');
ck(K.contestGapGius(10, 0) === 0, 'gap gius no pts');

// השורה המעודדת
ck(!K.contestNudge(J()).includes('עקפת'), '[POWER-DAY] בלי השוואה לחודש הקודם');
const j1 = J({me: {group: 0, kind: 'row', label: 'רויטל גל'}}); j1.board.groups[0].rows[0].gius = 2;
ck(K.contestNudge(j1).includes('מוביל'), 'rank 1 → מוביל');
const j3 = J({me: {group: 0, kind: 'row', label: 'אירנה אוברוב'}});
ck(K.contestNudge(j3) === 'עוד 15 נקודות למקום הבא', 'else → עוד: ' + K.contestNudge(j3));

// null → —
const jn = J(); jn.board.groups[0].rows[1].gius = null; jn.board.groups[0].rows[1].partial = true;
h = K.contestCardHtml(jn, {});
ck(h.includes('—') && !h.includes('null') && !h.includes('undefined'), 'gius null → —');
ck(!K.contestNudge(jn).includes('עקפת'), 'null gius → no עקפת');

// מתאמת: נקודות ופגישות בלבד
h = K.contestCardHtml(J({me: {group: 0, kind: 'coord', label: 'נוי רבן'}}), {});
ck(h.includes('הניקוד שלך') && h.includes('35') && h.includes('פגישות') && !h.includes('P.D.') && !h.includes('גיוסים</span>'), 'coord me card');

// כרטיס המנצחת
const w = J({mode: 'winner'});
h = K.contestWinnerHtml(w, {});
ck(h.includes('קבוצה א&#39; ניצחה'), 'winner group');
ck(h.includes('רויטל גל') && h.includes('אור צוקרמן') && h.includes('נדב רייזר') && !h.includes('אירנה אוברוב'), 'top 3 across groups');
ck(!h.includes('נוי רבן'), 'winner: rows only');
ck(K.contestCardHtml(w, {}) === h, 'card in winner mode → winner card');

// מטמון
K.contestCachePut('T1', J());
ck(K.contestCacheGet('T1') && K.contestCacheGet('T1').board.id === '2026-11', 'cache same token');
ck(K.contestCacheGet('T2') === null, 'cache other token');
ck(K.contestCacheGet('T1', '1999-01-01') === null, 'cache other day');

// טבלת המסך
let t = K.contestTableHtml(J(), 0, {});
ck(t.includes('tr class="me') || /class="[^"]*\bme\b/.test(t), 'me row highlighted');
ck((t.match(/<tr/g) || []).length === 4, 'header + 3 rows');
t = K.contestTableHtml(J(), 1, {});
ck(t.includes('cAdj'), 'adj mark on row with adj');
ck(!t.includes('תיקון ידני'), 'no edit buttons without can_edit');
t = K.contestTableHtml(J({can_edit: true}), 1, {});
ck(t.includes('תיקון'), 'edit buttons with can_edit');
ck(K.contestCoordsHtml(J(), 0).includes('נוי רבן'), 'coords table');
ck(K.contestCoordsHtml(J(), 1) === '', 'no coords → empty');
const adjs = [{id: 'a', group: 1, kind: 'row', label: 'אור צוקרמן', pts: 5, reason: 'בונוס'},
              {id: 'b', group: 0, kind: 'row', label: 'אור צוקרמן', pts: 9, reason: 'x'}];
ck(K.contestAdjFor(adjs, 1, 'row', 'אור צוקרמן').length === 1, 'adj filter by group/kind/label');
ck(K.contestRules({gius: 30, meeting: 5}).includes('= 30') && K.contestRules({gius: 30, meeting: 5}).includes('= 5'), 'rules line');
ck(K.contestRules({gius: 30, meeting: 5}).includes('Power Day') && !K.contestRules({gius: 30, meeting: 5}).includes('P.D.'), 'rules: Power Day, no P.D.');
ck(K.contestRange('2026-11-01', '2026-11-30') === '1–30 בנובמבר', 'range: ' + K.contestRange('2026-11-01', '2026-11-30'));
ck(K.contestSplit(' א , ב,, ג ').join('|') === 'א|ב|ג', 'split');

// תווית עם גרש לא שוברת את ה-onclick
const ja = J({can_edit: true}); ja.board.groups[1].rows[0].label = "רפי דה פיצ'וטו";
t = K.contestTableHtml(ja, 1, {});
const oc = t.match(/onclick="adjOpen\(([^"]*)\)"/);
ck(oc && oc[1].includes('%27') && !/פיצ'/.test(oc[1]), 'apostrophe encoded in onclick: ' + (oc && oc[1]));
ck(decodeURIComponent(oc[1].split(",'")[2].replace(/'$/, '')) === "רפי דה פיצ'וטו", 'round-trips');

// [FIX2] לוח חלקי — 'לא זמין' במקום סכומי קבוצות ומובילה
const jp = J(); jp.board.partial = true; jp.board.leader = null;
h = K.contestCardHtml(jp, {story: true});
ck(h.includes('לא זמין') && !h.includes('מובילה') && !h.includes('395') && !h.includes('פער של') && !h.includes('ck-team lead'), 'partial story card: ' + h.slice(0, 200));
h = K.contestCardHtml(jp, {tv: true});
ck(h.includes('לא זמין') && !h.includes('מובילה') && !h.includes('395') && !h.includes('ck-col lead'), 'partial tv card');
h = K.contestWinnerHtml(Object.assign({}, jp, {mode: 'winner'}), {});
ck(h.includes('לא זמין') && !h.includes('ניצחה') && !h.includes('395'), 'partial winner card');
ck(!K.contestCardHtml(J(), {}).includes('לא זמין'), 'full board → no לא זמין');
ck(K.contestTotal(jp.board, jp.board.groups[0]) === 'לא זמין' && K.contestTotal(J().board, J().board.groups[0]) === '395', 'contestTotal');
// מסך: mini-vs ושורת המתאמות על לוח חלקי + הודעת שמות שלא נמצאו לעורכים
const PJS = scripts(PAGE).join('\n');
function pageWorld(j) {
  const els = {};
  const pc = {localStorage: {getItem: () => 'T', setItem() {}}, location: {href: '', replace() {}}, Intl, Date, Math, JSON, String, Number,
    isNaN, encodeURIComponent, decodeURIComponent, console, setTimeout() { return 1; }, clearTimeout() {},
    fetch: () => new Promise(() => {}), Promise,
    document: {getElementById: id => els[id] || (els[id] = {innerHTML: '', style: {}, textContent: ''})}};
  vm.createContext(pc); vm.runInContext(kitJs + '\n' + PJS, pc);
  pc.CJ = j; vm.runInContext('CJ = this.CJ; SEL = null; render();', pc);
  return els.app.innerHTML;
}
let ph = pageWorld(jp);
ck(ph.includes('לא זמין') && !/class="lead"/.test(ph) && !ph.includes('395'), 'page mini-vs partial');
ph = pageWorld(J({can_edit: true, unmatched: ['נויה', 'פלוני']}));
ck(ph.includes('שמות שלא נמצאו באפי') && ph.includes('נויה') && ph.includes('פלוני'), 'unmatched notice for editors');
ck(!pageWorld(J({can_edit: false, unmatched: ['נויה']})).includes('שמות שלא נמצאו'), 'no notice for non-editors');
ck(!pageWorld(J({can_edit: true, unmatched: []})).includes('שמות שלא נמצאו'), 'no notice when empty');

// ── [POWER-DAY 04/11] ──
const jpw = J(); jpw.board.power_today = true; jpw.board.power_days = ['2026-11-05']; jpw.board.power_mult = 2;
jpw.board.groups[0].rows[1].power_pts = 70; jpw.board.groups[0].coords[0].power_pts = 20;
h = K.contestCardHtml(jpw, {story: true});
ck(h.includes('היום POWER DAY') && h.includes('גיוס 60') && h.includes('פגישה 10'), 'story banner on power day');
ck(!K.contestCardHtml(J(), {story: true}).includes('POWER DAY'), 'no banner on normal day');
h = K.contestCardHtml(jpw, {tv: true});
ck(h.includes('היום POWER DAY') && h.includes('ck-pow'), 'tv card banner');
ck(K.contestPowerStrip(jpw).includes('ck-pow-strip') && K.contestPowerStrip(J()) === '', 'tv strip only on power day');
ck(K.contestNudge(jpw).includes('60') && K.contestNudge(jpw).includes('10'), 'nudge on power day: ' + K.contestNudge(jpw));
t = K.contestTableHtml(jpw, 0, {});
ck(t.includes('>Power Day<') && t.includes('>70<'), 'table power column');
ck(!K.contestTableHtml(J(), 0, {}).includes('Power Day'), 'no column before any power day');
ck(K.contestCoordsHtml(jpw, 0).includes('>20<'), 'coords power column');
const jpast = J(); jpast.board.power_days = ['2026-11-02']; jpast.board.power_today = false;
ck(!K.contestCardHtml(jpast, {story: true}).includes('POWER DAY') && K.contestTableHtml(jpast, 0, {}).includes('Power Day'), 'past day: column yes, banner no');
h = K.contestCardHtml(jpw, {});
ck(h.includes('ב-Power Day'), 'me chip power');
ck(!K.contestCardHtml(J(), {}).includes('ב-Power Day') && !K.contestCardHtml(J(), {}).includes('P.D.'), 'no P.D. chip');
ck(!K.contestWinnerHtml(Object.assign({}, jpw, {mode: 'winner'}), {}).includes('POWER DAY'), 'winner: no banner');
console.log(n + ' passed');
