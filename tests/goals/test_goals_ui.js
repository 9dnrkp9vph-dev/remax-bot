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

// [GOALS4] מתחילת השבוע ומתחילת החודש: שני פסים לכל יעד, סימון קצב, סטטוס
const PACE = {week: 0.5, month: 0.5, week_from: '2026-10-25', month_from: '2026-10-01', month_to: '2026-10-31'};
const T0 = {listings: 1, meetings: 1, nb_wa: 2, buyers: 1, past_clients: 1, reviews: 1};
const agentJ = {ok: true, view: 'agent', day: '2026-10-28', can_edit: false,
  me: {counts: {listings: 0, meetings: 1, nb_wa: 0, buyers: 3, bpage: 1, past_clients: 0, reviews: null,
                followups: {due: 4, done: 2}, missed: 3},
       targets: T0, pace: PACE,
       week: {counts: {listings: 0, meetings: 3, nb_wa: 1, buyers: 6, buyers_sign: 2, bpage: 1, past_clients: 1, reviews: null},
              targets: {listings: 2, meetings: 4, nb_wa: 12, buyers: 6, past_clients: 6, reviews: 6}},
       month: {counts: {listings: 3, meetings: 11, nb_wa: 20, buyers: 20, past_clients: 4, reviews: 1},
               targets: {listings: 9, meetings: 14, nb_wa: 40, buyers: 20, past_clients: 12, reviews: 12}}}};
const h = K.goalsCardHtml(agentJ, {});
ck((h.match(/class="gk-rw/g) || []).length === 12, 'week + month row per goal: ' + (h.match(/class="gk-rw/g) || []).length);
ck(h.includes('השבוע') && h.includes('החודש'), 'both periods');
ck(h.includes('3<i> / 4</i>') && h.includes('11<i> / 14</i>'), 'meetings week 3/4, month 11/14');
ck(h.includes('—<i> / 6</i>'), 'null reviews → —');
// סטטוס: קונים 6/6 הושג; פגישות 3 ≥ קצב 2 → בקצב; פניות 1 < קצב 6 → חסרים 5 לקצב
ck(/gk-st ok">הושג/.test(h), 'done status');
ck(h.includes('gk-st pace">בקצב'), 'on pace');
ck(h.includes('חסרים 5 לקצב'), 'behind pace by 5');
ck((h.match(/class="tk"/g) || []).length >= 8, 'pace ticks on unfinished bars');
ck(h.includes('הכי קרוב ליעד השבוע'), 'motivating push line');
ck(h.includes('2 מהחתמה'), 'buyers from signing (week)');
ck(h.includes('היום: <b>1</b>'), 'today count shown');
ck(h.includes('נשארו 2.5 ימי עבודה') || h.includes('נשארו 3 ימי עבודה'), 'workdays left');
ck(h.includes('פולו-אפ להיום') && h.includes('2<i>/4</i>'), 'followups 2/4 (today)');
ck(h.includes('שיחות שלא חזרת אליהן') && />3<\/div>/.test(h), 'missed 3');
ck(/<button class="gBtn green" onclick="goalsGo\('\/v2\/history'\)">להיסטוריית העסקאות<\/button>/.test(h), 'green history button');
ck(KIT.includes('.gBtn.green{background:#157A43'), 'green #157A43');
['/v2/sign?type=owner', '/v2/newborn', '/v2/buyers', '/v2/history', '/v2/reviews', '/v2/meets', '/v2/calls'].forEach(u => ck(h.includes("goalsGo('" + u + "')"), 'button ' + u));
ck(K.gDoneP(K.goalsData(agentJ).week) === 1 && K.gDoneP(K.goalsData(agentJ).month) === 1, 'done counts week/month');
ck(K.GOALS_NAVY === '#1E3A5F' && KIT.includes('.gk-rw.ok .gBar div{background:#1E3A5F}'), 'done bar navy');
const emo = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/u;
ck(!emo.test(h) && !emo.test(KIT) && !emo.test(PAGE), 'no emoji');
ck(!/#C24040/i.test(KIT) && !/#C24040/i.test(PAGE), 'no red');
// כל היעדים הושגו → שורת כל הכבוד
const allJ = JSON.parse(JSON.stringify(agentJ)); allJ.me.week.counts = Object.assign({}, allJ.me.week.targets);
ck(K.goalsCardHtml(allJ, {}).includes('כל יעדי השבוע הושגו'), 'all week goals done');
// עותק ישן בלי week (מטמון מגרסה קודמת) → תצוגת 'היום', בלי ליפול
const oldJ = {ok: true, view: 'agent', me: {counts: {meetings: 1, buyers: 3}, targets: T0}};
const hold = K.goalsCardHtml(oldJ, {});
ck(hold.includes('יעדים הושלמו היום') && (hold.match(/class="gk-rw/g) || []).length === 6, 'fallback without week');
const hn = K.goalsCardHtml(null, {});
ck(!/\b0<i>/.test(hn) && hn.includes('—<i> / —</i>'), 'null data → — never 0');

// מתאמת/מנהל: סכום + פירוט לפי סוכן
const teamJ = {ok: true, view: 'team', can_edit: false, me: null,
  total: {counts: {meetings: 3, buyers: 2, bpage: 0, past_clients: 4, reviews: 1, followups: {due: 0, done: 0}, missed: 0},
          targets: T0, partial: true, pace: PACE, agents: 2,
          week: {counts: {listings: 1, meetings: 3, nb_wa: 9, buyers: 4, past_clients: 4, reviews: 1}, targets: {listings: 4, meetings: 8, nb_wa: 24, buyers: 12, past_clients: 12, reviews: 12}},
          month: {counts: {listings: 5, meetings: 20}, targets: {listings: 18, meetings: 28}}},
  agents: [{name: 'דנה כהן', counts: {followups: {due: 0, done: 0}, missed: 0}, targets: T0, seen_today: true,
            week: {counts: {meetings: 2, buyers: 3}, targets: {meetings: 4, buyers: 6}}, month: {counts: {meetings: 9}, targets: {meetings: 14}}},
           {name: 'רועי לוי', counts: {followups: null, missed: 0}, targets: T0, seen_today: false, active: false,
            week: {counts: {meetings: 1}, targets: {meetings: 4}}, month: {counts: {meetings: 2}, targets: {meetings: 14}}}]};
const ht = K.goalsCardHtml(teamJ, {story: true});
ck(ht.includes('פירוט לפי סוכן') && ht.includes("goalsGo('/v2/goals')"), 'team card link to /v2/goals');
ck(ht.includes('3<i> / 8</i>') && ht.includes('אין שיחות פתוחות'), 'team week totals');
ck(ht.includes('חלק מהנתונים') && ht.includes('2 סוכנים פעילים'), 'partial note + team count');
const ha = K.goalsAgentsHtml(teamJ, false);
ck(ha.includes('דנה כהן') && ha.includes('רועי לוי') && ha.includes('לא נכנס/ה ב-10 ימים') && ha.includes('השבוע 0/6 · החודש 0/6'), 'agents list');
ck(ha.includes('חודש 9/14') && ha.includes('2/4'), 'agent week + month numbers');
ck((ha.match(/class="gBar"/g) || []).length === 12, 'bar per goal per agent');
ck(!ha.includes('עריכת יעד') && !ha.includes('יעד המשרד לחודש'), 'no edit for non-manager');
const hm = K.goalsAgentsHtml(Object.assign({}, teamJ, {view: 'office', can_edit: true}), true);
ck(hm.includes('עריכת יעד') && hm.includes('יעד המשרד לחודש') && !hm.includes('יעד ברירת מחדל'), 'manager edit buttons');
const hown = K.goalsAgentsHtml({view: 'office', can_edit: true, agents: [Object.assign({}, teamJ.agents[0], {own: ['meetings']})]}, true);
ck(hown.includes('יעד אישי לחודש'), 'own target marked');
const hoff = K.goalsCardHtml({view: 'office', total: Object.assign({}, teamJ.total, {office_month: {meetings: 160}, share_agents: 25})}, {});
ck(hoff.includes('מתחלק בין 25 סוכנים פעילים'), 'office card explains split');
ck(K.goalsCardHtml(agentJ, {}).includes('החלק שלך ביעד המשרד'), 'agent card: share of office goal');
ck(K.goalsCardHtml(agentJ, {story: true}).indexOf('פירוט לפי סוכן') < 0, 'agent story: no breakdown link');

// צ'יפים בבית — לפי השבוע
const c = K.goalsChipsHtml(agentJ);
ck(c.includes('נכס נולד 3/4') && c.includes('קונים 6/6') && c.includes('לקוחות עבר 1/6') && c.includes('המלצות —/6'), 'week chips: ' + c);
ck(/class="gChip ok">קונים 6\/6/.test(c), 'completed chip ok');
ck(c.includes('פולו-אפ היום 2/4') && c.includes('שיחות 3'), 'status chips');
ck(K.goalsMiniTitle(agentJ) === 'היעדים שלי השבוע · 1/6', 'mini title: ' + K.goalsMiniTitle(agentJ));
ck(K.goalsMiniTitle(teamJ).indexOf('הצוות') >= 0, 'team mini title');
ck(K.goalsMiniTitle(oldJ).indexOf('להיום') >= 0, 'mini title fallback');

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
// יחיד כשנשאר 1 (שורת העידוד)
const one = JSON.parse(JSON.stringify(agentJ)); one.me.week.counts = Object.assign({}, one.me.week.targets, {meetings: 3});
ck(K.goalsCardHtml(one, {}).includes('רק עוד פגישה אחת'), 'singular push');
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
// [GOALS2 29/10] גיוס נכסים ראשון ומודגש (שבועי), פניות לנכס נולד, קונים מהחתמה, יעד המשרד לפי פעילים
const g2 = K.goalsCardHtml({ok: true, view: 'office', total: {agents: 12,
  counts: {listings: 1, meetings: 0, nb_wa: 7, buyers: 5, buyers_sign: 2, bpage: 1, past_clients: 0, reviews: 0, followups: {due: 0, done: 0}, missed: 0},
  targets: {listings: 24, meetings: 24, nb_wa: 120, buyers: 36, past_clients: 60, reviews: 24}}}, {});
ck(g2.indexOf('גיוס נכסים') > 0 && g2.indexOf('גיוס נכסים') < g2.indexOf('פגישות מנכס נולד'), 'listings first');
ck(/class="gk-g( done)? hl"/.test(g2), 'listings highlighted');
ck(g2.includes("goalsGo('/v2/sign?type=owner')") && /class="gBtn gold"/.test(g2), 'listings gold button to owner signing');
ck(g2.includes('פניות לנכס נולד') && g2.includes('7<i> / 120</i>'), 'nb_wa 7/120 (fallback without week)');
ck(g2.includes('2 מהחתמה') && g2.includes('דף קונה נשלח ל-1'), 'buyers from signings + bpage');
ck(g2.includes('12 סוכנים פעילים'), 'target by active agents');
ck(K.GOALS_KEYS.length === 6 && K.GOALS_KEYS[0] === 'listings', 'six goals, listings first');
const ha2 = K.goalsAgentsHtml({agents: [{name: 'ב', active: false, seen_today: false, counts: {buyers: 1}, targets: {}}]}, false);
ck(ha2.includes('לא נכנס/ה ב-10 ימים'), 'inactive agent label');
ck(/id="t_listings"/.test(PAGE) && /id="t_nb_wa"/.test(PAGE), 'edit sheet has new goals');
console.log('ok', n);
