// tests/contest/test_story.js — התחרות ככרטיס ראשון בסטורי של הבית (על הקוד האמיתי ב-effie_v2.py וב-contest.py)
const fs = require('fs'), path = require('path'), vm = require('vm'), cp = require('child_process');
const ROOT = path.join(__dirname, '..', '..');
const src = fs.readFileSync(path.join(ROOT, 'effie_v2.py'), 'utf8');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };

function block(name, q) {
  const a = src.indexOf('\n' + name + ' = r' + q);
  if (a < 0) throw new Error('missing ' + name);
  const s = src.indexOf(q, a) + 3, e = src.indexOf(q, s);
  return src.slice(s, e);
}
function scripts(html) {
  const out = []; let i = 0;
  for (;;) {
    const a = html.indexOf('<script>', i); if (a < 0) break;
    const b = html.indexOf('</script>', a); out.push(html.slice(a + 8, b)); i = b + 9;
  }
  return out;
}
const HOME = block('V2_HOME_HTML', "'''");
const GKIT = scripts(block('V2_GOALS_KIT', '"""')).join('\n');
const CKIT = scripts(cp.execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, ' + JSON.stringify(ROOT) +
  '); import contest; sys.stdout.write(contest.V2_CONTEST_KIT)'], {encoding: 'utf8'})).join('\n');

// הזרקה
ck(HOME.includes('<!--CONTEST_KIT-->'), 'home has CONTEST_KIT placeholder');
ck(HOME.indexOf('<!--CONTEST_KIT-->') < HOME.indexOf('var TOK = null'), 'kit placeholder before home script');
ck(/V2_HOME_HTML\.replace\("<!--GOALS_KIT-->", V2_GOALS_KIT, 1\)\.replace\("<!--CONTEST_KIT-->", _ck, 1\)/.test(src), 'home route injects contest kit');
ck(/import contest as _contest[\s\S]{0,200}_ck = ''|_ck = ''[\s\S]{0,200}import contest as _contest/.test(src), 'guarded import with empty fallback');

// הסטורי — מחלצים את הפונקציות האמיתיות ומריצים בהקשר מזויף
const H = scripts(HOME).join('\n');
function fn(name) {
  const a = H.indexOf('function ' + name + '(');
  if (a < 0) throw new Error('missing fn ' + name);
  let i = H.indexOf('{', a), d = 0;
  for (; i < H.length; i++) { if (H[i] === '{') d++; else if (H[i] === '}') { d--; if (!d) break; } }
  return H.slice(a, i + 1);
}
function line(re) { const m = re.exec(H); if (!m) throw new Error('missing ' + re); return m[0]; }

function mkEl() { return {textContent: '', innerHTML: '', style: {}, scrollTop: 0, children: [],
  classList: {_c: {}, toggle(k, on) { this._c[k] = !!on; }, contains(k) { return !!this._c[k]; }},
  querySelectorAll() { return []; }}; }
function world(CJ, hot) {
  const els = {};
  const ctx = {
    localStorage: {_s: {}, getItem(k) { return this._s[k] || null; }, setItem(k, v) { this._s[k] = String(v); }},
    location: {href: ''}, Intl, Date, Math, JSON, String, Number, isNaN, isFinite, parseFloat, encodeURIComponent, console,
    el(id) { return els[id] || (els[id] = mkEl()); },
    setBars() {}, setTimeout() { return 1; }, clearTimeout() {},
    STORY: {DUR: 9000, open: false, i: 0}, B: {hotProps: hot, _loaded: true}, M: {name: 'נדב רייזר'},
    HDAYS: ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ש'], HMON: Array(12).fill('נובמבר'),
    esc: s => String(s == null ? '' : s), firstName: s => String(s || '').split(' ')[0], greetWord: () => 'בוקר טוב',
    GJ: {ok: true, view: 'agent', me: {counts: {}, targets: {}}}, CJ: CJ, CS: null, CO: 0, TOK: 'T1',
  };
  vm.createContext(ctx);
  vm.runInContext(GKIT + '\n' + CKIT, ctx);
  vm.runInContext([fn('openStory'), fn('total'), fn('durFor'), fn('nextCard'), fn('go'), fn('renderCard'), fn('closeStory'), fn('storyLog'), fn('contestLoad')].join('\n'), ctx);
  ctx.seenKey = () => 'x'; ctx.todayStr = () => 'd'; ctx.fetch = () => {}; ctx.goalsCardHtml = () => '<div class="gk">GOALS</div>';
  return ctx;
}
const BOARD = {id: '2026-11', name: 'תחרות נובמבר', start: '2026-11-01', end: '2026-11-30', days_left: 26,
  pts: {gius: 30, meeting: 5}, leader: 0,
  groups: [{name: "קבוצה א'", total: 395, rows: [{label: 'נדב רייזר', gius: 2, meetings: 4, pd: 1, points: 80, rank: 1}], coords: []},
           {name: "קבוצה ב'", total: 340, rows: [{label: 'רויטל גל', gius: 1, meetings: 3, pd: 2, points: 45, rank: 1}], coords: []}]};
const LIVE = {ok: true, mode: 'live', board: BOARD, me: {group: 0, kind: 'row', label: 'נדב רייזר'}, can_edit: false};

// בלי תחרות — בדיוק כמו היום
let w = world(null, [{title: 'א'}, {title: 'ב'}]);
w.openStory(true);
ck(w.CO === 0, 'no contest → CO 0');
ck(w.total() === 4, 'no contest total 4: ' + w.total());
ck(w.el('storyBody').innerHTML.includes('GOALS'), 'no contest card 0 = goals');
ck(w.el('storyTitle').textContent === 'היעדים שלי להיום', 'goals title');
ck(w.durFor(0) === 20000 && w.durFor(1) === 9000, 'durations unchanged');
w.go(1); ck(w.el('storyBody').innerHTML.includes('המשרד מתחילת השנה'), 'card 1 = summary');
w.go(2); ck(w.el('storyBody').innerHTML.includes('>א<'), 'card 2 = hot #1');
// תחרות שאין לה מצב (mode null) — כמו בלי תחרות
w = world({ok: true, mode: null, board: null}, []);
w.openStory(false); ck(w.CO === 0 && w.total() === 2 && w.el('storyBody').innerHTML.includes('GOALS'), 'mode null → unchanged');

// תחרות חיה
w = world(LIVE, [{title: 'א'}, {title: 'ב'}]);
w.openStory(true);
ck(w.CO === 1, 'live → CO 1');
ck(w.total() === 5, 'live total 5: ' + w.total());
let h0 = w.el('storyBody').innerHTML;
ck(h0.includes('class="ck story"') && h0.includes('מובילה'), 'card 0 = contest card');
ck(h0.includes('href="/v2/contest"') && h0.includes('לטבלה המלאה'), 'full table link');
ck(/onclick="nextCard\(\)">המשך לסטורי</.test(h0), 'continue button');
ck(w.el('storyTitle').textContent === 'תחרות', 'contest title');
ck(w.durFor(0) === 15000 && w.durFor(1) === 20000 && w.durFor(2) === 9000, 'durations shifted: ' + [w.durFor(0), w.durFor(1), w.durFor(2)]);
w.nextCard(); ck(w.STORY.i === 1 && w.el('storyBody').innerHTML.includes('GOALS'), 'card 1 = goals');
ck(w.el('storyTitle').textContent === 'היעדים שלי להיום', 'goals title at 1');
w.go(2); ck(w.el('storyBody').innerHTML.includes('המשרד מתחילת השנה'), 'card 2 = summary');
w.go(3); ck(w.el('storyBody').innerHTML.includes('>א<'), 'card 3 = hot #1');
w.go(4); ck(w.el('storyBody').innerHTML.includes('>ב<') && w.el('storyBody').innerHTML.includes('בוא נתחיל את היום'), 'card 4 = last hot');
// נתונים שמגיעים אחרי הפתיחה לא מזיזים את הסטורי
w = world(undefined, []); w.openStory(true); w.CJ = LIVE;
ck(w.CO === 0 && w.total() === 2, 'late data: no jump while open');
// הקבוצה המנצחת
w = world(Object.assign({}, LIVE, {mode: 'winner'}), []);
w.openStory(true);
h0 = w.el('storyBody').innerHTML;
ck(h0.includes('ניצחה') && h0.includes('התחרות הסתיימה'), 'winner card');
ck(w.el('storyTitle').textContent === 'הקבוצה המנצחת', 'winner title');

// טעינה: בדפוס goalsLoad
ck(/var CJ;/.test(H) && /CJ = \(typeof contestCacheGet === 'function' && contestCacheGet\(TOK\)\) \|\| undefined;/.test(H), 'CJ from cache before open');
ck(/function contestLoad\(tries\)\{[\s\S]{0,700}\/v2\/api\/contest[\s\S]{0,700}contestLoad\(\(tries \|\| 0\) \+ 1\)/.test(H), 'contestLoad with retries');
ck(/\ncontestLoad\(0\);/.test(H), 'contestLoad started');
// אינדקסים שהוזזו
ck(/STORY\.i === CO\) renderCard\(CO\)/.test(H), 'goals re-render at CO');
ck(/STORY\.i === CO \+ 1\) renderCard\(CO \+ 1\)/.test(H), 'brief re-render at CO+1');
ck(/STORY\.i === CO \+ 3\) renderCard\(CO \+ 3\)/.test(H), 'nb re-render at CO+3');
ck(/if \(STORY\.open && STORY\.i > CO\) renderCard\(STORY\.i\);/.test(H), 'loadData skips contest+goals cards');
// תחביר
scripts(HOME).forEach((js, i) => { new vm.Script(js); ck(true, 'syntax ' + i); });

// [FIX3] התמונה בפתיחה (CS) — CJ שמתעדכן אחרי הפתיחה לא משנה את הכרטיס שעל המסך
w = world(LIVE, []); w.openStory(true);
w.CJ = Object.assign({}, LIVE, {board: Object.assign({}, BOARD, {leader: 1})});
w.renderCard(0);
ck(w.el('storyBody').innerHTML.includes('קבוצה א&#39; מובילה'), 'card 0 rendered from snapshot CS');
ck(/CS = CO \? CJ : null/.test(fn('openStory')), 'openStory snapshots CS');
ck(!/contest(Card|Winner)Html\(CJ/.test(fn('renderCard')) && !/CJ\.mode/.test(fn('renderCard')), 'renderCard uses CS, not CJ');
// [FIX3] סטורי שנפתח לפני שהתחרות נטענה (בוקר קר) — כשהיא מגיעה, עוברים לכרטיס התחרות
function lateWorld(i, ans) {
  const w = world(undefined, [{title: 'א'}]);
  let res; w.GET = () => new Promise(r => { res = r; });
  w.openStory(true); if (i) w.go(i);
  w.contestLoad(0); res(ans);
  return w;
}
const pending = [];
let lw = lateWorld(0, LIVE);
pending.push(Promise.resolve().then(() => new Promise(r => setImmediate(r))).then(() => {
  ck(lw.CO === 1 && lw.STORY.i === 0 && lw.total() === 4, 'late upgrade: CO 1, total 4: ' + lw.CO + '/' + lw.total());
  ck(lw.el('storyBody').innerHTML.includes('class="ck story"') && lw.el('storyTitle').textContent === 'תחרות', 'late upgrade renders contest card');
  ck(lw.CS && lw.CS.mode === 'live', 'late upgrade snapshots CS');
}));
let lw2 = lateWorld(1, LIVE);
pending.push(new Promise(r => setImmediate(r)).then(() => {
  ck(lw2.CO === 0 && lw2.STORY.i === 1, 'no upgrade after user advanced');
}));
let lw3 = lateWorld(0, {ok: true, mode: null, board: null});
pending.push(new Promise(r => setImmediate(r)).then(() => {
  ck(lw3.CO === 0 && lw3.el('storyBody').innerHTML.includes('GOALS'), 'no upgrade when no contest');
}));
Promise.all(pending).then(() => console.log(n + ' passed')).catch(e => { console.error(e); process.exit(1); });
