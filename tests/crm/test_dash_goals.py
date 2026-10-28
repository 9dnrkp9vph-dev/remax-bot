# tests/crm/test_dash_goals.py — [GOALS 28/10] 'יעדי היום' בלוח הבקרה: היום / אתמול / השבוע, מגמה מול שבוע שעבר,
# וכיתוב ריבוע הסטורי ('ראה 1 = רק היעדים'). python3 tests/crm/test_dash_goals.py
import os, sys, re, json, subprocess, datetime as dt
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import _load
from _load import ck
from zoneinfo import ZoneInfo
import goals

IL = ZoneInfo("Asia/Jerusalem")
canon = lambda n: " ".join(str(n or "").split())
WED = dt.date(2026, 10, 28)          # רביעי
FRI = dt.date(2026, 10, 30)
SAT = dt.date(2026, 10, 31)
SUN = dt.date(2026, 10, 25)

# ── ימי עבודה ────────────────────────────────────────────────────────────────
ck(goals.week_start(WED) == SUN and goals.week_start(SUN) == SUN and goals.week_start(SAT) == SUN, "week starts Sunday")
ck(goals.workdays_elapsed(WED) == 4, goals.workdays_elapsed(WED))
ck(goals.workdays_elapsed(FRI) == 5.5 and goals.workdays_elapsed(SAT) == 5.5, "Friday = half, Saturday = 0")
ck(goals.workdays_elapsed(SUN) == 1, "Sunday = 1")


def at(day, h=11):
    return dt.datetime(day.year, day.month, day.day, h, 0, tzinfo=IL).timestamp()


def dmy(day, h=11):
    return dt.datetime(day.year, day.month, day.day, h, 0, tzinfo=IL).strftime("%d/%m/%Y %H:%M")


TUE, LAST_WED, LAST_TUE = WED - dt.timedelta(days=1), WED - dt.timedelta(days=7), WED - dt.timedelta(days=8)
nb = {"a1": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(WED), "pkey": "p1"},
      "a2": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(WED, 12), "pkey": "p2"},
      "a3": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(TUE), "pkey": "p3"},
      "a4": {"agent": "דנה כהן", "status": "meeting", "meeting_at": at(LAST_WED), "pkey": "p4"},
      "f1": {"agent": "רון לוי", "status": "followup", "date": WED.isoformat(), "done": True},
      "f2": {"agent": "רון לוי", "status": "followup", "date": TUE.isoformat()}}
buyers = [{"agent": "דנה כהן", "date": dmy(WED), "row": 1}, {"agent": "דנה כהן", "date": dmy(WED), "row": 2},
          {"agent": "דנה כהן", "date": dmy(WED), "row": 3}, {"agent": "רון לוי", "date": dmy(SUN), "row": 4}]
act = [{"action": goals.ACT_REMIND, "name": "רון לוי", "detail": "50000000%d" % i, "ts": at(WED)} for i in range(5)] + \
      [{"action": goals.ACT_REMIND, "name": "רון לוי", "detail": "500000009", "ts": at(TUE)},
       {"action": goals.ACT_REMIND, "name": "רון לוי", "detail": "500000009", "ts": at(LAST_TUE)}]
src = {"nb": nb, "buyers": buyers, "bpages": [{"row": 1, "last_sent_at": dmy(WED)}], "activity": act,
       "reviews": [], "missed": [{"agent": "רון לוי"}], "seen": ["דנה כהן"],
       "roster": ["רון לוי", "דנה כהן", "מיכל בר"], "cfg": {}}
o = goals.build_periods(src, WED, canon)
ck(set(o) == {"today", "yesterday", "week"}, o.keys())
T = o["today"]
ck(T["day"] == WED.isoformat(), T["day"])
names = [r["name"] for r in T["rows"]]
ck(names[0] == "דנה כהן" and "מיכל בר" in names and len(names) == 3, ("sorted by met desc, unseen still present", names))
dana = T["rows"][0]
ck(dana["counts"]["meetings"] == 2 and dana["counts"]["buyers"] == 3 and dana["counts"]["bpage"] == 1, dana["counts"])
ck(dana["met"] == 2 and dana["targets"]["meetings"] == 2, dana)        # פגישות 2/2 + קונים 3/3
ck(dana["trend"]["meetings"] == 1 and dana["trend"]["buyers"] == 3, ("vs last Wednesday", dana["trend"]))
ck(dana["seen_today"] is True, dana)
ron = next(r for r in T["rows"] if r["name"] == "רון לוי")
ck(ron["counts"]["past_clients"] == 5 and ron["met"] == 1 and ron["counts"]["missed"] == 1, ron)
ck(ron["counts"]["followups"] == {"due": 1, "done": 1}, ron["counts"]["followups"])
ck(next(r for r in T["rows"] if r["name"] == "מיכל בר")["seen_today"] is False, "unseen row present, flagged")
ck(T["total"]["counts"]["meetings"] == 2 and T["total"]["targets"]["meetings"] == 6, T["total"])
ck(T["total"]["met"] == 0, ("office: 2/6 meetings etc.", T["total"]))

Y = o["yesterday"]
ck(Y["day"] == TUE.isoformat(), Y["day"])
yr = next(r for r in Y["rows"] if r["name"] == "רון לוי")
ck(yr["counts"]["past_clients"] == 1 and yr["trend"]["past_clients"] == 0, yr)   # מול שלישי שעבר

W = o["week"]
ck(W["day"] == SUN.isoformat() and W["to"] == WED.isoformat(), W)
wd = next(r for r in W["rows"] if r["name"] == "דנה כהן")
ck(wd["targets"]["meetings"] == 8 and wd["targets"]["buyers"] == 12, ("4 workdays × daily", wd["targets"]))
ck(wd["counts"]["meetings"] == 3 and wd["counts"]["buyers"] == 3, wd["counts"])
ck(wd["trend"]["meetings"] == 2, ("Sun–Wed vs last Sun–Wed", wd["trend"]))
wr = next(r for r in W["rows"] if r["name"] == "רון לוי")
ck(wr["counts"]["past_clients"] == 6 and wr["counts"]["buyers"] == 1, ("summed per day", wr["counts"]))
ck(wr["counts"]["missed"] == 1, ("open calls are a current state, not summed", wr["counts"]))
ck(wr["counts"]["followups"] == {"due": 2, "done": 1}, wr["counts"]["followups"])
ck(W["total"]["targets"]["meetings"] == 24, W["total"]["targets"])

fw = goals.build_periods(dict(src, roster=["דנה כהן"]), FRI, canon)["week"]
ck(fw["rows"][0]["targets"]["meetings"] == 11 and fw["rows"][0]["targets"]["buyers"] == 16.5, ("Friday adds half", fw["rows"][0]["targets"]))

# מקור שנופל → None (—), לא 0, והשאר נספר
bad = goals.build_periods(dict(src, activity=RuntimeError("down")), WED, canon)["week"]
br = next(r for r in bad["rows"] if r["name"] == "רון לוי")
ck(br["counts"]["past_clients"] is None and br["trend"]["past_clients"] is None and br["counts"]["buyers"] == 1, br)
ck(goals.build_periods(dict(src, roster=RuntimeError("x")), WED, canon)["today"]["rows"] == [], "roster down → no rows")

# ── crm_dashboard_data מעביר את מקור היעדים ────────────────────────────────────
ns = _load.load("crm_dashboard_data", "_CRM_EFFIE_AI", "CRM_STREAMS", "crm_health", "_work_hours_between", "crm_daily_series", "crm_ts",
                "inv_parse_dt", "crm_nb_area_last", "crm_period_bounds", "crm_agent_table", "crm_todo", "bs_p9", "_CRM_NB_CONTACT",
                "_CRM_BPAGE_SEND", "crm_wa_official", "crm_story_stats", "_CRM_WA_OFFICIAL", "_CRM_DASH_HTML")
now = at(WED, 15)
d = ns["crm_dashboard_data"]({"goals": lambda: o}, now, False, WED.isoformat())
ck(d["goals"] is o, "goals passed through")
d2 = ns["crm_dashboard_data"]({"goals": lambda: (_ for _ in ()).throw(RuntimeError("x"))}, now, False, WED.isoformat())
ck(d2["goals"] is None, "goals source down → None, dashboard still builds")

# ── הדף: כרטיס 'יעדי היום' + כיתוב הסטורי ─────────────────────────────────────
h = ns["_CRM_DASH_HTML"]
m = re.search(r"<script>(\s*var P='month'.*?)</script>", h, re.S)
ck(m, "dashboard script")
D = {"goals": json.loads(json.dumps(o, ensure_ascii=False)),
     "periods": {"calls": {}, "calls_answered": {}, "signings_by_label": {}, "signings": {}, "buyers": {}, "newborn": {}, "shtaf": {},
                 "deals_closed": {}, "deals_opened": {}},
     "story": {"month": {"taps": 3, "tap_people": 2, "autos": 4, "past_summary": 2, "full": 1}}}
js = ("var document={getElementById:function(){return {}}},localStorage={getItem:function(){return ''}},fetch=function(){return {then:function(){return {then:function(){return {catch:function(){}}},catch:function(){}}}}},setInterval=function(){};"
      + m.group(1).split("function render(){")[0] + ";D=" + json.dumps(D, ensure_ascii=False)
      + ";var a=goalsCard();GP='week';var b=goalsCard();GP='yesterday';var c=goalsCard();console.log(a+'\\n@@\\n'+b+'\\n@@\\n'+c+'\\n@@\\n'+kpis());")
out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
ck(out.returncode == 0, out.stderr[-800:])
gt, gw, gy, kp = out.stdout.split("@@")
for col in ("סוכן", "פגישות נכס נולד", "קונים", "דף קונה", "לקוחות עבר", "המלצות", "פולו-אפ", "שיחות פתוחות", "עמידה"):
    ck("<th>" + col in gt, ("column", col))
ck(gt.index("כל המשרד") < gt.index("דנה כהן") < gt.index("מיכל בר"), "office row first, then by met")
ck(gt.count("· לא נכנס/ה היום") == 2 and 'class="z"><td>מיכל בר' in gt, "unseen (רון, מיכל) flagged on today, greyed")
ck("לא נכנס" not in gw and "לא נכנס" not in gy, "only on today")
ck("2/2" in gt and "3/3" in gt and "2/4" in gt, gt)
ck("3/8" in gw and "16.5" not in gw and "ימי עבודה" in gw, "week shows target × workdays")
ck("↑4 מול רביעי שעבר" in gt and "כמו ברביעי שעבר" in gt and "מול שבוע שעבר" in gw, "trend label")
ck("#C24040" not in gt and "red" not in gt, "no red")
ck("ראה 1 = רק היעדים" in kp, kp)
print("dash_goals OK", _load.n)

# ── [fix 1] היום בלוח הבקרה = build_office (אותה ליבה) ─────────────────────────────
s_today = dict(src, activity=[a for a in act if goals._in(goals.parse_ts(a["ts"]), goals.day_bounds(WED))])  # כמו במסלול היום
bo = goals.build_office(s_today, WED, canon)
bp = goals.build_periods(s_today, WED, canon)["today"]
for k in ("counts", "targets", "partial"):
    ck(bp["total"][k] == bo["total"][k], ("today totals == build_office", k, bp["total"][k], bo["total"][k]))
ck(sorted((r["name"], json.dumps(r["counts"], sort_keys=True), r["seen_today"]) for r in bp["rows"]) ==
   sorted((r["name"], json.dumps(r["counts"], sort_keys=True), r["seen_today"]) for r in bo["rows"]), "same rows")
ck(set(bo["rows"][0]) == {"name", "counts", "targets", "seen_today"}, ("build_office row shape unchanged", bo["rows"][0].keys()))
bad_r = goals.build_office(dict(src, roster=RuntimeError("x")), WED, canon)
ck(bad_r["rows"] == [] and bad_r["total"]["partial"] is True, bad_r)

# ── [fix 2] היום/אתמול לפי משקל יום העבודה (שבת 0 = הושלם; שישי חצי) ────────────────
sat = goals.build_periods(dict(src, roster=["דנה כהן"]), SAT, canon)
st = sat["today"]["rows"][0]
ck(st["targets"] == {"meetings": 0, "buyers": 0, "past_clients": 0, "reviews": 0}, st["targets"])
ck(st["met"] == 4 and st["goals_n"] == 4, ("Saturday target 0 counts as met", st))
ck(sat["yesterday"]["rows"][0]["targets"]["meetings"] == 1 and sat["yesterday"]["rows"][0]["targets"]["buyers"] == 1.5, "Friday yesterday = half")
sun = goals.build_periods(dict(src, roster=["דנה כהן"]), dt.date(2026, 11, 1), canon)
ck(sun["yesterday"]["day"] == SAT.isoformat() and sun["yesterday"]["rows"][0]["targets"]["meetings"] == 0, ("Sunday's yesterday = Saturday, 0", sun["yesterday"]))
ck(sun["today"]["rows"][0]["targets"]["meetings"] == 2, "Sunday today = full daily target")
D2 = {"goals": json.loads(json.dumps(sat, ensure_ascii=False))}
js2 = js.split(";D=")[0] + ";D=" + json.dumps(D2, ensure_ascii=False) + ";console.log(goalsCard());"
o2 = subprocess.run(["node", "-e", js2], capture_output=True, text=True)
ck(o2.returncode == 0, o2.stderr[-500:])
ck("0/—" in o2.stdout and "0/0" not in o2.stdout and "<b>4/4</b>" in o2.stdout, ("target 0 shown as —", o2.stdout[:600]))
# האפליקציה: הכרטיס של הסוכן נשאר עם היעד היומי המלא (build_office לא משקלל)
ck(goals.build_office(dict(src, roster=["דנה כהן"]), SAT, canon)["rows"][0]["targets"]["meetings"] == 2, "app keeps plain daily target")
print("dash_goals fix1/2 OK", _load.n)

# ── dashboard_goals: שליפת המקורות (יומן מסונן בשרת מתחילת השבוע הקודם) ─────────────
class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None
asked = {}
class SB:
    def enabled(self): return True
    def bpage_all(self): return []
    def fetch_activity_actions(self, t0, prefixes):
        asked["t0"], asked["p"] = t0, prefixes
        return [{"action": goals.ACT_REMIND, "name": "דנה כהן", "detail": "501", "ts": at(WED)}]
Gf = AutoG(log=None, _sbdb=SB(), _load_config=lambda: {"nbStatus": nb},
           _fetch_manual_buyers=lambda: (_ for _ in ()).throw(RuntimeError("down")),
           _canon_key=canon, _canon_agent_name=lambda n: n, _name_key=canon,
           _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
           _contacts_rows=lambda: [["דנה כהן", "0501111111"]], _suspended_set=lambda: set(),
           _removed_agent_keys=lambda: set(), _resolve_roles=lambda l9: ("agent", "agent"),
           web_fetch_raw=lambda *a: [], _usage_rows=lambda start: [{"name": "דנה כהן"}])
import effie_v2  # noqa: E402  (crm_roster / crm_todo)
gd = goals.dashboard_goals(Gf, at(WED, 15))
ck(asked["p"] == (goals.ACT_REMIND,) and asked["t0"] == goals.day_bounds(dt.date(2026, 10, 18))[0], ("from last week's Sunday", asked))
r0 = gd["today"]["rows"][0]
ck(r0["name"] == "דנה כהן" and r0["counts"]["past_clients"] == 1 and r0["counts"]["meetings"] == 2, r0["counts"])
ck(r0["counts"]["buyers"] is None and r0["seen_today"] is True, ("buyers down → —", r0))
print("dash_goals fetch OK", _load.n)
