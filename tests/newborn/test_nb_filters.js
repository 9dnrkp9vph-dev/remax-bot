// tests/newborn/test_nb_filters.js — תגיות במסך נכס נולד (06/11): ירידות מחיר (ברירת מחדל) · חדשים מהיום · הכל · ירד מפרסום
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const st = src.indexOf('V2_NB_HTML = ');
const page = src.slice(st, src.indexOf("</html>'''", st));
const js = page.slice(page.indexOf('<script>') + 8, page.indexOf('</script>', page.indexOf('<script>')));
function fn(name){
  const i = js.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing function ' + name);
  let j = js.indexOf('{', i), d = 0;
  for (; j < js.length; j++){ if (js[j] === '{') d++; else if (js[j] === '}' && --d === 0) break; }
  return js.slice(i, j + 1);
}
let n = 0; const ck = (c, m) => { if (!c) throw new Error(m); n++; };

ck(page.indexOf('id="nbf"') > 0 && page.indexOf('id="nbf"') < page.indexOf('id="ages"'), 'chip row above months');
const els = {};
const el = id => (els[id] = els[id] || {id, style: {}, textContent: '', innerHTML: '', value: '', children: []});
const env = {el, esc: s => String(s == null ? '' : s), nbCard: r => '<card ' + r.key + '>', window: {scrollTo(){}}};
const code = ['var ROWS = [], BUCKETS = [7,0,0,0,0,0,0], TOTAL = 0, AGE = -1, MEETS = [], DEAL = "", RENT_OK = false, NB_FULL = true;',
  js.match(/var BUCKET_RANGES = [^\n]*/)[0], 'var NB_SHOWN = 40;',
  js.match(/var NBF = [^\n]*/)[0], js.match(/var NBF_LIST = [^\n]*/)[0], js.match(/var NBF_EMPTY = [^\n]*/)[0],
  fn('nbfKeys'), fn('nbfLabel'), fn('setNbF'), fn('setAge'), fn('render'),
  'return {render, setNbF, setAge, set: r => { ROWS = r; }, st: () => ({NBF, AGE})};'].join('\n');
const T = new Function(...Object.keys(env), code)(...Object.values(env));
const cards = () => (els.list.innerHTML.match(/<card ([^>]+)>/g) || []).map(s => s.slice(6, -1));

T.set([
  {key: 'n1', ageDays: 0},
  {key: 'd_old', ageDays: 40, priceDropped: true, priceDropAt: 100},
  {key: 'd_new', ageDays: 200, priceDropped: true, priceDropAt: 900},
  {key: 'r1', ageDays: 10},
  {key: 'g1', ageDays: 5, delisted: '01/11', priceDropped: true, priceDropAt: 999},
]);
els.q = {value: ''};
ck(T.st().NBF === 'drops', 'default = price drops');
T.render();
ck(JSON.stringify(cards()) === '["d_new","d_old"]', 'drops: newest drop first, any month, no delisted: ' + cards());
const chips = els.nbf.innerHTML;
ck(chips.indexOf('ירידות מחיר') < chips.indexOf('חדשים מהיום') && chips.indexOf('חדשים מהיום') < chips.indexOf('>הכל') &&
   chips.indexOf('>הכל') < chips.indexOf('ירד מפרסום'), 'chip order');
ck(/ירידות מחיר<b>2<\/b>/.test(chips) && /חדשים מהיום<b>1<\/b>/.test(chips) && /הכל<b>4<\/b>/.test(chips) && /ירד מפרסום<b>1<\/b>/.test(chips), 'counts: ' + chips);
T.setNbF('new'); ck(JSON.stringify(cards()) === '["n1"]', 'new today');
T.setNbF('all'); ck(JSON.stringify(cards()) === '["n1","d_old","d_new","r1"]', 'all hides delisted');
T.setNbF('gone'); ck(JSON.stringify(cards()) === '["g1"]', 'delisted only');
T.setAge(0); ck(T.st().NBF === 'all' && T.st().AGE === 0, 'month → all');
ck(JSON.stringify(cards()) === '["n1","r1"]', 'month 1 within all: ' + cards());
T.setNbF('drops'); ck(T.st().AGE === -1, 'chip clears month');
T.set([{key: 'n1', ageDays: 0, address: 'הרצל 5'}, {key: 'g1', ageDays: 5, delisted: '01/11', address: 'הרצל 9'}]);
els.q.value = 'הרצל'; T.render();
ck(JSON.stringify(cards()) === '["n1","g1"]', 'search ignores the chip: ' + cards());
els.q.value = '';
T.set([{key: 'r1', ageDays: 10}]); T.setNbF('drops');
ck(els.list.innerHTML.indexOf('אין ירידות מחיר') >= 0 && els.list.innerHTML.indexOf("setNbF('all')") >= 0, 'empty state with CTA');
console.log('ok', n);
