// tests/contest/test_tv.js — התחרות ככרטיס ראשון בטלוויזיה (על הקוד האמיתי ב-effie_v2.py וב-contest.py)
const fs = require('fs'), path = require('path'), vm = require('vm'), cp = require('child_process');
const ROOT = path.join(__dirname, '..', '..');
const src = fs.readFileSync(path.join(ROOT, 'effie_v2.py'), 'utf8');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };
const a = src.indexOf('\nV2_TV_HTML = r\'\'\''), s0 = src.indexOf("'''", a) + 3, e0 = src.indexOf("'''", s0);
let html = src.slice(s0, e0);
const kit = cp.execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, ' + JSON.stringify(ROOT) +
  '); import contest; sys.stdout.write(contest.V2_CONTEST_KIT)'], {encoding: 'utf8'});
const kjs = kit.slice(kit.indexOf('<script>') + 8, kit.lastIndexOf('</script>'));
ck(html.includes('<!--CONTEST_STYLE-->') && html.includes('/*CONTEST_KIT_JS*/'), 'placeholders in TV html');
ck(src.includes('_kit[:_kit.index("<script>")]') && src.includes('"/*CONTEST_KIT_JS*/"'), 'route injects kit');
const inject = h => h.replace('/*CONTEST_KIT_JS*/', kjs);
const mk = (h, nodes, fetchImpl) => {
  const js = h.slice(h.indexOf('<script>') + 8, h.lastIndexOf('</script>')); new vm.Script(js);
  const stub = () => ({style: {}, cls: {}, classList: {add(x) { this.o.cls[x] = 1; }, remove(x) { delete this.o.cls[x]; }}, querySelectorAll: () => [], set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; }});
  const ctx = {
    document: {getElementById: id => nodes[id] || (nodes[id] = (o => (o.classList.o = o, o))(stub())), addEventListener() {}},
    location: {search: '?k=abc', replace() {}, reload() {}}, localStorage: {getItem: () => null},
    window: {innerWidth: 1920}, requestAnimationFrame() {}, setTimeout() { return 1; }, clearTimeout() {}, setInterval() {},
    fetch: (...x) => fetchImpl(...x), Intl, Date, Math, JSON, String, Number, isNaN, encodeURIComponent, decodeURIComponent, console, Promise,
  };
  vm.createContext(ctx); vm.runInContext(js, ctx); return c => vm.runInContext(c, ctx);
};
const rows = nm => [9, 8, 7, 6, 5, 4].map((p, i) => ({label: nm + i, points: p}));
const J = {ok: true, mode: 'live', board: {name: 'תחרות נובמבר', days_left: 12, leader: 0, pts: {gius: 10, meeting: 3},
  groups: [{name: 'הכחולים', total: 39, rows: rows('כ')}, {name: 'הזהובים', total: 21, rows: rows('ז')}]}};
let nodes = {}, fetchImpl = () => new Promise(() => {});
const run = mk(inject(html), nodes, (...x) => fetchImpl(...x));

run("B = {hotProps:[1,2,3].map(function(i){return {title:'x'+i}})}; G = {counts:{},targets:{}}; C = null;");
let base = run('JSON.stringify(playlist())');
ck(run('playlist()[0].t') === 'goals', 'no contest -> as today');
run('C = ' + JSON.stringify(Object.assign({}, J, {mode: null})));
ck(run('JSON.stringify(playlist())') === base, 'mode null -> unchanged');
run('C = ' + JSON.stringify(J));
let pl = run('playlist()');
ck(pl[0].t === 'contest' && pl[1].t === 'goals' && pl[2].t === 'sum' && pl.length === 6, 'contest, goals, sum, props');
ck(run('durFor(playlist(), playlist()[0])') === run('durFor(playlist(), playlist()[1])'), 'contest duration == goals');
ck(run('blockInfo(playlist(), 0).len') === 1 && run('blockInfo(playlist(), 1).len') === 1 && run('blockInfo(playlist(), 3).pos') === 1, 'contest is a block boundary');
run('render(0)');
const h = nodes.card._h;
ck(h.includes('class="ck tv"') && h.includes('הכחולים מובילה') && h.includes('הזהובים'), 'tv card rendered');
ck(h.includes('כ0') && h.includes('כ4') && !h.includes('כ5') && h.includes('ז4') && !h.includes('ז5'), 'top 5 names per group');
ck((h.match(/class="ck-col( lead)?"/g) || []).length === 2 && h.includes('39') && h.includes('21'), 'two columns with totals');
ck(nodes.card.cls.wide === 1, 'wide card'); run('render(1)'); ck(!nodes.card.cls.wide, 'goals not wide');
run('C = ' + JSON.stringify(Object.assign({}, J, {mode: 'winner'}))); run('render(0)');
ck(nodes.card._h.includes('ניצחה') && nodes.card._h.includes('התחרות הסתיימה'), 'winner variant');

// בלי הערכה (הזרקה כשלה) — contestCardHtml לא קיים → אין פריט תחרות
const run2 = mk(html, {}, () => new Promise(() => {}));
run2("B = {hotProps:[]}; G = null; C = " + JSON.stringify(J));
ck(run2('playlist()[0].t') === 'sum' && run2('playlist().length') === 1, 'kit missing -> TV unchanged');

// טעינה: מפתח הקיוסק, הצלחה/כשל/ללא תחרות
let urls = [];
fetchImpl = u => { urls.push(u); return Promise.resolve({json: () => J}); };
run('C = null; loadContest()');
setTimeout(() => {
  ck(run('C && C.mode') === 'live', 'success sets contest');
  ck(urls.some(u => u.startsWith('/v2/api/contest') && u.includes('k=abc')), 'kiosk key on contest url');
  fetchImpl = () => Promise.resolve({json: () => ({ok: true, mode: null, board: null})});
  run('loadContest()');
  setTimeout(() => { ck(run('C') === null, 'no contest clears');
    fetchImpl = () => Promise.reject(new Error('x')); run('C = ' + JSON.stringify(J) + '; loadContest()');
    setTimeout(() => { ck(run('C') === null, 'failure clears'); console.log('OK ' + n); }, 20); }, 20);
}, 20);
