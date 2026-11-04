"""ראוטי התחרות. python3 tests/contest/test_api.py"""
import os, sys, copy, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from zoneinfo import ZoneInfo
from flask import Flask
import contest

IL = ZoneInfo("Asia/Jerusalem")
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=IL).timestamp()
contest._now = lambda: NOW


class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


def _key(n):
    return " ".join(str(n or "").split())


REV = {"name": "רויטל גל", "role": "agent", "drole": "agent", "phone": "501111111"}
MGR = {"name": "אייל שמול", "role": "admin", "drole": "manager", "phone": "505709865"}
COORD_MGR = {"name": "נוי רבן", "role": "admin", "drole": "manager", "phone": "507777777"}
COORD_ROLE = {"name": "מישהי", "role": "coordinator", "drole": "coordinator", "phone": "508888888"}
COORD_CFG = {"name": "אוצר", "role": "admin", "drole": "manager", "phone": "509999999"}


def make(sess, tv_key="", nb=None, cfg_extra=None, disp=None, g_extra=None):
    contest._LAST_GOOD.clear()
    os.environ["TV_KEY"] = tv_key
    cfg = {"nbStatus": nb if nb is not None else {
        "a": {"agent": "רויטל גל", "by": "רויטל גל", "status": "meeting", "meeting_at": NOW - 3600, "date": NOW - 3600}}}
    cfg.update(cfg_extra or {})
    st = {"cfg": cfg, "mut": 0, "logs": [], "cleared": [], "swr": [], "sig_fail": False}

    def signings(a, b):
        if st["sig_fail"]:
            raise RuntimeError("sheets down")
        return []

    def swr(k, ttl, b, **kw):
        st["swr"].append(k)
        return b()

    def mutate(fn):
        st["mut"] += 1
        return True, fn(st["cfg"])

    G = AutoG(
        log=None, _web_auth=lambda: sess, _swr=swr,
        _cache_clear=lambda k: st["cleared"].append(k), _load_config=lambda: st["cfg"],
        _config_mutate=mutate, _log_activity=lambda *a: st["logs"].append(a),
        _display_name_for=disp or (lambda n, p: n), _canon_key=_key, _canon_agent_name=lambda n: n,
        _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
        _coordinators_all=lambda: {"509999999": {"name": "אוצר", "agents": set(), "names": set()}},
        get_signings=signings, _deal_label=lambda c: "")
    G.update(g_extra or {})
    app = Flask(__name__)
    contest.register(app, G)
    return app.test_client(), st


def pts(j, name):
    return [r for g in j["board"]["groups"] for r in g["rows"] if r["label"] == name][0]["points"]


def test_auth():
    c, _ = make(None)
    assert c.get("/v2/api/contest").status_code == 403
    c, _ = make(None, tv_key="K1")
    assert c.get("/v2/api/contest?k=K1").status_code == 200
    assert c.get("/v2/api/contest?k=bad").status_code == 403


def test_me_and_edit():
    c, _ = make(REV)
    j = c.get("/v2/api/contest").get_json()
    assert j["mode"] == "live" and j["me"]["group"] == 0 and j["me"]["kind"] == "row" and j["can_edit"] is False, j
    assert pts(j, "רויטל גל") == 5, j
    c, _ = make(MGR)
    assert c.get("/v2/api/contest").get_json()["can_edit"] is True
    for s in (COORD_MGR, COORD_ROLE, COORD_CFG):
        c, _ = make(s, cfg_extra={"coordinators": [{"coordinator": "אוצר", "agents": []}]})
        j = c.get("/v2/api/contest").get_json()
        assert j["can_edit"] is False, s
        assert c.post("/v2/api/contest/save", json={"contest": contest.NOV_2026}).status_code == 403
        assert c.post("/v2/api/contest/adjust", json={"contest": "2026-11", "group": 0, "kind": "row",
                                                      "label": "רויטל גל", "pts": 5, "reason": "x"}).status_code == 403


def test_save():
    c, st = make(REV)
    assert c.post("/v2/api/contest/save", json={"contest": contest.NOV_2026}).status_code == 403
    c, st = make(MGR)
    bad = copy.deepcopy(contest.NOV_2026)
    bad["groups"][0]["rows"][0]["members"].append("אור צוקרמן")
    r = c.post("/v2/api/contest/save", json={"contest": bad})
    assert r.status_code == 400 and r.get_json()["ok"] is False
    good = copy.deepcopy(contest.NOV_2026)
    good["name"] = "חדש"
    assert c.post("/v2/api/contest/save", json={"contest": good}).get_json()["ok"]
    lst = st["cfg"]["v2_contests"]["list"]
    assert [x["name"] for x in lst] == ["חדש"], lst
    assert any(l[3] == "תחרות — עדכון" for l in st["logs"]), st["logs"]
    r = c.post("/v2/api/contest/save", json={"copy_from": "2026-11", "id": "2026-12", "name": "דצמבר",
                                              "start": "2026-12-01", "end": "2026-12-31"})
    assert r.get_json()["ok"], r.get_json()
    lst = st["cfg"]["v2_contests"]["list"]
    assert [x["id"] for x in lst] == ["2026-11", "2026-12"] and lst[1]["groups"] == lst[0]["groups"]


def test_adjust():
    c, st = make(MGR)
    base = {"contest": "2026-11", "group": 0, "kind": "row", "label": "רויטל גל", "pts": 25, "reason": "בונוס"}
    assert pts(c.get("/v2/api/contest").get_json(), "רויטל גל") == 5
    assert c.post("/v2/api/contest/adjust", json=base).get_json()["ok"]
    assert pts(c.get("/v2/api/contest").get_json(), "רויטל גל") == 30
    assert any(l[3] == "תחרות — תיקון ידני" for l in st["logs"])
    aid = st["cfg"]["v2_contest_adj"]["2026-11"][0]["id"]
    for bad in (0, 1001, -1001, 1.5, "5", True):
        assert c.post("/v2/api/contest/adjust", json=dict(base, pts=bad)).status_code == 400, bad
    assert c.post("/v2/api/contest/adjust", json=dict(base, reason="")).status_code == 400
    assert c.post("/v2/api/contest/adjust", json={"contest": "2026-11", "delete": aid}).get_json()["ok"]
    assert pts(c.get("/v2/api/contest").get_json(), "רויטל גל") == 5
    assert any(l[3] == "תחרות — מחיקת תיקון" for l in st["logs"])


def test_deleted_meeting():
    nb = {"f": {"agent": "רויטל גל", "by": "רויטל גל", "status": "meeting", "meeting_at": NOW + 86400, "date": NOW + 86400},
          "p": {"agent": "רויטל גל", "by": "רויטל גל", "status": "meeting", "meeting_at": NOW - 7200, "date": NOW - 7200}}
    c, st = make(REV, nb=nb)
    assert pts(c.get("/v2/api/contest").get_json(), "רויטל גל") == 10
    st["cfg"]["nbStatus"].clear()
    assert pts(c.get("/v2/api/contest").get_json(), "רויטל גל") == 5   # העתידית ירדה, העבר נשאר


def test_ledger_write_once():
    c, st = make(REV)
    c.get("/v2/api/contest")
    m = st["mut"]
    assert m == 1 and "2026-11" in st["cfg"]["v2_contest_ledger"], m
    c.get("/v2/api/contest")
    assert st["mut"] == m, "ה-ledger לא השתנה — אסור לכתוב שוב"


def test_get_adjustments_and_def():
    c, st = make(MGR)
    base = {"contest": "2026-11", "group": 0, "kind": "row", "label": "רויטל גל", "pts": 25, "reason": "בונוס"}
    assert c.post("/v2/api/contest/adjust", json=base).get_json()["ok"]
    j = c.get("/v2/api/contest").get_json()
    assert [a["reason"] for a in j["adjustments"]] == ["בונוס"], j.get("adjustments")
    assert j["def"]["id"] == "2026-11" and j["def"]["groups"][0]["rows"][0]["label"] == "נדב רייזר", j.get("def")
    c2, st2 = make(REV)
    st2["cfg"]["v2_contest_adj"] = st["cfg"]["v2_contest_adj"]
    j = c2.get("/v2/api/contest").get_json()
    assert [a["label"] for a in j["adjustments"]] == ["רויטל גל"] and "by" not in j["adjustments"][0], j
    assert j.get("def") is None, "הגדרת התחרות רק למי שעורך"
    c3, _ = make(None, tv_key="K1")
    assert c3.get("/v2/api/contest?k=K1").get_json()["adjustments"] == []



GEN_COORD = {"name": "מנהל", "role": "admin", "drole": "manager", "phone": "507777777"}
GEN_MGR = {"name": "מנהל", "role": "admin", "drole": "manager", "phone": "505709865"}
PH = {"507777777": "נוי רבן", "505709865": "אייל שמול"}


def _disp(n, p):
    return PH.get(p, n) if n == "מנהל" else n


def test_generic_manager_name():   # [FIX1]
    c, _ = make(GEN_COORD, disp=_disp)
    j = c.get("/v2/api/contest").get_json()
    assert j["can_edit"] is False, j
    assert j["me"] == {"group": 0, "kind": "coord", "label": "נוי רבן"}, j["me"]
    assert c.post("/v2/api/contest/save", json={"contest": contest.NOV_2026}).status_code == 403
    assert c.post("/v2/api/contest/adjust", json={"contest": "2026-11", "group": 0, "kind": "row",
                                                  "label": "רויטל גל", "pts": 5, "reason": "x"}).status_code == 403
    c, _ = make(GEN_MGR, disp=_disp)
    j = c.get("/v2/api/contest").get_json()
    assert j["can_edit"] is True and j["me"] is None, j


def test_sigs_failure_last_good():   # [FIX2]
    c, st = make(REV)
    good = c.get("/v2/api/contest").get_json()["board"]
    assert "partial" not in good and "stale" not in good
    st["sig_fail"] = True
    b = c.get("/v2/api/contest").get_json()["board"]
    assert b.get("stale") is True and b["groups"] == good["groups"] and b["leader"] == good["leader"], b
    c, st = make(REV)
    st["sig_fail"] = True
    b = c.get("/v2/api/contest").get_json()["board"]
    assert b.get("partial") is True and b["leader"] is None, b


def test_malformed_save_and_adjust():   # [FIX4]
    c, _ = make(MGR)
    def m(fn):
        x = copy.deepcopy(contest.NOV_2026); fn(x); return x
    for bad in (m(lambda x: x.__setitem__("groups", [1, 2])),
                m(lambda x: x["groups"][0]["rows"].append({"label": "x"})),
                m(lambda x: x["groups"][0]["rows"][0].__setitem__("members", "נדב")),
                m(lambda x: x["groups"][1].__setitem__("coords", "אוצר")),
                m(lambda x: x["groups"][1].__setitem__("name", None)),
                m(lambda x: x["pts"].__setitem__("gius", 1.5))):
        r = c.post("/v2/api/contest/save", json={"contest": bad})
        assert r.status_code == 400 and r.get_json()["ok"] is False, (r.status_code, bad)
    base = {"contest": "2026-11", "kind": "row", "label": "רויטל גל", "pts": 5, "reason": "x"}
    for g in (0.0, 1.0, True, "0", None, 2):
        assert c.post("/v2/api/contest/adjust", json=dict(base, group=g)).status_code == 400, g
    assert c.post("/v2/api/contest/adjust", json=dict(base, group=1)).get_json()["ok"]


def test_build_exception_safe():   # [FIX4]
    broken = copy.deepcopy(contest.NOV_2026)
    broken["groups"][0]["rows"].append({"label": "שבור"})          # בלי members — score נופל
    c, _ = make(MGR, cfg_extra={"v2_contests": {"list": [broken]}})
    r = c.get("/v2/api/contest")
    assert r.status_code == 200, r.status_code
    j = r.get_json()
    assert j["board"] is None and j["def"]["id"] == "2026-11", j
    c, _ = make(REV, cfg_extra={"v2_contests": {"list": [broken]}})
    r = c.get("/v2/api/contest")
    assert r.status_code == 200 and r.get_json()["board"] is None


def test_unmatched_for_editors():   # [FIX5]
    known = {n: "0500000000" for n in ["רויטל גל", "נדב רייזר"]}
    c, _ = make(MGR, g_extra={"fetch_agents_phones": lambda: known})
    j = c.get("/v2/api/contest").get_json()
    u = j.get("unmatched")
    assert isinstance(u, list) and "אור צוקרמן" in u and "נויה" in u and "רויטל גל" not in u and "נדב רייזר" not in u, u
    c, _ = make(REV, g_extra={"fetch_agents_phones": lambda: known})
    assert "unmatched" not in c.get("/v2/api/contest").get_json()
    c, _ = make(MGR)                      # אין מקור שמות — לא מציגים רשימה מטעה
    assert not c.get("/v2/api/contest").get_json().get("unmatched")


def test_generation_key():   # [FIX-m2]
    c, st = make(MGR)
    c.get("/v2/api/contest")
    k1 = st["swr"][-1]
    assert c.post("/v2/api/contest/adjust", json={"contest": "2026-11", "group": 0, "kind": "row",
                                                  "label": "רויטל גל", "pts": 5, "reason": "x"}).get_json()["ok"]
    c.get("/v2/api/contest")
    assert st["swr"][-1] != k1 and k1 in st["cleared"], (k1, st["swr"][-1], st["cleared"])


def test_can_edit_latest_contest():   # [FIX-m4]
    old = dict(copy.deepcopy(contest.NOV_2026), id="2026-08", start="2026-08-01", end="2026-08-31")
    old["groups"][0]["coords"] = ["אחר"]
    new = dict(copy.deepcopy(contest.NOV_2026), id="2026-09", start="2026-09-01", end="2026-09-30")
    c, _ = make(COORD_MGR, cfg_extra={"v2_contests": {"list": [old, new]}})
    assert c.get("/v2/api/contest").get_json()["can_edit"] is False   # נוי מתאמת בתחרות האחרונה


def test_power_day_route_and_hiding():   # [POWER-DAY 04/11]
    for sess in (REV, COORD_MGR):
        c, _ = make(sess)
        assert c.post("/v2/api/contest/power", json={"contest": "2026-11", "date": "2026-11-15"}).status_code == 403
    c, st = make(MGR)
    assert c.post("/v2/api/contest/power", json={"contest": "2026-11", "date": "2026-12-02"}).status_code == 400
    assert c.post("/v2/api/contest/power", json={"contest": "2026-11", "date": "x"}).status_code == 400
    r = c.post("/v2/api/contest/power", json={"contest": "2026-11", "date": "2026-11-15"}).get_json()
    assert r["ok"] and r["power_all"] == ["2026-11-15"], r
    assert any(l[3] == "תחרות — Power Day נקבע" for l in st["logs"])
    j = c.get("/v2/api/contest").get_json()
    assert j["power_all"] == ["2026-11-15"] and j["board"]["power_days"] == [] and j["board"]["power_today"] is False
    # סוכן לא רואה יום עתידי
    c2, st2 = make(REV, cfg_extra={"v2_contest_power": {"2026-11": ["2026-11-15"]}})
    j2 = c2.get("/v2/api/contest").get_json()
    assert "power_all" not in j2 and j2["board"]["power_days"] == [] and pts(j2, "רויטל גל") == 5
    # היום — ניקוד כפול לפגישה שנקבעה היום
    c3, st3 = make(REV, cfg_extra={"v2_contest_power": {"2026-11": ["2026-11-10"]}})
    j3 = c3.get("/v2/api/contest").get_json()
    assert j3["board"]["power_today"] is True and pts(j3, "רויטל גל") == 10, j3["board"]["power_days"]
    # ביטול
    r = c.post("/v2/api/contest/power", json={"contest": "2026-11", "date": "2026-11-15", "on": False}).get_json()
    assert r["ok"] and r["power_all"] == []


def test_power_run_sends_once():
    sent = []
    cfg = {"v2_contest_power": {"2026-11": ["2026-11-10"]}}
    phones = {"נדב רייזר": "0501111111", "נוי רבן": "0502222222", "אייל שמול": "0505709865", "אור צוקרמן": "0529999999"}
    G = AutoG(_d360_on=lambda: True, _quiet_mode=lambda: False, _switch_off=lambda n: False,
              _load_config=lambda: cfg, fetch_agents_phones=lambda: phones, _agent_vphones9=lambda: {"529999999"},
              _wa_phone=lambda p: "972" + str(p)[1:], _last9=lambda p: "".join(ch for ch in str(p) if ch.isdigit())[-9:],
              send_text=lambda to, t: sent.append((to, t)) or True, _log_activity=lambda *a: None,
              _canon_key=_key, _canon_agent_name=lambda n: n,
              _config_mutate=lambda fn: (True, fn(cfg)))
    os.environ.pop("CONTEST_POWER_WA", None); os.environ.pop("CONTEST_POWER_EXTRA", None)
    n = contest.power_run(G, NOW, _key)
    tos = sorted(t for t, _ in sent)
    assert n == 3 and tos == ["972501111111", "972502222222", "972505709865"], (n, tos)   # הנייד של אור = וירטואלי → לא
    assert all("POWER DAY" in t and "\n" not in t for _, t in sent)
    rec = cfg["v2_contest_power_sent"]["2026-11"]["2026-11-10"]
    assert rec[_key("נדב רייזר")]["r"] == "sent" and rec[_key("אור צוקרמן")]["r"] == "no_phone"
    assert contest.power_run(G, NOW + 60, _key) == 0 and len(sent) == 3        # פעם אחת
    early = dt.datetime(2026, 11, 10, 8, 30, tzinfo=IL).timestamp()
    cfg2 = {"v2_contest_power": {"2026-11": ["2026-11-10"]}}
    G2 = AutoG(dict(G, _load_config=lambda: cfg2))
    assert contest.power_run(G2, early, _key) == 0                              # לפני 09:00
    G3 = AutoG(dict(G, _load_config=lambda: cfg2, _quiet_mode=lambda: True))
    assert contest.power_run(G3, NOW, _key) == 0                                # שבת / השתקה
    os.environ["CONTEST_POWER_WA"] = "0"
    assert contest.power_run(AutoG(dict(G, _load_config=lambda: cfg2)), NOW, _key) == 0
    os.environ.pop("CONTEST_POWER_WA", None)


if __name__ == "__main__":
    n = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_") and callable(v):
            v(); n += 1; print("ok", k)
    print(n, "passed")
