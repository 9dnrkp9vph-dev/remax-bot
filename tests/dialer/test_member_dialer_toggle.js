// tests/dialer/test_member_dialer_toggle.js — 04/11 (אייל): מתג 'חייגן' בכרטיס החבר בניהול, מתחת ל'השהיה'.
// node tests/dialer/test_member_dialer_toggle.js — על הקוד האמיתי של V2_ADMIN_HTML.
const fs = require('fs'), path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
const st = src.indexOf('V2_ADMIN_HTML = ');
const page = src.slice(st, src.indexOf("</html>'''", st));
const a = page.indexOf('<script>') + 8, js = page.slice(a, page.indexOf('</script>', a));
function fn(code, name){
  const i = code.indexOf('function ' + name + '(');
  if (i < 0) throw new Error('missing ' + name);
  let d = 0, j = code.indexOf('{', i);
  for (let k = j; k < code.length; k++){ if (code[k] === '{') d++; else if (code[k] === '}'){ d--; if (!d) return code.slice(i, k + 1); } }
}
let n = 0; const ck = (c, m) => { if (!c){ console.error('✗ ' + m); process.exit(1); } n++; console.log('  ✓ ' + m); };

function run(P, dlrOn){
  const posts = []; let sheet = '';
  const mk = on => { const s = new Set(on ? ['on'] : []); return {classList: {contains: c => s.has(c)}}; };
  const tgD = mk(dlrOn);
  const env = {
    el: id => id === 'teamList' ? {_list: [P]} : id === 'tgDlr' ? tgD
      : id === 'tgPlain' ? mk(P.nbPlain) : id === 'tgRent' ? mk(P.nbRent) : id === 'tgSusp' ? mk(false) : null,
    esc: s => String(s == null ? '' : s), seg: () => '', coordAgentsOf: () => [], PEOPLE: [P], COORDS: [],
    openSheet: h => { sheet = h; }, POST: (u, d) => { posts.push([u, d]); return Promise.resolve({ok: true, names: d.names}); },
    closeSheet: () => {}, toast: () => {}, boot: () => {}, _pickedNames: () => [],
  };
  const code = ['var SEL_ROLE = ' + JSON.stringify(P.role || 'agent') + ';',
    'var DLR = {names: ["דנה לוי"], coords: ["אוצר בן חמו"]};',
    fn(js, 'dlrKey'), fn(js, 'dlrHas'), fn(js, 'dlrIsAuto'), fn(js, 'openMember'), fn(js, 'saveMember'),
    'return {openMember, saveMember};'].join('\n');
  const A = new Function(...Object.keys(env), code)(...Object.values(env));
  A.openMember(0); A.saveMember(0);
  return {sheet, posts: posts.filter(p => p[0] === '/v2/api/dialer/users')};
}
const base = {phone: '501111111', vphone: '', nbRent: false, nbPlain: true};

let r = run(Object.assign({name: 'יוסי לוי', role: 'agent'}, base), false);
const iS = r.sheet.indexOf('id="tgSusp"'), iD = r.sheet.indexOf('id="tgDlr"');
ck(iD > iS && iS > 0, 'מתג חייגן מתחת להשהיה');
ck(r.sheet.indexOf('>חייגן<') >= 0, 'התווית: חייגן');
ck(r.sheet.slice(iD - 20, iD).indexOf(' on') < 0, 'סוכן שלא נבחר — כבוי');
ck(r.posts.length === 0, 'בלי שינוי — בלי שמירה');

r = run(Object.assign({name: 'יוסי לוי', role: 'agent'}, base), true);
ck(r.posts.length === 1 && JSON.stringify(r.posts[0][1].names) === JSON.stringify(['דנה לוי', 'יוסי לוי']), 'הדלקה — נוסף לרשימה');

r = run(Object.assign({name: 'דנה לוי', role: 'agent'}, base), true);
ck(/class="tg on" id="tgDlr"/.test(r.sheet), 'מי שנבחר — דלוק');
ck(r.posts.length === 0, 'דלוק ונשאר — בלי שמירה');
r = run(Object.assign({name: 'דנה לוי', role: 'agent'}, base), false);
ck(r.posts.length === 1 && r.posts[0][1].names.length === 0, 'כיבוי — הוסר מהרשימה');

r = run(Object.assign({name: 'נוי רבן', role: 'coordinator'}, base), false);
ck(/class="tg on" id="tgDlr"/.test(r.sheet) && r.sheet.indexOf('מתאמת · תמיד רואה') >= 0, 'מתאמת — דלוק ונעול');
ck(r.posts.length === 0, 'מתאמת — אין שמירה לרשימה');
r = run(Object.assign({name: 'אוצר בן חמו', role: 'manager'}, base), false);
ck(r.sheet.indexOf('מתאמת · תמיד רואה') >= 0 && r.posts.length === 0, 'מזוהה כמתאמת בשיוך — נעול');
console.log('ok', n);
