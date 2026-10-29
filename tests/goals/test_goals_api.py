"""API היעדים: /v2/api/goals/today, /office, /targets. python3 tests/goals/test_goals_api.py"""
import os, sys, json, time, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from zoneinfo import ZoneInfo
from flask import Flask
import goals
import site_api

IL = ZoneInfo("Asia/Jerusalem")


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


def _key(n):
    return " ".join(str(n or "").split())


AGENT = {"name": "דנה כהן", "role": "agent", "drole": "agent", "phone": "501111111"}
COORD = {"name": "אוצר", "role": "coordinator", "drole": "coordinator", "phone": "509999999"}
MGR = {"name": "אייל שמול", "role": "admin", "drole": "manager", "phone": "505709865"}
CONTACTS = [["דנה כהן", "0501111111"], ["רון לוי", "0502222222"], ["מיכל בר", "0503333333"],
            ["חשבון בדיקה", "0504444444"], ["מושהה", "0505555555"], ["חגית", "0506666666"]]


def now_dmy():
    return dt.datetime.now(IL).strftime("%d/%m/%Y %H:%M")


def make(sess, buyers_fail=False, cfg=None, tv_key="", swr=None, buyers_list=None, coord_fail=False):
    os.environ["TV_KEY"] = tv_key
    now_iso = dt.datetime.now(IL).strftime("%Y-%m-%dT%H:%M")
    cfg = cfg if cfg is not None else {
        "office_name": "רימקס פמילי",
        "nbStatus": {
            "דנה::a": {"agent": "דנה כהן", "status": "meeting", "meeting_at": time.time(), "pkey": "x1"},
            "רון::b": {"agent": "רון לוי", "status": "meeting", "meeting_at": time.time(), "pkey": "x2"},
            "רון::c": {"agent": "רון לוי", "status": "meeting", "meeting_at": time.time(), "pkey": "x3"},
            "מיכל::d": {"agent": "מיכל בר", "status": "meeting", "meeting_at": time.time(), "pkey": "x4"}}}
    state = {"cfg": cfg, "act_calls": [], "mutates": 0, "logs": [], "cleared": []}

    def mutate(fn):
        state["mutates"] += 1
        res = fn(state["cfg"])
        return True, res

    def buyers():
        if buyers_fail:
            raise RuntimeError("boom")
        if buyers_list is not None:
            return list(buyers_list)
        return [{"agent": "דנה כהן", "date": now_dmy(), "row": 5}, {"agent": "רון לוי", "date": now_dmy(), "row": 6}]

    class SB:
        def enabled(self): return True
        def bpage_all(self): return [{"row": 5, "last_sent_at": now_iso}]
        def fetch_activity_actions(self, t0, prefixes):
            state["act_calls"].append(tuple(prefixes))
            return [{"action": goals.ACT_REMIND, "name": "דנה כהן", "detail": "501234567", "ts": time.time()}]

    calls_t = (dt.datetime.now(IL) - dt.timedelta(hours=1)).strftime("%d/%m/%Y %H:%M")
    G = AutoG(
        log=None,
        _web_auth=lambda: sess,
        _swr=swr or (lambda k, ttl, b, **kw: b()),
        _cache_clear=lambda k: state["cleared"].append(k),
        _load_config=lambda: state["cfg"],
        _config_mutate=mutate,
        _log_activity=lambda *a: state["logs"].append(a),
        _fetch_manual_buyers=buyers,
        _sbdb=SB(),
        _activity_fetch=lambda t0, today=True: [{"action": goals.ACT_REMIND, "name": "דנה כהן", "detail": "501234567", "ts": time.time()}],
        web_fetch_raw=lambda *a: [{"caller_phone": "0541112222", "agent": "רון לוי", "status": "NOANSWER", "received_at": calls_t}],
        _is_answered_status=lambda st: str(st).upper() == "ANSWER",
        _canon_key=_key, _canon_agent_name=lambda n: n, _name_key=_key,
        _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
        _coordinators_all=(lambda: (_ for _ in ()).throw(RuntimeError("cfg down"))) if coord_fail else lambda: {"509999999": {"name": "אוצר", "agents": {"502222222"}, "names": {"מיכל בר"}}},
        web_phone_name_map=lambda: {"502222222": "רון לוי"},
        web_contacts_phone_name=lambda: {},
        _contacts_rows=lambda: CONTACTS,
        _suspended_set=lambda: {"505555555"},
        _removed_agent_keys=lambda: set(),
        _resolve_roles=lambda l9: ("admin", "accountant") if l9 == "506666666" else ("agent", "agent"),
        # היום נכנסה רק דנה; ב-10 הימים האחרונים — דנה ורון (מיכל לא נכנסה, אבל יש לה פגישה)
        # [GOALS3] פעיל = לפחות 10 דק' ב-10 ימים; 'אייל שמול' מנהל — לא נספר; 'עדי קצר' 4 דק' — לא נספר
        _usage_rows=lambda t_from, *a, **kw: ([{"name": "דנה כהן", "min": 5}]
                                             if t_from.date() >= dt.datetime.now(IL).date()
                                             else [{"name": "דנה כהן", "min": 15}, {"name": "רון לוי", "min": 30},
                                                   {"name": "אייל שמול", "min": 300}, {"name": "עדי קצר", "min": 4}]),
        get_signings=lambda frm, to: [
            {"agent": "דנה כהן", "address": "הרצל 5, קרית ביאליק", "deal_type": "OWNER_EXCLUSIVE",
             "commission_pct": "https://x/s/1", "received_at": now_dmy()},
            {"agent": "דנה כהן", "address": "הרצל 5 קריית ביאליק", "deal_type": "OWNER_EXCLUSIVE",
             "commission_pct": "2", "received_at": now_dmy()},                      # אותו נכס — נספר פעם אחת
            {"agent": "דנה כהן", "address": "בגין 3", "deal_type": "OWNER_EXCLUSIVE",
             "commission_pct": "", "received_at": now_dmy()},                       # לא נחתם
            {"agent": "רון לוי", "address": "ויצמן 7", "deal_type": "OWNER_SALE",
             "commission_pct": "2", "received_at": now_dmy()}],                     # מוכר, לא בלעדיות
        _deal_label=lambda c: {"OWNER_EXCLUSIVE": "בלעדיות", "OWNER_SALE": "מוכר"}.get(c, "קונים"),
    )
    goals._ACTIVE_BOX.update(k=None, t=0.0, v=None)
    site_api.review_rows = lambda sb=None: [{"kind": "review", "key": "r1", "data": {
        "agents": ["מיכל בר"], "text": "מעולה", "at": dt.datetime.now(IL).isoformat()}}]
    app = Flask(__name__)
    goals.register(app, G)
    return app.test_client(), state


def _today():
    return dt.datetime.now(IL).date()


def _plan(cfg, agents):
    return goals.office_plan(cfg, agents, _key, _today())


def _daily(cfg, agents, name):
    p = _plan(cfg, agents)
    return goals.scaled(goals.rates_for(p, name, _key), 1)


ACTIVE = ["דנה כהן", "רון לוי"]


def test_agent_own_only():
    c, _ = make(AGENT)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["ok"] and j["view"] == "agent" and j["can_edit"] is False, j
    assert j["me"]["counts"]["meetings"] == 1 and j["me"]["counts"]["buyers"] == 1, j
    assert j["me"]["counts"]["bpage"] == 1 and j["me"]["counts"]["past_clients"] == 1, j
    assert j["me"]["targets"] == _daily({}, ACTIVE, "דנה כהן") and j["total"] is None and "agents" not in j, j
    assert j["me"]["targets"]["meetings"] >= 1 and j["me"]["targets"]["buyers"] >= 1, j   # מעוגל למעלה
    assert j["day"] == dt.datetime.now(IL).date().isoformat()


def test_scope_guard():
    c, _ = make(AGENT)
    j = c.get("/v2/api/goals/today?agent=" + "רון לוי").get_json()
    assert j["view"] == "agent" and j["me"]["counts"]["meetings"] == 1, j   # עדיין שלה, לא של רון
    c, _ = make(COORD)
    assert c.get("/v2/api/goals/today?agent=" + "דנה כהן").status_code == 403
    j = c.get("/v2/api/goals/today?agent=" + "רון לוי").get_json()
    assert j["view"] == "agent" and j["me"]["counts"]["meetings"] == 2, j
    c, _ = make(MGR)
    j = c.get("/v2/api/goals/today?agent=" + "דנה כהן").get_json()
    assert j["view"] == "agent" and j["me"]["counts"]["meetings"] == 1 and j["can_edit"] is True, j
    c, _ = make(None)
    assert c.get("/v2/api/goals/today").status_code == 403


def test_team_rollup():
    c, _ = make(COORD)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["view"] == "team" and j["me"] is None and j["can_edit"] is False, j
    names = sorted(a["name"] for a in j["agents"])
    assert names == ["מיכל בר", "רון לוי"], names
    t = j["total"]
    assert t["counts"]["meetings"] == 3 and t["counts"]["buyers"] == 1 and t["counts"]["reviews"] == 1, t
    # יעד הצוות = רק מי שנכנס ב-10 ימים (רון); מיכל מוצגת כי יש לה פגישה, בלי יעד
    want = goals.sum_scaled(_plan({}, ACTIVE), ["רון לוי"], _key, 1)
    assert t["counts"]["missed"] == 1 and t["targets"] == want and t["agents"] == 1 and t["partial"] is False, t
    assert all(a["seen_today"] is False for a in j["agents"]), j
    act = {a["name"]: a["active"] for a in j["agents"]}
    assert act == {"רון לוי": True, "מיכל בר": False}, act


def test_office_view():
    c, _ = make(MGR)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["view"] == "office" and j["can_edit"] is True, j
    names = sorted(a["name"] for a in j["agents"])
    assert names == sorted(["דנה כהן", "רון לוי", "מיכל בר"]), names   # בלי בדיקה/מושהה/הנה"ח
    seen = {a["name"]: a["seen_today"] for a in j["agents"]}
    assert seen["דנה כהן"] is True and seen["רון לוי"] is False, seen
    want = goals.office_scaled(_plan({}, ACTIVE), 1)            # יעד המשרד לחודש, ליום
    assert j["total"]["counts"]["meetings"] == 4 and j["total"]["targets"] == want, j
    assert j["total"]["agents"] == 2 and j["total"]["share_agents"] == 2, j           # דנה + רון בלבד
    assert j["total"]["office_month"] == goals.OFFICE_MONTH, j
    assert all(a["name"] != "אייל שמול" for a in j["agents"]), j


def test_office_kiosk():
    c, _ = make(None, tv_key="K123")
    assert c.get("/v2/api/goals/office?k=bad").status_code == 403
    assert c.get("/v2/api/goals/office").status_code == 403
    r = c.get("/v2/api/goals/office?k=K123")
    j = r.get_json()
    assert j["ok"] and set(j) == {"ok", "total"} and j["total"]["counts"]["meetings"] == 4, j
    raw = r.get_data(as_text=True)
    txt = json.dumps(j, ensure_ascii=False)
    for n in ("דנה", "רון", "מיכל"):
        assert n not in txt and n not in raw, n
    c, _ = make(AGENT)   # Ruling 2: כל משתמש מחובר — סכומים בלבד
    j = c.get("/v2/api/goals/office").get_json()
    assert set(j) == {"ok", "total"}, j


def test_targets_manager_only():
    for s in (AGENT, COORD, None):
        c, st = make(s)
        assert c.post("/v2/api/goals/targets", json={"agent": "", "targets": {"meetings": 4}}).status_code == 403
        assert st["mutates"] == 0
    c, st = make(MGR)
    j = c.post("/v2/api/goals/targets", json={"agent": "", "targets": {"meetings": 400, "zzz": 9}}).get_json()
    assert j["ok"] and j["targets"] == dict(goals.OFFICE_MONTH, meetings=400), j        # יעד המשרד לחודש
    j = c.post("/v2/api/goals/targets", json={"agent": "רון לוי", "targets": {"buyers": 7, "reviews": "999"}}).get_json()
    assert j["targets"] == {"buyers": 7, "reviews": 999}, j                              # יעד אישי לחודש
    assert st["mutates"] == 2
    gl = st["cfg"]["v2_goals"]
    assert gl["office"] == {"meetings": 400} and gl["agents_month"]["רון לוי"] == {"buyers": 7, "reviews": 999}, gl
    acts = [l for l in st["logs"] if l[3] == "יעדים — עדכון"]
    assert len(acts) == 2 and "רון לוי" in acts[1][4] and "7" in acts[1][4], acts
    j = c.get("/v2/api/goals/today?agent=" + "רון לוי").get_json()
    assert j["me"]["targets"]["buyers"] == 1, j                     # 7 בחודש → פחות מ-1 ביום → מעוגל ל-1
    # דנה מקבלת את היתרה: 120 − 7 = 113 בחודש
    j = c.get("/v2/api/goals/today").get_json()
    row = {a["name"]: a for a in j["agents"]}
    assert row["רון לוי"]["monthly"]["buyers"] == 7 and row["דנה כהן"]["monthly"]["buyers"] == 113, row
    assert row["רון לוי"]["own"] == ["buyers", "reviews"] and row["דנה כהן"]["own"] == [], row
    assert row["דנה כהן"]["monthly"]["meetings"] == 200, row         # 400 / 2
    j = c.post("/v2/api/goals/targets", json={"agent": "רון לוי", "clear": True}).get_json()
    assert j["ok"] and "רון לוי" not in st["cfg"]["v2_goals"]["agents_month"], st["cfg"]
    assert c.post("/v2/api/goals/targets", json={"agent": "", "clear": True}).status_code == 400
    assert c.post("/v2/api/goals/targets", json={"agent": "", "targets": "x"}).status_code == 400


def test_source_failure_dash():
    c, _ = make(AGENT, buyers_fail=True)
    r = c.get("/v2/api/goals/today")
    assert r.status_code == 200
    j = r.get_json()
    assert j["me"]["counts"]["buyers"] is None and j["me"]["counts"]["bpage"] is None, j
    assert j["me"]["counts"]["meetings"] == 1, j
    c, _ = make(MGR, buyers_fail=True)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["total"]["counts"]["buyers"] is None and j["total"]["partial"] is True, j


def test_build_office_pure():
    day = dt.datetime.now(IL).date()
    src = {"roster": ["א", "ב"], "cfg": {}, "seen": ["א"], "nb": {}, "buyers": [], "bpages": [],
           "activity": [], "reviews": [], "missed": []}
    o = goals.build_office(src, day, _key)
    assert [r["name"] for r in o["rows"]] == ["א", "ב"] and o["rows"][0]["seen_today"] is True
    assert o["total"]["targets"] == goals.office_scaled(_plan({}, ["א", "ב"]), 1) and o["total"]["counts"]["meetings"] == 0
    o = goals.build_office(dict(src, roster=RuntimeError("x")), day, _key)
    assert o["rows"] == [] and o["total"]["partial"] is True, o


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


def real_swr(clock):
    """כמו app._swr: טרי → מוחזר; פג עד max_stale → מוחזר הישן ובנייה 'ברקע' (כאן מיד); אחרת בנייה."""
    cache = {}

    def swr(key, ttl, build, max_stale=1800):
        e = cache.get(key)
        now = clock()
        if e and now - e[0] < ttl:
            return e[1]
        if e and now - e[0] < max_stale:
            cache[key] = (clock(), build())
            return e[1]
        v = build()
        cache[key] = (clock(), v)
        return v
    return swr


def test_fresh_after_ttl():
    clk = Clock(time.time())
    goals._clock = clk
    try:
        bl = [{"agent": "דנה כהן", "date": now_dmy(), "row": 5}]
        c, _ = make(AGENT, swr=real_swr(clk), buyers_list=bl)
        assert c.get("/v2/api/goals/today").get_json()["me"]["counts"]["buyers"] == 1
        bl.append({"agent": "דנה כהן", "date": now_dmy(), "row": 7})
        clk.t += 61
        c.get("/v2/api/goals/today")                        # לכל היותר תשובה ישנה אחת (בונה ברקע)
        j = c.get("/v2/api/goals/today").get_json()
        assert j["me"]["counts"]["buyers"] == 2, j          # הבנייה ברקע קיבלה מקורות טריים
        clk.t += 2000                                       # מעבר ל-max_stale (30 דק') — בנייה בתוך הבקשה
        bl.append({"agent": "דנה כהן", "date": now_dmy(), "row": 8})
        assert c.get("/v2/api/goals/today").get_json()["me"]["counts"]["buyers"] == 3
    finally:
        goals._clock = goals._tm.time


def test_scoped_max_stale_30min():
    """המטמון של היעדים מחזיר ישן עד 30 דק' (בנייה ברקע) — לא בונה בתוך הבקשה."""
    seen = []
    base = lambda k, ttl, b, **kw: (seen.append(kw.get("max_stale")), b())[1]
    c, _ = make(AGENT, swr=base)
    c.get("/v2/api/goals/today")
    assert seen and all(m is not None and m >= 1800 for m in seen), seen


def test_activity_filtered_fetch():
    c, st = make(AGENT)
    j = c.get("/v2/api/goals/today").get_json()
    assert st["act_calls"] and st["act_calls"][0] == (goals.ACT_REMIND, goals.ACT_NB_WA), st["act_calls"]
    assert j["me"]["counts"]["past_clients"] == 1, j


def test_no_yesterday_after_midnight():
    d = dt.datetime.now(IL).date()
    clk = Clock(dt.datetime(d.year, d.month, d.day, 23, 59, 40, tzinfo=IL).timestamp())
    goals._clock = clk
    try:
        c, _ = make(MGR, swr=real_swr(clk))
        assert c.get("/v2/api/goals/today").get_json()["day"] == d.isoformat()
        clk.t += 30                                          # 00:00:10 — עדיין בתוך ה-TTL
        j = c.get("/v2/api/goals/today").get_json()
        nxt = (d + dt.timedelta(days=1)).isoformat()
        assert j["day"] == nxt, j["day"]
        assert j["total"]["counts"]["meetings"] == 0, j      # הפגישות של אתמול לא נספרות היום
        k = c.get("/v2/api/goals/office").get_json()
        assert k["total"]["counts"]["meetings"] == 0, k
    finally:
        goals._clock = goals._tm.time


def test_coord_team_failure():
    c, _ = make(COORD, coord_fail=True)
    r = c.get("/v2/api/goals/today")
    assert r.status_code == 200, r.status_code
    j = r.get_json()
    assert j["view"] == "team" and j["agents"] == [] and j["total"]["partial"] is True, j
    assert c.get("/v2/api/goals/today?agent=" + "רון לוי").status_code == 403




def test_listings_and_nb_wa():
    """גיוס נכסים: בלעדיות שנחתמה, נכס ייחודי; פניות לנכס נולד: וואטסאפ ייחודי לכל מודעה ביום."""
    c, st = make(AGENT)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["me"]["counts"]["listings"] == 1, j
    assert j["me"]["targets"]["listings"] == _daily({}, ACTIVE, "דנה כהן")["listings"], j
    assert goals.ACT_NB_WA in st["act_calls"][0], st["act_calls"]


def test_inactive_hidden_without_counts():
    day = dt.datetime.now(IL).date()
    src = {"roster": ["א", "ב", "ג"], "cfg": {}, "seen": [], "active": ["א"], "nb": {},
           "buyers": [{"agent": "ב", "date": now_dmy(), "summary": "מהחתמת מתעניין · הרצל 1"}],
           "bpages": [], "activity": [], "reviews": [], "missed": [], "sigs": []}
    o = goals.build_office(src, day, _key)
    rows = {r["name"]: r for r in o["rows"]}
    assert set(rows) == {"א", "ב"}, rows                          # ג לא נכנס ולא עשה כלום → לא מוצג
    assert rows["ב"]["active"] is False and rows["ב"]["counts"]["buyers_sign"] == 1
    assert o["total"]["counts"]["buyers"] == 1 and o["total"]["agents"] == 1, o
    assert o["total"]["targets"]["buyers"] == goals.office_scaled(_plan({}, ["א"]), 1)["buyers"], o
    o = goals.build_office(dict(src, active=None), day, _key)       # מקור לא זמין → כולם עם יעד
    assert o["total"]["agents"] == 3 and len(o["rows"]) == 3, o


def test_sigs_use_signed_time():
    """גיוס נכסים לפי שעת החתימה (sign_docs), לא שעת השליחה."""
    class SB:
        def enabled(self): return True
        def signdoc_times(self): return {"tok1": "2026-10-25T09:00:00+02:00"}
    G = AutoG(_sbdb=SB(), _deal_label=lambda c: "בלעדיות",
              get_signings=lambda frm, to: [{"agent": "א", "address": "הרצל 5", "deal_type": "OWNER_EXCLUSIVE",
                                             "commission_pct": "https://x/s/tok1", "received_at": "22/10/2026 10:00"},
                                            {"agent": "א", "address": "בגין 1", "deal_type": "OWNER_EXCLUSIVE",
                                             "commission_pct": "2", "received_at": "26/10/2026 10:00"}])
    rows = goals.g_sigs(G, dt.date(2026, 10, 18))
    assert rows[0]["ts"] == "2026-10-25T09:00:00+02:00" and rows[1]["ts"] == "26/10/2026 10:00", rows
    n = goals.count_listings("א", goals.week_bounds(dt.date(2026, 10, 28)), rows, _key)
    assert n == 2, n


def test_active_min_and_staff():
    """[GOALS3] פעיל = לפחות 10 דק' ב-10 ימים; מנהל לא נספר גם כשהשתמש הרבה."""
    c, _ = make(MGR)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["total"]["share_agents"] == 2, j        # דנה (15) + רון (30); עדי (4 דק') ואייל (מנהל) — לא


def test_plan_division():
    day = dt.date(2026, 11, 10)                      # נובמבר 2026: 24 ימי עבודה, 30 יום
    p = goals.office_plan({}, ["א", "ב", "ג", "ד"], _key, day)
    r = goals.rates_for(p, "א", _key)
    assert goals.scaled(r, 1) == {"listings": 5, "meetings": 2, "nb_wa": 11, "buyers": 2, "past_clients": 4,
                                  "reviews": 4}, goals.scaled(r, 1)
    assert {k: goals._ceil(v) for k, v in goals.monthly_for(p, "א", _key).items()} == \
        {"listings": 20, "meetings": 40, "nb_wa": 250, "buyers": 30, "past_clients": 75, "reviews": 75}
    assert goals.office_scaled(p, 24, 30 / 7.0) == goals.OFFICE_MONTH
    cfg = {"v2_goals": {"office": {"meetings": 100}, "agents_month": {"א": {"meetings": 40}}}}
    p = goals.office_plan(cfg, ["א", "ב", "ג"], _key, day)
    m = {n: goals.monthly_for(p, n, _key)["meetings"] for n in ("א", "ב", "ג")}
    assert round(m["א"]) == 40 and round(m["ב"]) == 30 and round(m["ג"]) == 30, m
    cfg = {"v2_goals": {"office": {"meetings": 10}, "agents_month": {"א": {"meetings": 40}}}}
    p = goals.office_plan(cfg, ["א", "ב"], _key, day)
    assert goals.monthly_for(p, "ב", _key)["meetings"] == 0                  # יתרה שלילית → 0
    assert goals.scaled(goals.rates_for(p, "לא פעיל", _key), 1)["meetings"] == 0


def test_g_active_rules():
    """פעיל = 10 דק'+ ב-10 ימים, בלי מנהלים/מתאמות (תפקיד בניהול, מפת תפקידים, רשימת המתאמות)."""
    G = AutoG(_usage_rows=lambda t, *a, **k: [{"name": "דנה", "min": 20}, {"name": "מתן", "min": 50},
                                                {"name": "קצר", "min": 3}, {"name": "הודיה", "min": 40},
                                                {"name": "נוי", "min": 40}],
              _canon_key=_key, _canon_agent_name=lambda n: n,
              _contacts_rows=lambda: [["מתן", "0507000001"], ["דנה", "0507000002"]],
              _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
              _resolve_roles=lambda l9: ("admin", "manager") if l9 == "507000001" else ("agent", "agent"),
              _load_config=lambda: {"roles": {"0507000003": "coordinator"}},
              _display_name_for=lambda n, ph: {"507000003": "נוי"}.get(ph, n),
              _coordinators_all=lambda: {"509": {"name": "הודיה"}})
    goals._ACTIVE_BOX.update(k=None, t=0.0, v=None)
    assert sorted(goals.g_staff(G)) == sorted(["מתן", "נוי", "הודיה"]), goals.g_staff(G)
    assert goals.g_active(G, _today()) == ["דנה"], goals.g_active(G, _today())
    goals._ACTIVE_BOX.update(k=None, t=0.0, v=None)
    G["_usage_rows"] = lambda t, *a, **k: []
    assert goals.g_active(G, _today()) is None
    goals._ACTIVE_BOX.update(k=None, t=0.0, v=None)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
