// tests/goals/test_tv.js — כרטיס יעדים בטלוויזיה (על הקוד האמיתי ב-effie_v2.py)
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };
const a = src.indexOf('\nV2_TV_HTML = r\'\'\''), s0 = src.indexOf("'''", a) + 3, e0 = src.indexOf("'''", s0);
const html = src.slice(s0, e0);
const js = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));
new vm.Script(js); ck(true, 'syntax');

const nodes = {}; const stub = () => ({style: {}, classList: {add() {}, remove() {}}, querySelectorAll: () => [], set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; }});
let fetchImpl = () => new Promise(() => {});
const ctx = {
  document: {getElementById: id => nodes[id] || (nodes[id] = stub()), addEventListener() {}},
  location: {search: '?k=abc', replace() {}, reload() {}}, localStorage: {getItem: () => null},
  window: {innerWidth: 1920}, requestAnimationFrame() {}, setTimeout() { return 1; }, clearTimeout() {}, setInterval() {},
  fetch: (...a) => fetchImpl(...a), Intl, Date, Math, JSON, String, Number, isNaN, encodeURIComponent, decodeURIComponent, console, Promise,
};
vm.createContext(ctx); vm.runInContext(js, ctx);
const run = c => vm.runInContext(c, ctx);

run("B = {hotProps:[1,2,3].map(function(i){return {title:'x'+i}})}; G = null;");
let pl = run('playlist()'); ck(pl[0].t === 'sum', 'no goals when G null');
run("G = {counts:{meetings:1,buyers:3,past_clients:null,reviews:0}, targets:{meetings:4,buyers:6,past_clients:10,reviews:4}};");
pl = run('playlist()');
ck(pl[0].t === 'goals' && pl[1].t === 'sum' && pl[2].t === 'hot' && pl.length === 5, 'goals, sum, props');
ck(run('durFor(playlist(), playlist()[0])') === run('durFor(playlist(), playlist()[1])'), 'goals duration == sum');
ck(run('durFor(playlist(), playlist()[0])') > run('durFor(playlist(), playlist()[2])'), 'goals longer than hot');
run("B = {hotProps:[]}"); pl = run('playlist()'); ck(pl.length === 2 && pl[0].t === 'goals', 'no hot props');

const h = run("goalsTvHtml(G)");
ck(h.includes('היעדים של המשרד להיום') && h.includes('/ 4') && h.includes('—'), 'totals + dash for missing');
ck(h.includes('פגישות מנכס נולד') && h.includes('המלצות'), 'goal titles');
const h2 = run("goalsTvHtml({counts:{meetings:4,buyers:0,past_clients:0,reviews:0}, targets:{meetings:4,buyers:1,past_clients:1,reviews:1}, name:'דוד כהן', rows:[{name:'דוד כהן'}]})");
ck(h2.includes('הושלם') && !h2.includes('דוד'), 'completed label, no agent names');

// כשל בשליפה → אין פריט יעדים; הצלחה → יש
fetchImpl = () => Promise.reject(new Error('x'));
run("G = {counts:{},targets:{}}; loadGoals()");
setTimeout(() => {
  ck(run('G') === null, 'fetch failure clears goals');
  fetchImpl = () => Promise.resolve({json: () => ({ok: true, total: {counts: {meetings: 1}, targets: {meetings: 2}}})});
  run('loadGoals()');
  setTimeout(() => { ck(run('G && G.targets.meetings') === 2, 'success sets goals');
    ck(run('GET.toString()').includes('encodeURIComponent(KEY)'), 'kiosk key appended');
    console.log('OK ' + n); }, 20);
}, 20);
