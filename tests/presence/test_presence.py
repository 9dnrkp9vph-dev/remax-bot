"""במשרד / מחוץ למשרד לפי IP (אייל 19/10: 'לדעת מי נמצא במשרד ומשתמש או מהבית').
רץ ישירות: python3 tests/presence/test_presence.py"""
import os, sys, datetime as dt
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from flask import Flask
import office_presence as op

IPS = [{"branch": "ביאליק", "ip": "79.180.1.1"}, {"branch": "ביאליק", "ip": "79.180.1.2"},
       {"branch": "מוצקין", "ip": "2a02:6680::1"}]


def test_client_ip():
    assert op.client_ip({"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9"}, "10.0.0.1") == "1.2.3.4"
    assert op.client_ip({"X-Forwarded-For": "5.6.7.8, 10.1.1.1"}, "10.0.0.1") == "5.6.7.8"
    assert op.client_ip({}, "10.0.0.1") == "10.0.0.1"
    assert op.client_ip({"CF-Connecting-IP": "zzz"}, "") == ""          # זבל → ריק


def test_device():
    assert op.device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)") == "אייפון"
    assert op.device_label("Mozilla/5.0 (Linux; Android 14; SM-S911B)") == "אנדרואיד"
    assert op.device_label("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)") == "אייפד"
    assert op.device_label("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)") == "מחשב"
    assert op.device_label("") == ""


def test_place_for_ip():
    assert op.place_for_ip("79.180.1.2", IPS) == "ביאליק"
    assert op.place_for_ip("2a02:6680:0::1", IPS) == "מוצקין"               # אותה כתובת בכתיב אחר
    assert op.place_for_ip("8.8.8.8", IPS) == ""
    assert op.place_for_ip("", IPS) == ""


def test_clean_entries():
    raw = IPS + [{"branch": "", "ip": "1.1.1.1"}, {"branch": "ים", "ip": "nope"}, {"branch": "ביאליק", "ip": "79.180.1.1"}]
    out = op.clean_entries(raw)
    assert [e["ip"] for e in out] == ["79.180.1.1", "79.180.1.2", "2a02:6680::1"], out


def test_where_label():
    h = {"CF-Connecting-IP": "79.180.1.1", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)"}
    assert op.where_label(h, "", IPS) == "IP 79.180.1.1 · אייפון · במשרד ביאליק"
    h2 = {"CF-Connecting-IP": "8.8.8.8", "User-Agent": "Mozilla/5.0 (Macintosh)"}
    assert op.where_label(h2, "", IPS) == "IP 8.8.8.8 · מחשב · מחוץ למשרד"
    assert op.where_label(h2, "", []) == "IP 8.8.8.8 · מחשב"                 # בלי כתובות משרד — בלי תווית


def test_presence_change():
    st = {}
    d = dt.datetime(2026, 10, 20, 9, 0)
    assert op.presence_change(st, "501", "ביאליק", d) == "מיקום: במשרד · ביאליק"
    assert op.presence_change(st, "501", "ביאליק", d + dt.timedelta(minutes=5)) is None
    assert op.presence_change(st, "501", "", d + dt.timedelta(hours=2)) == "מיקום: מחוץ למשרד"
    assert op.presence_change(st, "501", "", d + dt.timedelta(days=1)) == "מיקום: מחוץ למשרד"   # יום חדש — רישום חדש


def test_office_minutes():
    t0 = 1_000_000.0
    events = {"501": [(t0 - 10, True), (t0 + 600, False)]}       # במשרד, ואחרי 10 דק' יצא
    pts = [(t0 + i * 45, "501") for i in range(27)]               # 0..1170ש' ברצף
    office = op.office_minutes(pts, events)
    assert 9 <= office <= 11, office
    assert op.office_minutes([(t0, "501")], events) == 0.75       # פעימה בודדת במשרד
    assert op.office_minutes([(t0, "777")], events) == 0           # אין אירוע → מחוץ למשרד


def test_timeline_from_activity():
    items = [{"ts": 5, "phone": "0501111111", "action": "מיקום: במשרד · ביאליק"},
             {"ts": 9, "phone": "0501111111", "action": "מיקום: מחוץ למשרד"},
             {"ts": 7, "phone": "0501111111", "action": "חיפוש נכסים"}]
    assert op.timeline_from_activity(items) == {"501111111": [(5.0, True), (9.0, False)]}


def test_stale_warning():
    sun_noon = dt.datetime(2026, 10, 18, 13, 0)    # ראשון
    st = {p: {"place": "", "day": "2026-10-18", "ts": 0} for p in ("1", "2", "3")}
    assert op.stale_warning(IPS, st, sun_noon)
    st["2"]["place"] = "ביאליק"
    assert not op.stale_warning(IPS, st, sun_noon)
    st["2"]["place"] = ""
    assert not op.stale_warning(IPS, st, dt.datetime(2026, 10, 17, 13, 0))   # שבת
    assert not op.stale_warning([], st, sun_noon)                             # לא הוגדר
    assert not op.stale_warning(IPS, st, dt.datetime(2026, 10, 18, 9, 0))   # לפני 12:00


# ---- ראוטים ----
class AutoG(dict):
    def __missing__(self, k):
        return lambda *a, **kw: None


def make(cfg, dev=True, phone="505709865"):
    logs = []

    def mutate(fn):
        fn(cfg)
        return True, True
    G = AutoG(log=None, _load_config=lambda: cfg, _config_mutate=mutate,
              _web_auth=lambda: {"phone": phone, "name": "אייל שמול", "role": "admin"},
              _is_dev=lambda p: dev, _last9=lambda p: str(p or "")[-9:],
              _log_activity=lambda *a: logs.append(a))
    app = Flask(__name__)

    @app.route("/v2/api/ping", methods=["POST"])
    def ping():
        return {"ok": True}
    op.register(app, G)
    return app, logs


def test_admin_routes():
    cfg = {}
    app, logs = make(cfg)
    c = app.test_client()
    h = {"CF-Connecting-IP": "79.180.1.1"}
    j = c.get("/v2/api/admin/office_ips", headers=h).get_json()
    assert j["ok"] and j["entries"] == [] and j["my_ip"] == "79.180.1.1" and j["my_place"] == ""
    j = c.post("/v2/api/admin/office_ips", json={"action": "add", "branch": "ביאליק", "ip": "79.180.1.1"}).get_json()
    assert j["ok"] and cfg["v2_office_ips"][0]["ip"] == "79.180.1.1"
    assert c.post("/v2/api/admin/office_ips", json={"action": "add", "branch": "ביאליק", "ip": "bad"}).get_json()["reason"] == "bad_ip"
    assert c.get("/v2/api/admin/office_ips", headers=h).get_json()["my_place"] == "ביאליק"
    c.post("/v2/api/admin/office_ips", json={"action": "del", "ip": "79.180.1.1"})
    assert cfg["v2_office_ips"] == [] and logs
    app2, _ = make({}, dev=False)
    assert app2.test_client().get("/v2/api/admin/office_ips").status_code == 403


def test_ping_hook_logs_place_changes():
    cfg = {"v2_office_ips": [{"branch": "ביאליק", "ip": "79.180.1.1"}]}
    app, logs = make(cfg)
    c = app.test_client()
    c.post("/v2/api/ping", headers={"CF-Connecting-IP": "79.180.1.1", "User-Agent": "iPhone"})
    c.post("/v2/api/ping", headers={"CF-Connecting-IP": "79.180.1.1", "User-Agent": "iPhone"})
    c.post("/v2/api/ping", headers={"CF-Connecting-IP": "8.8.8.8", "User-Agent": "iPhone"})
    acts = [l[3] for l in logs]
    assert acts == ["מיקום: במשרד · ביאליק", "מיקום: מחוץ למשרד"], acts
    assert logs[0][4] == "IP 79.180.1.1 · אייפון"
    assert app.presence_place("505709865") == ""                  # עכשיו בחוץ
    app2, logs2 = make({})                                        # בלי כתובות משרד — לא רושמים מיקום
    app2.test_client().post("/v2/api/ping", headers={"CF-Connecting-IP": "8.8.8.8"})
    assert not logs2 and app2.presence_place("505709865") is None


def _effie_const(name):
    import ast
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name:
            return n.value.value if isinstance(n.value, ast.Constant) else n
    raise NameError(name)


def test_usage_now_rows_place():
    import ast, re
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "effie_v2.py"), encoding="utf-8").read()
    ns = {"_re": re, "re": re}
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name in ("usage_now_rows", "_bp_digits", "bpage_iso_ep"):
            exec(compile(ast.Module([n], []), "effie_v2.py", "exec"), ns)
    pings = [{"phone": "0501111111", "name": "דנה", "ts": "2026-10-20T07:00:00+00:00"},
             {"phone": "0502222222", "name": "רון", "ts": "2026-10-20T07:00:30+00:00"}]
    now = dt.datetime(2026, 10, 20, 7, 1, tzinfo=dt.timezone.utc).timestamp()
    rows = ns["usage_now_rows"](pings, now, lambda n, p: n, place_for=lambda p: "ביאליק" if p == "501111111" else "")
    assert {r["name"]: r["place"] for r in rows} == {"דנה": "ביאליק", "רון": ""}, rows
    assert "place" not in ns["usage_now_rows"](pings, now, lambda n, p: n)[0]


def test_place_label_js():
    import re, shutil, subprocess
    if not shutil.which("node"):
        return
    html = _effie_const("V2_ACTIVITY_HTML")
    fn = re.search(r"function placeTxt\(p\)\{.*?\n", html).group(0)
    js = "function esc(s){return String(s);}" + fn + \
         "console.log(JSON.stringify([placeTxt(null),placeTxt(undefined),placeTxt(''),placeTxt('ביאליק')]))"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True).stdout.strip()
    import json
    assert json.loads(out) == ["", "", " · מחוץ למשרד", " · במשרד ביאליק"], out


def test_usage_rows_office_minutes():
    import ast, re, logging
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
    t0 = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
    pings = [{"phone": "501111111", "name": "דנה", "ts": (t0 + dt.timedelta(seconds=45 * i)).isoformat()} for i in range(41)]

    class SB:
        def enabled(self): return True
        def fetch_pings_today(self, iso): return pings
        def fetch_activity_actions(self, t, prefixes):
            assert prefixes == ["מיקום:"]
            return [{"ts": t0.timestamp() - 5, "phone": "0501111111", "action": "מיקום: במשרד · ביאליק"},
                    {"ts": t0.timestamp() + 900, "phone": "0501111111", "action": "מיקום: מחוץ למשרד"}]
    cfg = {"v2_office_ips": [{"branch": "ביאליק", "ip": "1.1.1.1"}]}
    ns = {"re": re, "_sbdb": SB(), "_display_name_for": lambda n, p: n, "_canon_key": lambda n: n,
          "_last9": lambda p: str(p)[-9:], "_load_config": lambda: cfg, "_activity": [],
          "log": logging.getLogger("t"), "_office_presence_mod": op}
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and n.name in ("_usage_rows", "_usage_places"):
            exec(compile(ast.Module([n], []), "app.py", "exec"), ns)
    r = ns["_usage_rows"](t0)[0]
    assert r["min"] == 30 and r["office"] == 15, r
    cfg.clear()
    assert "office" not in ns["_usage_rows"](t0)[0]                 # בלי כתובות משרד — בלי עמודה


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            f(); n += 1; print("ok", k)
    print("%d passed" % n)
