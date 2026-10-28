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


def make(sess, buyers_fail=False, cfg=None, tv_key=""):
    os.environ["TV_KEY"] = tv_key
    now_iso = dt.datetime.now(IL).strftime("%Y-%m-%dT%H:%M")
    cfg = cfg if cfg is not None else {
        "office_name": "רימקס פמילי",
        "nbStatus": {
            "דנה::a": {"agent": "דנה כהן", "status": "meeting", "meeting_at": time.time(), "pkey": "x1"},
            "רון::b": {"agent": "רון לוי", "status": "meeting", "meeting_at": time.time(), "pkey": "x2"},
            "רון::c": {"agent": "רון לוי", "status": "meeting", "meeting_at": time.time(), "pkey": "x3"},
            "מיכל::d": {"agent": "מיכל בר", "status": "meeting", "meeting_at": time.time(), "pkey": "x4"}}}
    state = {"cfg": cfg, "mutates": 0, "logs": [], "cleared": []}

    def mutate(fn):
        state["mutates"] += 1
        res = fn(state["cfg"])
        return True, res

    def buyers():
        if buyers_fail:
            raise RuntimeError("boom")
        return [{"agent": "דנה כהן", "date": now_dmy(), "row": 5}, {"agent": "רון לוי", "date": now_dmy(), "row": 6}]

    class SB:
        def enabled(self): return True
        def bpage_all(self): return [{"row": 5, "last_sent_at": now_iso}]

    calls_t = (dt.datetime.now(IL) - dt.timedelta(hours=1)).strftime("%d/%m/%Y %H:%M")
    G = AutoG(
        log=None,
        _web_auth=lambda: sess,
        _swr=lambda k, ttl, b, **kw: b(),
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
        _coordinators_all=lambda: {"509999999": {"name": "אוצר", "agents": {"502222222"}, "names": {"מיכל בר"}}},
        web_phone_name_map=lambda: {"502222222": "רון לוי"},
        web_contacts_phone_name=lambda: {},
        _contacts_rows=lambda: CONTACTS,
        _suspended_set=lambda: {"505555555"},
        _removed_agent_keys=lambda: set(),
        _resolve_roles=lambda l9: ("admin", "accountant") if l9 == "506666666" else ("agent", "agent"),
        _usage_rows=lambda t_from, *a, **kw: [{"name": "דנה כהן", "min": 5}],
    )
    site_api.review_rows = lambda sb=None: [{"kind": "review", "key": "r1", "data": {
        "agents": ["מיכל בר"], "text": "מעולה", "at": dt.datetime.now(IL).isoformat()}}]
    app = Flask(__name__)
    goals.register(app, G)
    return app.test_client(), state


def test_agent_own_only():
    c, _ = make(AGENT)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["ok"] and j["view"] == "agent" and j["can_edit"] is False, j
    assert j["me"]["counts"]["meetings"] == 1 and j["me"]["counts"]["buyers"] == 1, j
    assert j["me"]["counts"]["bpage"] == 1 and j["me"]["counts"]["past_clients"] == 1, j
    assert j["me"]["targets"] == goals.DEFAULTS and j["total"] is None and "agents" not in j, j
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
    assert t["counts"]["missed"] == 1 and t["targets"]["meetings"] == 4 and t["partial"] is False, t
    assert all(a["seen_today"] is False for a in j["agents"]), j


def test_office_view():
    c, _ = make(MGR)
    j = c.get("/v2/api/goals/today").get_json()
    assert j["view"] == "office" and j["can_edit"] is True, j
    names = sorted(a["name"] for a in j["agents"])
    assert names == sorted(["דנה כהן", "רון לוי", "מיכל בר"]), names   # בלי בדיקה/מושהה/הנה"ח
    seen = {a["name"]: a["seen_today"] for a in j["agents"]}
    assert seen["דנה כהן"] is True and seen["רון לוי"] is False, seen
    assert j["total"]["counts"]["meetings"] == 4 and j["total"]["targets"]["buyers"] == 9, j


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
    j = c.post("/v2/api/goals/targets", json={"agent": "", "targets": {"meetings": 4, "zzz": 9}}).get_json()
    assert j["ok"] and j["targets"]["meetings"] == 4 and j["targets"]["buyers"] == 3, j
    j = c.post("/v2/api/goals/targets", json={"agent": "רון לוי", "targets": {"buyers": 7, "reviews": "999"}}).get_json()
    assert j["targets"] == {"meetings": 4, "buyers": 7, "past_clients": 5, "reviews": 50}, j
    assert st["mutates"] == 2
    gl = st["cfg"]["v2_goals"]
    assert gl["default"] == {"meetings": 4} and gl["agents"]["רון לוי"] == {"buyers": 7, "reviews": 50}, gl
    acts = [l for l in st["logs"] if l[3] == "יעדים — עדכון"]
    assert len(acts) == 2 and "רון לוי" in acts[1][4] and "7" in acts[1][4], acts
    j = c.get("/v2/api/goals/today?agent=" + "רון לוי").get_json()
    assert j["me"]["targets"]["buyers"] == 7, j
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
    assert o["total"]["targets"]["meetings"] == 4 and o["total"]["counts"]["meetings"] == 0
    o = goals.build_office(dict(src, roster=RuntimeError("x")), day, _key)
    assert o["rows"] == [] and o["total"]["partial"] is True, o


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v(); print("ok", k)
