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


def make(sess, tv_key="", nb=None, cfg_extra=None):
    os.environ["TV_KEY"] = tv_key
    cfg = {"nbStatus": nb if nb is not None else {
        "a": {"agent": "רויטל גל", "by": "רויטל גל", "status": "meeting", "meeting_at": NOW - 3600, "date": NOW - 3600}}}
    cfg.update(cfg_extra or {})
    st = {"cfg": cfg, "mut": 0, "logs": [], "cleared": []}

    def mutate(fn):
        st["mut"] += 1
        return True, fn(st["cfg"])

    G = AutoG(
        log=None, _web_auth=lambda: sess, _swr=lambda k, ttl, b, **kw: b(),
        _cache_clear=lambda k: st["cleared"].append(k), _load_config=lambda: st["cfg"],
        _config_mutate=mutate, _log_activity=lambda *a: st["logs"].append(a),
        _display_name_for=lambda n, p: n, _canon_key=_key, _canon_agent_name=lambda n: n,
        _last9=lambda p: "".join(c for c in str(p or "") if c.isdigit())[-9:],
        _coordinators_all=lambda: {"509999999": {"name": "אוצר", "agents": set(), "names": set()}},
        get_signings=lambda a, b: [], _deal_label=lambda c: "")
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


if __name__ == "__main__":
    n = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_") and callable(v):
            v(); n += 1; print("ok", k)
    print(n, "passed")
