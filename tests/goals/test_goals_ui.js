// tests/goals/test_goals_ui.js — מסך היעדים, כרטיס ראשון בסטורי, כרטיס בבית (על הקוד האמיתי ב-effie_v2.py)
const fs = require('fs'), path = require('path'), vm = require('vm');
const src = fs.readFileSync(path.join(__dirname, '..', '..', 'effie_v2.py'), 'utf8');
let n = 0; const ck = (c, m) => { if (!c) throw new Error('FAIL: ' + m); n++; };

function block(name, q) {                 // גוף מחרוזת פייתון ברמת המודול: NAME = r'''…'''
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
const KIT = block('V2_GOALS_KIT', '"""');
const kitJs = scripts(KIT).join('\n');
const HOME = block('V2_HOME_HTML', "'''");
const PAGE = block('V2_GOALS_HTML', "'''");

// תחביר: כל ה-<script> של הבית, של מסך היעדים ושל הערכה
[...scripts(HOME), ...scripts(PAGE), kitJs].forEach((js, i) => { new vm.Script(js); ck(true, 'syntax ' + i); });
ck(HOME.includes('<!--GOALS_KIT-->') && PAGE.includes('<!--GOALS_KIT-->'), 'kit placeholder in both pages');
ck(/@app\.route\("\/v2\/goals", methods=\["GET"\]\)/.test(src), '/v2/goals route');
ck(/V2_HOME_HTML\.replace\("<!--GOALS_KIT-->", V2_GOALS_KIT/.test(src), 'home kit injected');
ck(/href="\/v2\/goals"/.test(HOME), 'home side menu link');

// הערכה בהקשר מבודד
const ctx = {localStorage: {_s: {}, getItem(k) { return this._s[k] || null; }, setItem(k, v) { this._s[k] = String(v); }},
             location: {href: ''}, Intl, Date, Math, JSON, String, Number, isNaN, encodeURIComponent, console};
vm.createContext(ctx);
vm.runInContext(kitJs, ctx);
const K = ctx;

const agentJ = {ok: true, view: 'agent', day: '2026-10-28', can_edit: false,
  me: {counts: {meetings: 1, buyers: 3, bpage: 1, past_clients: 0, reviews: null,
                followups: {due: 4, done: 2}, missed: 3},
       targets: {meetings: 2, buyers: 3, past_clients: 5, reviews: 2}}};
const h = K.goalsCardHtml(agentJ, {});
ck((h.match(/class="gBar"/g) || []).length === 5, '4 goal bars + followups bar: ' + (h.match(/class="gBar"/g) || []).length);
ck(h.includes('פגישות מנכס נולד') && h.includes('1<i>/2</i>'), 'meetings 1/2');
ck(h.includes('קונים חדשים') && h.includes('3<i>/3</i>'), 'buyers 3/3');
ck(h.includes('דף קונה נשלח ל-1 מהם'), 'bpage line');
ck(h.includes('0<i>/5</i>'), 'past clients 0/5');
ck(h.includes('—<i>/2</i>'), 'null reviews → —');
ck(h.includes('פולו-אפ להיום') && h.includes('2<i>/4</i>'), 'followups 2/4');
ck(h.includes('שיחות שלא חזרת אליהן') && />3<\/div>/.test(h), 'missed 3');
ck(h.includes("goalsGo('/v2/calls')"), 'calls button when missed>0');
// היעד שהושלם (קונים) — נייבי + הושלם
const bBlock = h.slice(h.indexOf('קונים חדשים') - 600, h.indexOf('קונים חדשים') + 900);
ck(/class="gk-g done"/.test(bBlock) && bBlock.includes('הושלם'), 'completed buyers → done + הושלם');
ck(K.GOALS_NAVY === '#1E3A5F' && KIT.includes('.gk-g.done .gBar div{background:#1E3A5F}'), 'done bar navy');
// כפתור לקוחות עבר ירוק
ck(/<button class="gBtn green" onclick="goalsGo\('\/v2\/history'\)">להיסטוריית העסקאות<\/button>/.test(h), 'green history button');
ck(KIT.includes('.gBtn.green{background:#157A43'), 'green #157A43');
['/v2/newborn', '/v2/buyers', '/v2/history', '/v2/reviews', '/v2/meets'].forEach(u => ck(h.includes("goalsGo('" + u + "')"), 'button ' + u));
ck(h.includes('2 נכסים בפייסבוק ובאינסטגרם') && h.includes('יופעל בקרוב'), 'soon row');
// טבעת: 1 מתוך 4 (רק קונים הושלם; המלצות null לא נספר)
ck(K.goalsDone(agentJ.me) === 1 && h.includes('1 מתוך 4 יעדים הושלמו') && h.includes('25%'), 'ring 1/4');
ck(K.goalsDone({counts: {meetings: 0, buyers: 0, past_clients: 0, reviews: 0}, targets: {meetings: 0, buyers: 0, past_clients: 0, reviews: 0}}) === 4, 'target 0 counts complete');
// אין אימוג'ים
const emo = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/u;
ck(!emo.test(h) && !emo.test(KIT) && !emo.test(PAGE), 'no emoji');
ck(!/#C24040/i.test(KIT) && !/#C24040/i.test(PAGE), 'no red');
// הכל חסר → —
const hn = K.goalsCardHtml(null, {});
ck(!/\b0<i>/.test(hn) && hn.includes('—<i>/—</i>'), 'null data → — never 0');

// מתאמת/מנהל: סכום + פירוט לפי סוכן
const teamJ = {ok: true, view: 'team', can_edit: false, me: null,
  total: {counts: {meetings: 3, buyers: 2, bpage: 0, past_clients: 4, reviews: 1, followups: {due: 0, done: 0}, missed: 0},
          targets: {meetings: 4, buyers: 6, past_clients: 10, reviews: 4}, partial: true},
  agents: [{name: 'דנה כהן', counts: {meetings: 2, buyers: 1, bpage: 0, past_clients: 4, reviews: 1, followups: {due: 0, done: 0}, missed: 0},
            targets: {meetings: 2, buyers: 3, past_clients: 5, reviews: 2}, seen_today: true},
           {name: 'רועי לוי', counts: {meetings: 1, buyers: 1, bpage: 0, past_clients: 0, reviews: 0, followups: null, missed: 0},
            targets: {meetings: 2, buyers: 3, past_clients: 5, reviews: 2}, seen_today: false}]};
const ht = K.goalsCardHtml(teamJ, {story: true});
ck(ht.includes('פירוט לפי סוכן') && ht.includes("goalsGo('/v2/goals')"), 'team card link to /v2/goals');
ck(ht.includes('3<i>/4</i>') && ht.includes('אין שיחות פתוחות'), 'team totals');
ck(ht.includes('חלק מהנתונים'), 'partial note');
const ha = K.goalsAgentsHtml(teamJ, false);
ck(ha.includes('דנה כהן') && ha.includes('רועי לוי') && ha.includes('לא נכנס/ה היום') && !ha.includes('לא נכנס היום'), 'agents list + not seen (gender-neutral)');
ck((ha.match(/class="gBar"/g) || []).length === 8, 'bar per goal per agent');
ck(!ha.includes('עריכת יעד') && !ha.includes('יעד ברירת מחדל'), 'no edit for non-manager');
const hm = K.goalsAgentsHtml(Object.assign({}, teamJ, {view: 'office', can_edit: true}), true);
ck(hm.includes('עריכת יעד') && hm.includes('יעד ברירת מחדל'), 'manager edit buttons');
ck(K.goalsCardHtml(agentJ, {story: true}).indexOf('פירוט לפי סוכן') < 0, 'agent story: no breakdown link');

// צ'יפים בבית
const c = K.goalsChipsHtml(agentJ);
ck(c.includes('נכס נולד 1/2') && c.includes('קונים 3/3') && c.includes('לקוחות עבר 0/5') && c.includes('המלצות —/2'), 'chips');
ck(/class="gChip ok">קונים 3\/3/.test(c), 'completed chip ok');
ck(c.includes('פולו-אפ 2/4') && c.includes('שיחות 3'), 'status chips');
ck(K.goalsMiniTitle(agentJ) === 'היעדים שלי להיום · 1/4', 'mini title: ' + K.goalsMiniTitle(agentJ));
ck(K.goalsMiniTitle(teamJ).indexOf('הצוות') >= 0, 'team mini title');

// הנכס החם שלי
const e0 = K.hotMineHtml(null);
ck(e0.includes('עוד לא סימנת נכס חם') && e0.includes('לסימון בנכסים שלי') && e0.includes('/v2/props?mine=1'), 'empty state');
ck(e0.includes('gk-eic'), 'gold circle icon');
const e1 = K.hotMineHtml({title: 'אהוד מנור 13, קרית ביאליק', details: "4 חד'", price: '2290000'});
ck(e1.includes('אהוד מנור 13') && e1.includes('2,290,000') && e1.includes('החלף נכס חם'), 'hot card');
ck(K.hotMineHtml({title: '<b>x'}).indexOf('<b>x') < 0, 'escaped');

// מטמון: אותו טוקן ואותו יום בלבד
K.goalsCachePut('T1', agentJ);
ck(K.goalsCacheGet('T1', '2026-10-28') && !K.goalsCacheGet('T2', '2026-10-28') && !K.goalsCacheGet('T1', '2026-10-29'), 'cache keyed by token+day');

// הסטורי: יעדים + סיכום + נכסים חמים
const tot = /function total\(\)\{[^\n]*\}/.exec(HOME)[0];
const sx = {B: {hotProps: [1, 2, 3]}}; vm.createContext(sx); vm.runInContext(tot, sx);
ck(sx.total() === 5, 'story total with 3 hot = 5');
sx.B = {}; ck(sx.total() === 2, 'story total no hot = 2');
ck(/goalsCardHtml\(GJ/.test(HOME), 'story renders goals card');
ck(/\(B\.hotProps \|\| \[\]\)\[i - 2\]/.test(HOME), 'hot props shifted by 2');
ck(/storyLog/.test(HOME) && /seen: STORY\.max \|\| 1, total: total\(\)/.test(HOME), 'story log unchanged');
// goalsGo סוגר את הסטורי ומנווט
let closed = 0; ctx.STORY = {open: true}; ctx.closeStory = () => { closed++; ctx.STORY.open = false; };
K.goalsGo('/v2/buyers'); ck(closed === 1 && ctx.location.href === '/v2/buyers', 'goalsGo closes + navigates');
// מסך היעדים: שדות 16px מספריים
ck(/inputmode="numeric"/.test(PAGE) && /font-size:16px/.test(PAGE), 'numeric 16px inputs');
// fix 1: יחיד כשנשאר 1, רבים מעל 1
const one = {ok: true, view: 'agent', me: {counts: {meetings: 1, buyers: 2, past_clients: 4, reviews: 1, followups: null, missed: null},
  targets: {meetings: 2, buyers: 3, past_clients: 5, reviews: 2}}};
const ho = K.goalsCardHtml(one, {});
ck(ho.includes('נשארו: פגישה אחת · קונה אחד · לקוח עבר אחד · המלצה אחת'), 'singular remaining');
ck(!/\b1 (פגישות|קונים|לקוחות|המלצות)/.test(ho), 'no "1 + plural"');
const two = {ok: true, view: 'agent', me: {counts: {meetings: 0, buyers: 0, past_clients: 0, reviews: 0}, targets: {meetings: 2, buyers: 3, past_clients: 5, reviews: 2}}};
ck(K.goalsCardHtml(two, {}).includes('נשארו: 2 פגישות · 3 קונים · 5 לקוחות עבר · 2 המלצות'), 'plural remaining');
// fix 2: רינדור מחדש רק אחרי מצב 'טוען'
ck(/var wasLoading = \(GJ === undefined\);[\s\S]{0,300}if \(wasLoading && STORY\.open && STORY\.i === 0\) renderCard\(0\);/.test(HOME), 'goalsLoad re-renders only from loading');
ck((HOME.match(/STORY\.i === 0\) renderCard\(0\)/g) || []).length === 2, 'no unconditional re-render');
// fix final: צעדי loadData לא מציירים מחדש את כרטיס היעדים (כרטיס 0)
ck(/if \(STORY\.open && STORY\.i !== 0\) renderCard\(STORY\.i\);/.test(HOME), 'loadData step skips card 0');
ck(!/if \(STORY\.open\) renderCard\(STORY\.i\)/.test(HOME), 'no unconditional renderCard(STORY.i)');
// fix 3: בלי פסיק כשאין שם
ck(/greet: firstName\(M\.name\) \? greetWord\(\) \+ ', ' \+ firstName\(M\.name\) : greetWord\(\)/.test(HOME), 'story greet no trailing comma');
const hg = K.goalsCardHtml(agentJ, {greet: ''});
ck(!hg.includes('class="gr"'), 'empty greet omitted');
console.log('ok', n);
